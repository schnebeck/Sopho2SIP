# SPDX-License-Identifier: GPL-3.0-or-later
"""Kleiner Schaltplan-Generator für KiCad 9/10 (Sopho2SIP-Hardware).

Ein Schaltplan entsteht aus zwei getrennten Angaben:
  SOLL     – je Bauteil: Symbol, Wert, Footprint, {Pin: Netz}. Das ist die elektrische Wahrheit.
  Zeichnung – Lage der Bauteile, Leitungen, Labels, Rahmen (Methoden von Blatt).
pruefe_projekt() exportiert mit kicad-cli die Netzliste und vergleicht ihre Pin-Gruppen mit SOLL – über
hierarchische Blätter hinweg. Eine Zeichnung kann also umgestaltet werden, ohne unbemerkt Verbindungen zu ändern.

Handlage: Wird ein Blatt in KiCad von Hand schöner gesetzt (Bauteile, Beschriftungen, Leitungen verschoben), erkennt
schreibe_projekt() das am Fingerabdruck der Zeichnung. Ergibt das Projekt mit diesem Blatt dieselbe Netzliste wie
SOLL, wird das Blatt nach handlage/ übernommen; ab dann stammt seine Zeichnung von dort, Werte, Footprints und
Symbole weiter aus SOLL. Ändert die Handänderung die Schaltung, wird nichts geschrieben.
Zurück zur erzeugten Zeichnung: --handlage-verwerfen <Blatt>[,<Blatt>] (Blattname oder Dateiname).
Aus einer Kopie des Projekts übernehmen: --handlage-aus <Ordner> (dort geänderte Blätter gelten als Handänderung).

Netzarten in SOLL:
  Versorgungsnetze (Schlüssel von POWER)  → global über alle Blätter (Power-Symbole, Wert = Netzname)
  Netze in Blatt.export                   → hierarchisches Label; im Wurzelblatt mit gleichnamigen Blattpins verbunden
  alle anderen                            → lokal im Blatt
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import pathlib
import re
import subprocess
import sys
import tempfile
import uuid

LIB = pathlib.Path("/usr/share/kicad/symbols")
POWER = {"GND": "power:GND", "+3V3": "power:+3V3", "+5V": "power:+5V", "+3.3VA": "power:+3.3VA",
         "GNDA": "power:GNDA", "GND_ISO": "power:GND", "+3V3_ISO": "power:+3V3", "VBUS": "power:VBUS"}
EIGENE_SYMBOLE: dict[str, str] = {}          # lib_id → fertiger Symbolblock (z. B. CM4-Stecker)


# ------------------------------------------------------------------------------------------------------------------
# Bibliothek
# ------------------------------------------------------------------------------------------------------------------
_NS = uuid.UUID("5f0c2f6e-3b7a-4d1e-9a51-50f2a9c3e7d1")    # Namensraum Sopho2SIP
_ZAEHLER = {"kontext": "", "n": 0}


def u() -> str:
    """Reproduzierbare UUID (Kontext + laufende Nummer): gleiche Zeichnung → gleiche Datei, keine Git-Unruhe."""
    _ZAEHLER["n"] += 1
    return str(uuid.uuid5(_NS, f'{_ZAEHLER["kontext"]}#{_ZAEHLER["n"]}'))


def u_fest(schluessel: str) -> str:
    """Feste UUID für Dinge, auf die von außen verwiesen wird (Blätter, Bauteile ↔ Platine)."""
    return str(uuid.uuid5(_NS, schluessel))


def uuid_kontext(name: str) -> None:
    _ZAEHLER["kontext"], _ZAEHLER["n"] = name, 0


def rd(v: float) -> float:
    return round(v, 2)


def _block(text: str, start: int) -> str:
    tiefe = 0
    for j in range(start, len(text)):
        if text[j] == "(":
            tiefe += 1
        elif text[j] == ")":
            tiefe -= 1
            if tiefe == 0:
                return text[start:j + 1]
    raise ValueError("unvollständiger Block")


_cache: dict[str, str] = {}


def lib_symbol(lib_id: str) -> str:
    """Symbolblock mit aufgelöstem 'extends' (Schaltpläne enthalten nur flache Symbole)."""
    if lib_id in EIGENE_SYMBOLE:
        return EIGENE_SYMBOLE[lib_id]
    bib, name = lib_id.split(":")
    if bib not in _cache:
        _cache[bib] = (LIB / f"{bib}.kicad_sym").read_text(encoding="utf-8")
    text = _cache[bib]
    i = text.find(f'(symbol "{name}"')
    if i < 0:
        raise KeyError(lib_id)
    sym = _block(text, i)
    m = re.search(r'\(extends "([^"]+)"\)', sym)
    if not m:
        return sym.replace(f'(symbol "{name}"', f'(symbol "{lib_id}"', 1)
    basis_name = m.group(1)
    basis = lib_symbol(f"{bib}:{basis_name}")
    for p in re.finditer(r'\(property "([^"]+)".*?\n\t\t\)', sym, re.S):
        if f'(property "{p.group(1)}"' in basis:
            basis = re.sub(r'\(property "%s".*?\n\t\t\)' % re.escape(p.group(1)), lambda _m, s=p.group(0): s,
                           basis, count=1, flags=re.S)
        else:   # Eigenschaft nur im abgeleiteten Symbol (z. B. ki_keywords): vor den Einheiten einfügen
            k = basis.find('\n\t\t(symbol "')
            basis = basis[:k] + "\n\t\t" + p.group(0) + basis[k:]
    basis = basis.replace(f'(symbol "{bib}:{basis_name}"', f'(symbol "{bib}:{name}"', 1)
    return basis.replace(f'(symbol "{basis_name}_', f'(symbol "{name}_')


def lib_pins(sym: str) -> dict[str, tuple[float, float, int]]:
    return {m.group(4): (float(m.group(1)), float(m.group(2)), int(m.group(3)))
            for m in re.finditer(r'\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) (\d+)\).*?\(number "([^"]*)"', sym, re.S)}


def lage(sym: str, name: str) -> tuple[float, float, float]:
    m = re.search(r'\(property "%s" "[^"]*"\s*\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)' % name, sym)
    return (float(m.group(1)), float(m.group(2)), float(m.group(3) or 0)) if m else (0.0, 0.0, 0.0)


def transform(px: float, py: float, rot: int, spiegel: str | None) -> tuple[float, float]:
    """Bibliothekskoordinate (y nach oben) → Versatz im Schaltplan (y nach unten).
    KiCad (am Testschaltplan bestimmt): erst gegen den Uhrzeigersinn drehen, dann spiegeln, dann y umkehren."""
    a = math.radians(rot)
    x = px * math.cos(a) - py * math.sin(a)
    y = px * math.sin(a) + py * math.cos(a)
    if spiegel == "y":
        x = -x
    elif spiegel == "x":
        y = -y
    return round(x, 3), round(-y, 3)


def stecker_symbol(lib_id: str, links: list, rechts: list, unten: list, oben: list, breite: float,
                   footprint: str, beschreibung: str, datenblatt: str) -> str:
    """Rechteck-Symbol für Steckverbinder/Module. Listen aus (Nummer, Name, Typ) bzw. None für eine Leerzeile;
    'unten'/'oben': Gruppen gleichnamiger Pins, die übereinander liegen (erster sichtbar, Rest versteckt)."""
    name = lib_id.split(":")[1]
    zeilen = max(len(links), len(rechts))
    h = zeilen * 2.54 + 2.54
    x0, y0 = -breite / 2, h / 2
    pins = []

    def pin(nr, nm, typ, x, y, winkel, versteckt=False):
        hide = " (hide yes)" if versteckt else ""
        pins.append(f'(pin {typ} line (at {rd(x)} {rd(y)} {winkel}) (length 2.54){hide} (name "{nm}" (effects (font '
                    f'(size 1.27 1.27)))) (number "{nr}" (effects (font (size 1.27 1.27)))))')
    for i, e in enumerate(links):
        if e:
            pin(e[0], e[1], e[2], x0 - 2.54, y0 - 2.54 * (i + 1), 0)
    for i, e in enumerate(rechts):
        if e:
            pin(e[0], e[1], e[2], -x0 + 2.54, y0 - 2.54 * (i + 1), 180)
    for gruppen, yy, winkel in ((unten, -y0 - 2.54, 90), (oben, y0 + 2.54, 270)):
        for k, gruppe in enumerate(gruppen):
            x = (k - (len(gruppen) - 1) / 2) * 5.08
            for j, (nr, nm, typ) in enumerate(gruppe):
                pin(nr, nm, typ if j == 0 else "passive", x, yy, winkel, versteckt=j > 0)
    eig = lambda n, w, x, y, hide=False, j="": (
        f'(property "{n}" "{w}" (at {x} {y} 0) (effects (font (size 1.27 1.27)){" (justify " + j + ")" if j else ""}'
        f'{" (hide yes)" if hide else ""}))')
    return (f'(symbol "{lib_id}" (pin_names (offset 1.016)) (exclude_from_sim no) (in_bom yes) (on_board yes)\n'
            f'\t{eig("Reference", "J", rd(x0), rd(y0 + 1.27), j="left")}\n'
            f'\t{eig("Value", name, rd(-x0), rd(y0 + 1.27), j="right")}\n'
            f'\t{eig("Footprint", footprint, 0, 0, True)}\n\t{eig("Datasheet", datenblatt, 0, 0, True)}\n'
            f'\t{eig("Description", beschreibung, 0, 0, True)}\n'
            f'\t(symbol "{name}_0_1" (rectangle (start {rd(x0)} {rd(y0)}) (end {rd(-x0)} {rd(-y0)}) '
            f'(stroke (width 0.254) (type default)) (fill (type background))))\n'
            f'\t(symbol "{name}_1_1"\n\t\t' + "\n\t\t".join(pins) + '\n\t)\n\t(embedded_fonts no)\n)')


# ------------------------------------------------------------------------------------------------------------------
# Blatt
# ------------------------------------------------------------------------------------------------------------------
class Blatt:
    def __init__(self, name: str, soll: dict, datei: str, export: set[str] | None = None, papier: str = "A3",
                 versatz: tuple[float, float] = (0, 0), titel: str = "", kommentare: tuple = ()) -> None:
        self.name, self.soll, self.datei = name, soll, datei
        self.export = set(export or ())
        self.papier, self.versatz, self.titel, self.kommentare = papier, versatz, titel, kommentare
        self.uuid = u_fest(f"blatt:{datei}")
        self.teile: list[tuple] = []          # (ref, lib_id, wert, fp, x, y, rot, spiegel, texte)
        self.pinpos: dict[tuple[str, str], tuple[float, float]] = {}
        self.segmente: list[tuple[tuple[float, float], tuple[float, float]]] = []
        self.labels: list[tuple[str, tuple[float, float], str]] = []
        self.power: list[tuple[str, tuple[float, float], int, bool]] = []
        self.flaggen: list[tuple[float, float]] = []
        self.nc: list[tuple[float, float]] = []
        self.rahmen: list[tuple[float, float, float, float, str]] = []
        self.texte: list[tuple[float, float, str, float]] = []
        self.kaesten: list[tuple[float, float, float, float, str, float]] = []   # Textkästen (x, y, b, h, Text, Größe)
        self.herkunft: dict[str, list] = {"text": [], "notiz": [], "rahmen_": []}   # Aufrufstellen (Datei, Zeile, Art)
        self.textquellen: dict[str, tuple[str, tuple | None]] = {}   # UUID → (Text, Aufrufstelle); von schreibe_blatt
        self.striche: list[tuple[tuple[float, float], tuple[float, float]]] = []
        self.blaetter: list[dict] = []        # Blattsymbole (nur im Wurzelblatt)
        self.libs: dict[str, str] = {}

    # --- Bauteile ---------------------------------------------------------------------------------------------
    def setze(self, ref: str, x: float, y: float, rot: int = 0, spiegel: str | None = None,
              ref_at=None, wert_at=None, links: bool = False) -> None:
        """ref_at/wert_at: (dx, dy[, Ausrichtung]) relativ zum Bauteil, waagerecht; sonst Lage aus der Bibliothek.
        Zweipole R/C: waagerecht Name oben/Wert unten, senkrecht beide daneben (links=True: links daneben)."""
        lib_id = self.soll[ref][0]
        sym = self.libs.setdefault(lib_id, lib_symbol(lib_id))
        if lib_id in ("Device:R", "Device:C", "Device:Polyfuse"):
            if rot in (90, 270):
                d = 3.3 if lib_id == "Device:C" else 2.54
                ref_at = ref_at or (0, -d)
                wert_at = wert_at or (0, d + 0.25)
            else:
                dx, ausr = (-3.0, "right") if links else (3.0, "left")
                ref_at = ref_at or (dx, -1.27, ausr)
                wert_at = wert_at or (dx, 1.27, ausr)
        self.teile.append((ref, lib_id, self.soll[ref][1], self.soll[ref][2], rd(x), rd(y), rot, spiegel,
                           {"Reference": ref_at, "Value": wert_at}))
        for nr, (px, py, _a) in lib_pins(sym).items():
            dx, dy = transform(px, py, rot, spiegel)
            self.pinpos[(ref, nr)] = (rd(x + dx), rd(y + dy))

    def P(self, ref: str, nr: str) -> tuple[float, float]:
        return self.pinpos[(ref, nr)]

    # --- Verbindungen -----------------------------------------------------------------------------------------
    def w(self, *punkte) -> None:
        pts = [(rd(x), rd(y)) for x, y in punkte]
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            if a[0] != b[0] and a[1] != b[1]:
                raise ValueError(f"{self.name}: schräge Leitung {a}–{b}")
            self.segmente.append((a, b))

    def lbl(self, netz: str, p, richtung: str) -> None:
        """Label; Netze aus export werden hierarchische Labels."""
        self.labels.append((netz, (rd(p[0]), rd(p[1])), richtung))

    def pw(self, netz: str, p, rot: int = 0, senkrecht: bool = False) -> None:
        self.power.append((netz, (rd(p[0]), rd(p[1])), rot, senkrecht))

    def flag(self, p) -> None:
        self.flaggen.append((rd(p[0]), rd(p[1])))

    def offen(self, *refs_pins) -> None:
        for ref, nr in refs_pins:
            self.nc.append(self.P(ref, nr))

    def nc_alle(self, ref: str) -> None:
        self.offen(*[(ref, n) for n, netz in self.soll[ref][3].items() if netz == "NC"])

    def ab(self, ref: str, nr: str, netz: str, laenge: float = 2.54) -> None:
        """Kurzer Draht senkrecht nach unten zu einem Masse-/Versorgungssymbol."""
        x, y = self.P(ref, nr)
        self.w((x, y), (x, y + laenge))
        self.pw(netz, (x, y + laenge))

    def auf(self, ref: str, nr: str, netz: str, laenge: float = 2.54) -> None:
        """Kurzer Draht senkrecht nach oben zu einem Versorgungssymbol."""
        x, y = self.P(ref, nr)
        self.w((x, y), (x, y - laenge))
        self.pw(netz, (x, y - laenge))

    # --- Gestaltung -------------------------------------------------------------------------------------------
    def _merke(self, art: str) -> None:
        """Aufrufstelle im Generator merken (für die Rückführung geänderter Texte)."""
        f = sys._getframe(2)
        self.herkunft[art].append((f.f_code.co_filename, f.f_lineno, art))

    def rahmen_(self, x0, y0, x1, y1, titel) -> None:
        self._merke("rahmen_")
        self.rahmen.append((x0, y0, x1, y1, titel))

    def text(self, x, y, s, groesse=1.27) -> None:
        self._merke("text")
        self.texte.append((x, y, s, groesse))

    def notiz(self, x, y, breite, *absaetze, groesse=1.27) -> None:
        """Textkasten: KiCad bricht innerhalb der Breite selbst um; jeder Absatz beginnt eine neue Zeile.
        (x, y) wie bei text(): linker Anfang der Grundlinie der ersten Zeile."""
        self._merke("notiz")
        innen = breite - 2 * KASTEN_RAND
        zeilen = sum(_zeilen(a, innen, groesse) for a in absaetze)
        hoehe = 2 * KASTEN_RAND + zeilen * ZEILENABSTAND * groesse + 0.3 * groesse
        self.kaesten.append((rd(x - KASTEN_RAND), rd(y - groesse - KASTEN_RAND), breite, rd(hoehe),
                             "\n".join(absaetze), groesse))

    def trenn(self, x, y0, y1) -> None:
        self.striche.append(((x, y0), (x, y1)))

    # --- Hierarchie (Wurzelblatt) -----------------------------------------------------------------------------
    def blatt(self, kind: "Blatt", x: float, y: float, breite: float, pins: list[tuple[str, str, float]],
              hoehe: float | None = None) -> dict[str, tuple[float, float]]:
        """Blattsymbol für kind; pins: (Name, 'l'|'r', y-Versatz). Liefert die Pin-Positionen."""
        hoehe = hoehe or (max(dy for _, _, dy in pins) + 5.08 if pins else 20)
        pos = {}
        for name, seite, dy in pins:
            pos[name] = (rd(x if seite == "l" else x + breite), rd(y + dy))
        self.blaetter.append({"kind": kind, "x": x, "y": y, "b": breite, "h": hoehe, "pins": pins, "pos": pos})
        return pos


# ------------------------------------------------------------------------------------------------------------------
# Textkästen
# ------------------------------------------------------------------------------------------------------------------
KASTEN_RAND = 0.9525            # Innenrand wie in KiCad voreingestellt
ZEILENABSTAND = 1.61            # × Schriftgröße (mit pcbnew an der Strichschrift gemessen)
_SCHMAL, _BREIT = set("iljtfrI.,:;|!()[]' "), set("mwMW")


def _breite(s: str, groesse: float) -> float:
    """Geschätzte Breite in der KiCad-Strichschrift (eher reichlich; gemessen im Mittel 0,81 × Größe je Zeichen)."""
    return groesse * sum(0.55 if c in _SCHMAL else 1.3 if c in _BREIT else 0.85 for c in s)


def _zeilen(absatz: str, breite: float, groesse: float) -> int:
    """Zeilenzahl nach Wortumbruch."""
    n, zeile = 1, ""
    for wort in absatz.split():
        probe = f"{zeile} {wort}" if zeile else wort
        if zeile and _breite(probe, groesse) > breite:
            n, zeile = n + 1, wort
        else:
            zeile = probe
    return n


# ------------------------------------------------------------------------------------------------------------------
# Ausgabe
# ------------------------------------------------------------------------------------------------------------------
def _eigenschaft(name, wert, x, y, winkel=0, versteckt=False, ausrichtung=None) -> str:
    hide = " (hide yes)" if versteckt else ""
    j = f" (justify {ausrichtung})" if ausrichtung else ""
    return (f'\t\t(property "{name}" "{wert}"\n\t\t\t(at {rd(x)} {rd(y)} {winkel:g})\n'
            f'\t\t\t(effects (font (size 1.27 1.27)){j}{hide})\n\t\t)\n')


def _symbol_text(b: Blatt, projekt, pfad, ref, lib_id, wert, fp, x, y, rot, spiegel, pinnummern,
                 versteckt_ref=False, versteckt_wert=False, texte=None) -> str:
    sym = b.libs[lib_id]
    m = f"\t\t(mirror {spiegel})\n" if spiegel else ""
    s = (f'\t(symbol\n\t\t(lib_id "{lib_id}")\n\t\t(at {rd(x)} {rd(y)} {rot})\n{m}\t\t(unit 1)\n\t\t(exclude_from_sim no)\n'
         f'\t\t(in_bom {"no" if ref.startswith("#") or lib_id.startswith("Mechanical:") else "yes"})\n\t\t(on_board yes)\n'
         f'\t\t(dnp {"yes" if wert == "DNP" else "no"})\n\t\t(uuid "{u_fest(f"symbol:{b.datei}:{ref}")}")\n')
    # Textwinkel ist in KiCad relativ zur Bauteildrehung: bei 90°/270° ergibt 90° waagerechte Schrift
    waagerecht = 90 if rot in (90, 270) else 0
    for name, wertx, versteckt in (("Reference", ref, versteckt_ref), ("Value", wert, versteckt_wert)):
        vorgabe = (texte or {}).get(name)
        if vorgabe:
            ausr = vorgabe[2] if len(vorgabe) > 2 else None
            if ausr and (waagerecht + rot) % 360 == 180:
                # KiCad dreht die Schrift lesbar zurück und spiegelt dabei die Ausrichtung
                ausr = {"left": "right", "right": "left"}.get(ausr, ausr)
            s += _eigenschaft(name, wertx, x + vorgabe[0], y + vorgabe[1], waagerecht, versteckt, ausr)
            continue
        lx, ly, la = lage(sym, name)
        dx, dy = transform(lx, ly, rot, spiegel)
        s += _eigenschaft(name, wertx, x + dx, y + dy, waagerecht if rot in (90, 270) else la, versteckt)
    s += _eigenschaft("Footprint", fp, x, y, versteckt=True)
    s += _eigenschaft("Datasheet", "", x, y, versteckt=True)
    for n in pinnummern:
        s += f'\t\t(pin "{n}" (uuid "{u()}"))\n'
    s += (f'\t\t(instances\n\t\t\t(project "{projekt}"\n\t\t\t\t(path "{pfad}" (reference "{ref}") (unit 1))\n'
          f'\t\t\t)\n\t\t)\n\t)\n')
    return s


def _auf_strecke(pt, a, b) -> bool:
    (x, y), (x1, y1), (x2, y2) = pt, a, b
    if x1 == x2 == x:
        return min(y1, y2) < y < max(y1, y2)
    if y1 == y2 == y:
        return min(x1, x2) < x < max(x1, x2)
    return False


SEITE = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0)}
RAND, SCHRIFTFELD = 10.0, 44.0      # Blattrand; unten für das Schriftfeld freigehaltene Höhe


def _textkasten(x, y, s, groesse, ausr=None, unten=False):
    """Grob geschätzte Ausdehnung eines Textes (für die Zentrierung)."""
    br, h = len(s) * groesse * 0.9, groesse * 1.4
    x0 = x if ausr == "left" else x - br if ausr == "right" else x - br / 2
    y0 = y - h if unten else y - h / 2
    return [(x0, y0), (x0 + br, y0 + h)]


def _ausdehnung(b: Blatt) -> tuple[float, float, float, float]:
    """Umgebendes Rechteck aller Inhalte eines Blatts (Bibliothekskoordinaten vor dem Versatz)."""
    pts = [pt for seg in b.segmente for pt in seg] + list(b.pinpos.values()) + list(b.nc) + list(b.flaggen)
    pts += [pt for seg in b.striche for pt in seg]
    for ref, lib_id, wert, _fp, x, y, rot, spiegel, texte in b.teile:
        sym = b.libs[lib_id]
        for m in re.finditer(r"\((?:start|end|xy|center|mid) ([-\d.]+) ([-\d.]+)\)", sym):
            dx, dy = transform(float(m.group(1)), float(m.group(2)), rot, spiegel)
            pts.append((x + dx, y + dy))
        for name, s in (("Reference", ref), ("Value", wert)):
            vorgabe = (texte or {}).get(name)
            if vorgabe:
                pts += _textkasten(x + vorgabe[0], y + vorgabe[1], s, 1.27, vorgabe[2] if len(vorgabe) > 2 else None)
            else:
                lx, ly, _ = lage(sym, name)
                dx, dy = transform(lx, ly, rot, spiegel)
                pts += _textkasten(x + dx, y + dy, s, 1.27)
    for netz, (x, y), richtung in b.labels:
        br = len(netz) * 1.15 + 2.5
        pts += [(x - br if richtung == "l" else x, y - 1.5), (x + br if richtung == "r" else x, y + 1.5)]
    for netz, (x, y), _rot, _s in b.power:
        pts += [(x - 3.0, y - 5.0), (x + 3.0, y + 5.0)] + _textkasten(x, y, netz, 1.27)
    for x, y, s, g in b.texte:
        pts += _textkasten(x, y, s, g, "left", unten=True)
    for x, y, br, h, _s, _g in b.kaesten:
        pts += [(x, y), (x + br, y + h)]
    for bl in b.blaetter:
        pts += [(bl["x"], bl["y"] - 3.0), (bl["x"] + bl["b"], bl["y"] + bl["h"] + 3.0)]
    xs, ys = [p_[0] for p_ in pts], [p_[1] for p_ in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _einzelblock(b: Blatt) -> None:
    """Steht nur ein Block auf dem Blatt: Rahmen weglassen (sein Titel wird Blatttitel), Inhalt zentrieren."""
    if len(b.rahmen) > 1:
        return
    if b.rahmen:
        b.titel = b.titel or b.rahmen[0][4]
        b.rahmen = []
    breite, hoehe = SEITE[b.papier]
    x0, y0, x1, y1 = _ausdehnung(b)
    raster = 1.27
    dx = round(((breite / 2) - (x0 + x1) / 2) / raster) * raster
    dy = round(((RAND + hoehe - SCHRIFTFELD) / 2 - (y0 + y1) / 2) / raster) * raster
    b.versatz = (round(dx, 2), round(dy, 2))


def schreibe_blatt(b: Blatt, projekt: str, pfad: str, wurzel: Blatt | None = None) -> str:
    """Text der .kicad_sch-Datei. pfad = Instanzpfad der Bauteile ("/<wurzel>" oder "/<wurzel>/<blatt>")."""
    uuid_kontext(b.datei)
    _einzelblock(b)
    ox, oy = b.versatz
    v = lambda pt: (rd(pt[0] + ox), rd(pt[1] + oy))
    anschluss: dict[tuple, set] = {}
    for (ref, nr), pt in b.pinpos.items():
        netz = b.soll[ref][3].get(nr)
        if netz and netz != "NC":
            anschluss.setdefault(pt, set()).add(f"{ref}.{nr}")
    blattpins = {pt for bl in b.blaetter for pt in bl["pos"].values()}
    # T-Stellen: Endpunkte, die im Inneren einer anderen Strecke liegen → Strecke dort teilen (KiCad braucht das)
    punkte = {pt for seg in b.segmente for pt in seg} | set(anschluss) | {lp for _, lp, _ in b.labels} \
        | {pp for _, pp, _, _ in b.power} | set(b.flaggen) | blattpins
    segmente = list(dict.fromkeys(b.segmente))
    i = 0
    while i < len(segmente):
        a, c = segmente[i]
        teil = next((pt for pt in punkte if _auf_strecke(pt, a, c)), None)
        if teil:
            segmente[i:i + 1] = [(a, teil), (teil, c)]
            continue
        i += 1
    grad: dict[tuple, int] = {}
    for a, c in segmente:
        grad[a] = grad.get(a, 0) + 1
        grad[c] = grad.get(c, 0) + 1
    for pt in set(anschluss) | {pp for _, pp, _, _ in b.power} | set(b.flaggen) | {lp for _, lp, _ in b.labels} | blattpins:
        if pt in grad:
            grad[pt] += 1
    junctions = sorted(pt for pt, g in grad.items() if g >= 3)
    beruehrt = {pt for seg in segmente for pt in seg} | {lp for _, lp, _ in b.labels} | {pp for _, pp, _, _ in b.power}
    offen = sorted(", ".join(sorted(v_)) for pt, v_ in anschluss.items() if pt not in beruehrt)
    if offen:
        raise SystemExit(f"{b.name}: Pins ohne Anschluss in der Zeichnung: {offen}")
    nc_ohne = [(r, n) for (r, n), pt in b.pinpos.items() if b.soll[r][3].get(n) == "NC" and pt not in b.nc]
    if nc_ohne:
        raise SystemExit(f"{b.name}: NC-Pins ohne Markierung: {nc_ohne}")
    exportiert = {n for n, _, _ in b.labels if n in b.export}
    if b.export - exportiert:
        raise SystemExit(f"{b.name}: exportierte Netze ohne hierarchisches Label: {sorted(b.export - exportiert)}")

    t = []
    for ref, lib_id, wert, fp, x, y, rot, spiegel, texte in b.teile:
        x, y = v((x, y))
        t.append(_symbol_text(b, projekt, pfad, ref, lib_id, wert, fp, x, y, rot, spiegel,
                              sorted(lib_pins(b.libs[lib_id])), texte=texte))
    for i, (netz, pt, rot, senkrecht) in enumerate(b.power, 1):
        lib_id = POWER[netz]
        b.libs.setdefault(lib_id, lib_symbol(lib_id))
        texte = None
        if rot in (90, 270) and not senkrecht:
            # Schrift neben die Pfeilspitze (die Umkehr der Ausrichtung bei 90° erledigt _symbol_text)
            texte = {"Value": (3.3, 0, "left") if rot == 90 else (-3.3, 0, "right")}
        x, y = v(pt)
        t.append(_symbol_text(b, projekt, pfad, f"#PWR{b.name[:3].upper()}{i:03d}", lib_id, netz, "", x, y, rot, None,
                              ["1"], versteckt_ref=True, texte=texte))
    if b.flaggen:
        b.libs.setdefault("power:PWR_FLAG", lib_symbol("power:PWR_FLAG"))
    for i, pt in enumerate(b.flaggen, 1):
        x, y = v(pt)
        t.append(_symbol_text(b, projekt, pfad, f"#FLG{b.name[:3].upper()}{i:03d}", "power:PWR_FLAG", "PWR_FLAG", "",
                              x, y, 0, None, ["1"], versteckt_ref=True, versteckt_wert=True))
    for a, c in segmente:
        (x1, y1), (x2, y2) = v(a), v(c)
        t.append(f'\t(wire (pts (xy {x1} {y1}) (xy {x2} {y2})) (stroke (width 0) (type default)) (uuid "{u()}"))\n')
    for pt in junctions:
        x, y = v(pt)
        t.append(f'\t(junction (at {x} {y}) (diameter 0) (color 0 0 0 0) (uuid "{u()}"))\n')
    for pt in b.nc:
        x, y = v(pt)
        t.append(f'\t(no_connect (at {x} {y}) (uuid "{u()}"))\n')
    ausr = {"l": (180, "right"), "r": (0, "left"), "u": (90, "left"), "d": (270, "right")}
    for netz, pt, richtung in b.labels:
        a, j = ausr[richtung]
        x, y = v(pt)
        if netz in b.export:
            t.append(f'\t(hierarchical_label "{netz}" (shape bidirectional) (at {x} {y} {a}) '
                     f'(effects (font (size 1.27 1.27)) (justify {j})) (uuid "{u()}"))\n')
        else:
            t.append(f'\t(label "{netz}" (at {x} {y} {a}) (effects (font (size 1.27 1.27)) (justify {j} bottom)) '
                     f'(uuid "{u()}"))\n')
    herkunft = lambda art, i: b.herkunft[art][i] if i < len(b.herkunft[art]) else None
    b.textquellen = {}
    for i, (x0, y0, x1, y1, titel) in enumerate(b.rahmen):
        (x0, y0), (x1, y1) = v((x0, y0)), v((x1, y1))
        t.append(f'\t(rectangle (start {x0} {y0}) (end {x1} {y1}) (stroke (width 0.3) (type dash) (color 72 72 72 1)) '
                 f'(fill (type none)) (uuid "{u()}"))\n')
        kennung = u()
        b.textquellen[kennung] = (titel, herkunft("rahmen_", i))
        t.append(f'\t(text "{_escape(titel)}" (exclude_from_sim no) (at {rd(x0 + 2)} {rd(y0 + 5)} 0) '
                 f'(effects (font (size 2.2 2.2) bold) (justify left bottom)) (uuid "{kennung}"))\n')
    for i, (x, y, s, g) in enumerate(b.texte):
        x, y = v((x, y))
        kennung = u()
        b.textquellen[kennung] = (s, herkunft("text", i))
        t.append(f'\t(text "{_escape(s)}" (exclude_from_sim no) (at {x} {y} 0) (effects (font (size {g} {g}) italic) '
                 f'(justify left bottom)) (uuid "{kennung}"))\n')
    for i, (x, y, br, h, s, g) in enumerate(b.kaesten):
        x, y = v((x, y))
        kennung = u()
        b.textquellen[kennung] = (s, herkunft("notiz", i))
        t.append(f'\t(text_box "{_escape(s)}" (exclude_from_sim no) (at {x} {y} 0) (size {rd(br)} {rd(h)}) '
                 f'(margins {KASTEN_RAND} {KASTEN_RAND} {KASTEN_RAND} {KASTEN_RAND}) '
                 f'(stroke (width 0.1) (type solid) (color 132 132 132 1)) (fill (type color) (color 255 255 230 1)) '
                 f'(effects (font (size {g} {g})) (justify left top)) (uuid "{kennung}"))\n')
    for a, c in b.striche:
        (x0, y0), (x1, y1) = v(a), v(c)
        t.append(f'\t(polyline (pts (xy {x0} {y0}) (xy {x1} {y1})) (stroke (width 0.4) (type dash_dot) '
                 f'(color 194 0 0 1)) (uuid "{u()}"))\n')
    for seite, bl in enumerate(b.blaetter, 2):
        k: Blatt = bl["kind"]
        x, y, br, h = bl["x"] + ox, bl["y"] + oy, bl["b"], bl["h"]
        s = (f'\t(sheet (at {rd(x)} {rd(y)}) (size {rd(br)} {rd(h)}) (exclude_from_sim no) (in_bom yes) (on_board yes) '
             f'(dnp no) (fields_autoplaced yes)\n\t\t(stroke (width 0.1524) (type solid))\n'
             f'\t\t(fill (color 0 0 0 0.0000))\n\t\t(uuid "{k.uuid}")\n'
             f'\t\t(property "Sheetname" "{k.name}" (at {rd(x)} {rd(y - 0.71)} 0) (effects (font (size 1.524 1.524) bold) '
             f'(justify left bottom)))\n'
             f'\t\t(property "Sheetfile" "{k.datei}" (at {rd(x)} {rd(y + h + 0.6)} 0) (effects (font (size 1.27 1.27)) '
             f'(justify left top)))\n')
        for name, seite_, dy in bl["pins"]:
            px = x if seite_ == "l" else x + br
            s += (f'\t\t(pin "{name}" bidirectional (at {rd(px)} {rd(y + dy)} {180 if seite_ == "l" else 0}) '
                  f'(uuid "{u()}") (effects (font (size 1.27 1.27)) (justify {"left" if seite_ == "l" else "right"})))\n')
        s += (f'\t\t(instances\n\t\t\t(project "{projekt}"\n\t\t\t\t(path "/{b.uuid}" (page "{seite}"))\n'
              f'\t\t\t)\n\t\t)\n\t)\n')
        t.append(s)

    titel = b.titel or b.name
    kom = "".join(f'\t\t(comment {i} "{c}")\n' for i, c in enumerate(b.kommentare, 1))
    kopf = (f'(kicad_sch\n\t(version 20250114)\n\t(generator "sopho2sip")\n\t(generator_version "3.0")\n'
            f'\t(uuid "{b.uuid}")\n\t(paper "{b.papier}")\n'
            f'\t(title_block\n\t\t(title "{titel}")\n\t\t(rev "0.2")\n\t\t(company "Sopho2SIP")\n{kom}\t)\n\t(lib_symbols\n')
    libteil = "".join("\t\t" + s.replace("\n", "\n\t\t") + "\n" for s in b.libs.values())
    fuss = '\t(sheet_instances\n\t\t(path "/" (page "1"))\n\t)\n' if wurzel is None else ""
    return kopf + libteil + "\t)\n" + "".join(t) + fuss + '\t(embedded_fonts no)\n)\n'


def schreibe_projekt(verzeichnis: pathlib.Path, projekt: str, wurzel: Blatt,
                    verwerfen: set[str] | None = None) -> pathlib.Path:
    """Wurzelblatt und alle Kindblätter schreiben (mit Handlagen, siehe Kopf); liefert den Pfad des Wurzelblatts."""
    verzeichnis.mkdir(parents=True, exist_ok=True)
    verwerfen = _verwerfen_aus_argv() if verwerfen is None else verwerfen
    blaetter = [(wurzel, f"{projekt}.kicad_sch", schreibe_blatt(wurzel, projekt, f"/{wurzel.uuid}"))]
    for bl in wurzel.blaetter:
        k: Blatt = bl["kind"]
        blaetter.append((k, k.datei, schreibe_blatt(k, projekt, f"/{wurzel.uuid}/{k.uuid}", wurzel)))
    texte, stand = _handlagen(verzeichnis, projekt, blaetter, verwerfen)
    for datei, text in texte.items():
        (verzeichnis / datei).write_text(text, encoding="utf-8")
    (verzeichnis / STAND).write_text(json.dumps(stand, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                                     encoding="utf-8")
    schreibe_bibliothek(verzeichnis)
    schreibe_fp_tabelle(verzeichnis)
    # vorhandene Einstellungen (z. B. Netzklassen und Regeln aus dem Layout-Generator) behalten
    pro = verzeichnis / f"{projekt}.kicad_pro"
    daten = json.loads(pro.read_text(encoding="utf-8")) if pro.exists() else {}
    daten.setdefault("meta", {"filename": f"{projekt}.kicad_pro", "version": 1})   # pflegt KiCad selbst
    daten.setdefault("sheets", [[b.uuid, "Root" if b is wurzel else b.name] for b, _, _ in blaetter])
    pro.write_text(json.dumps(daten, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return verzeichnis / f"{projekt}.kicad_sch"


def schreibe_fp_tabelle(verzeichnis: pathlib.Path) -> None:
    """Projektverweis auf die gemeinsamen eigenen Footprints (hardware/bibliothek/sopho2sip.pretty)."""
    (verzeichnis / "fp-lib-table").write_text(
        '(fp_lib_table\n\t(version 7)\n\t(lib (name "Sopho2SIP") (type "KiCad") '
        '(uri "${KIPRJMOD}/../bibliothek/sopho2sip.pretty") (options "") (descr "Sopho2SIP, eigene Footprints"))\n)\n',
        encoding="utf-8")


def schreibe_bibliothek(verzeichnis: pathlib.Path) -> None:
    """Eigene Symbole als Projektbibliothek (je Bibliotheksname eine .kicad_sym) samt sym-lib-table ablegen."""
    libs: dict[str, list[str]] = {}
    for lib_id, sym in EIGENE_SYMBOLE.items():
        lib, name = lib_id.split(":")
        libs.setdefault(lib, []).append(sym.replace(f'(symbol "{lib_id}"', f'(symbol "{name}"', 1))
    if not libs:
        return
    tabelle = ["(sym_lib_table", "\t(version 7)"]
    for lib, syms in sorted(libs.items()):
        datei = f"{lib.lower()}.kicad_sym"
        (verzeichnis / datei).write_text('(kicad_symbol_lib (version 20241209) (generator "sopho2sip") '
                                         '(generator_version "10.0")\n' + "\n".join(syms) + "\n)\n", encoding="utf-8")
        tabelle.append(f'\t(lib (name "{lib}") (type "KiCad") (uri "${{KIPRJMOD}}/{datei}") (options "") '
                       f'(descr "Sopho2SIP, vom Generator erzeugt"))')
    (verzeichnis / "sym-lib-table").write_text("\n".join(tabelle) + "\n)\n", encoding="utf-8")


# ------------------------------------------------------------------------------------------------------------------
# Handlage: von Hand nachgebesserte Zeichnungen übernehmen
# ------------------------------------------------------------------------------------------------------------------
HANDLAGE = "handlage"            # Unterordner im Projekt: übernommene Blätter (Quelle der Zeichnung)
STAND = ".generiert.json"        # Fingerabdruck der zuletzt geschriebenen Zeichnung je Blatt
_TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')
_QSTR = r'"((?:[^"\\]|\\.)*)"'


def _argument(name: str) -> str | None:
    if name not in sys.argv:
        return None
    i = sys.argv.index(name)
    if i + 1 >= len(sys.argv):
        raise SystemExit(f"{name}: Wert fehlt")
    return sys.argv[i + 1]


def _verwerfen_aus_argv() -> set[str]:
    return {n.strip() for n in (_argument("--handlage-verwerfen") or "").split(",") if n.strip()}


def _escape(s: str) -> str:
    """Text → Inhalt einer KiCad-Zeichenkette."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _entschluesseln(s: str) -> str:
    """Inhalt einer KiCad-Zeichenkette → Text."""
    return re.sub(r"\\(.)", lambda m: "\n" if m.group(1) == "n" else m.group(1), s)


def _sx(text: str):
    """S-Ausdruck → verschachtelte Listen (Zeichenketten ohne Anführungszeichen)."""
    stapel: list[list] = [[]]
    for m in _TOKEN.finditer(text):
        t = m.group(0)
        if t == "(":
            stapel.append([])
        elif t == ")":
            k = stapel.pop()
            stapel[-1].append(k)
        else:
            stapel[-1].append(_entschluesseln(t[1:-1]) if t[0] == '"' else t)
    return stapel[0][0]


def _kinder(text: str, start: int = 0) -> list[tuple[int, int, str]]:
    """Direkte Unterblöcke des Blocks, der bei start beginnt: [(Anfang, Ende, Kopf)]."""
    erg, tiefe, i, anfang, in_str = [], 0, start, 0, False
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            tiefe += 1
            anfang = i if tiefe == 2 else anfang
        elif c == ")":
            if tiefe == 2:
                erg.append((anfang, i + 1, re.match(r"\(([^\s()]+)", text[anfang:anfang + 64]).group(1)))
            tiefe -= 1
            if tiefe == 0:
                break
        i += 1
    return erg


def _unter(t: list, name: str):
    return next((k for k in t[1:] if isinstance(k, list) and k and k[0] == name), None)


def _alle(t: list, name: str) -> list:
    return [k for k in t[1:] if isinstance(k, list) and k and k[0] == name]


def _lage(t: list):
    a = _unter(t, "at")
    return tuple(round(float(v), 2) for v in a[1:]) if a else None


def _xy(t: list, name: str):
    k = _unter(t, name)
    return tuple(round(float(v), 2) for v in k[1:3]) if k else None


def _schrift(t: list) -> tuple:
    """Ausrichtung und Sichtbarkeit (KiCad schreibt hide teils im Feld, teils in effects)."""
    e = _unter(t, "effects") or ["effects"]
    j = _unter(e, "justify")
    h = _unter(t, "hide") or _unter(e, "hide")
    versteckt = "hide" in e[1:] or (h is not None and (len(h) == 1 or h[1] == "yes"))
    return tuple(j[1:]) if j else (), versteckt


def _punkte(t: list) -> tuple:
    pts = _unter(t, "pts") or ["pts"]
    return tuple(tuple(round(float(v), 2) for v in xy[1:3]) for xy in _alle(pts, "xy"))


def _zeichnung(text: str, mit_texten: bool = True) -> list[str]:
    """Alles, was die Zeichnung ausmacht (Lagen, Leitungen, Beschriftungen), ohne UUIDs und Formatierung.
    mit_texten=False: Inhalt von Texten und Textkästen nicht mitzählen, nur ihre Lage."""
    erg = []
    for k in _sx(text)[1:]:
        if not isinstance(k, list):
            continue
        kopf = k[0]
        if kopf == "symbol":
            felder = sorted((p[1], p[2], _lage(p), _schrift(p)) for p in _alle(k, "property")
                            if p[1] in ("Reference", "Value"))
            spiegel = _unter(k, "mirror")
            erg.append((kopf, _unter(k, "lib_id")[1], _lage(k), spiegel[1] if spiegel else "", felder))
        elif kopf in ("wire", "bus", "polyline"):
            erg.append((kopf, tuple(sorted(_punkte(k)))))
        elif kopf in ("junction", "no_connect", "bus_entry"):
            erg.append((kopf, _lage(k)))
        elif kopf in ("label", "hierarchical_label", "global_label"):
            erg.append((kopf, k[1], _lage(k), _schrift(k)))
        elif kopf == "text":
            erg.append((kopf, k[1] if mit_texten else "", _lage(k), _schrift(k)))
        elif kopf == "text_box":
            groesse = _unter(k, "size")
            erg.append((kopf, k[1] if mit_texten else "", _lage(k),
                        tuple(round(float(v), 2) for v in groesse[1:]) if groesse else None))
        elif kopf == "rectangle":
            erg.append((kopf, _xy(k, "start"), _xy(k, "end")))
        elif kopf == "sheet":
            groesse = _unter(k, "size")
            erg.append((kopf, _lage(k), tuple(groesse[1:]) if groesse else None,
                        sorted((p[1], _lage(p)) for p in _alle(k, "pin")),
                        sorted((p[1], _lage(p)) for p in _alle(k, "property"))))
    return sorted(repr(e) for e in erg)


def _fingerabdruck(text: str, mit_texten: bool = True) -> str:
    return hashlib.sha256("\n".join(_zeichnung(text, mit_texten)).encode()).hexdigest()


def _texte(text: str) -> dict[str, str]:
    """Inhalt der Texte und Textkästen eines Blatts nach UUID."""
    erg = {}
    for k in _sx(text)[1:]:
        if isinstance(k, list) and k and k[0] in ("text", "text_box"):
            kennung = _unter(k, "uuid")
            if kennung:
                erg[kennung[1]] = k[1]
    return erg


def _texte_setzen(text: str, inhalte: dict[str, str]) -> str:
    """Inhalt von Texten und Textkästen (nach UUID) ersetzen; Lage und Format bleiben."""
    if not inhalte:
        return text
    stuecke, pos = [], 0
    for a, e, kopf in _kinder(text, text.index("(kicad_sch")):
        if kopf not in ("text", "text_box"):
            continue
        block = text[a:e]
        k = _eigene_uuid(block)
        kennung = re.search(r'"([^"]+)"', block[k[0]:k[1]]).group(1) if k else None
        if kennung in inhalte:
            block = re.sub(r'^\((text|text_box) %s' % _QSTR,
                           lambda m: f'({m.group(1)} "{_escape(inhalte[kennung])}"', block, count=1)
            stuecke += [text[pos:a], block]
            pos = e
    return "".join(stuecke) + text[pos:]


# Argumente, die den Text tragen: text(x, y, s) · notiz(x, y, breite, *absaetze) · rahmen_(x0, y0, x1, y1, titel)
_TEXTARGUMENTE = {"text": slice(2, 3), "notiz": slice(3, None), "rahmen_": slice(4, 5)}


def _literal(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _literale(absaetze: list[str], spalte: int, breite: int = 120) -> str:
    """Python-Literale für die Absätze (durch Komma getrennt); lange Absätze als verkettete Literale über
    mehrere Zeilen, eingerückt auf die Spalte des ersten Literals."""
    platz = max(40, breite - spalte - 3)
    teile = []
    for absatz in absaetze:
        zeilen, z = [], ""
        for wort in absatz.split(" "):
            probe = f"{z} {wort}" if z else wort
            if z and len(probe) + 1 > platz:
                zeilen.append(z + " ")
                z = wort
            else:
                z = probe
        zeilen.append(z)
        teile.append(("\n" + " " * spalte).join(_literal(x) for x in zeilen))
    return (",\n" + " " * spalte).join(teile)


def _rueckfuehren(aenderungen: list[tuple]) -> dict[str, str]:
    """In KiCad geänderte Texte in den Generator-Quelltext schreiben.
    aenderungen: (Kennung, Herkunft (Datei, Zeile, Art), bisheriger Text, neuer Text).
    Ersetzt wird nur, wenn der Aufruf eindeutig ist und seine Literale genau den bisherigen Text ergeben.
    Liefert {Kennung: Grund} für die Texte, die nicht zurückgeführt werden konnten."""
    fehl: dict[str, str] = {}
    nach_datei: dict[str, list] = {}
    for kennung, herkunft, alt, neu in aenderungen:
        if herkunft is None:
            fehl[kennung] = "Herkunft unbekannt"
        else:
            nach_datei.setdefault(herkunft[0], []).append((kennung, herkunft, alt, neu))
    for datei, liste in nach_datei.items():
        quelltext = pathlib.Path(datei).read_text(encoding="utf-8")
        roh = quelltext.encode("utf-8")
        anfang = [0]                                   # Byte-Versatz jeder Zeile (ast zählt Spalten in Bytes)
        for zeile in roh.splitlines(keepends=True):
            anfang.append(anfang[-1] + len(zeile))
        aufrufe = [n for n in ast.walk(ast.parse(quelltext)) if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Attribute) and n.func.attr in _TEXTARGUMENTE]
        ersatz = []
        for kennung, (_, zeile, art), alt, neu in liste:
            ort = f"{pathlib.Path(datei).name}:{zeile}"
            treffer = [n for n in aufrufe if n.func.attr == art and n.lineno <= zeile <= n.end_lineno]
            if len(treffer) != 1:
                fehl[kennung] = f"{ort}: Aufruf nicht eindeutig"
                continue
            args = treffer[0].args[_TEXTARGUMENTE[art]]
            if not args or not all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in args):
                fehl[kennung] = f"{ort}: Text wird im Generator berechnet"
                continue
            if "\n".join(a.value for a in args) != alt:
                fehl[kennung] = f"{ort}: Quelltext ergibt nicht den bisherigen Text"
                continue
            erster, letzter = args[0], args[-1]
            a0 = anfang[erster.lineno - 1]
            spalte = len(roh[a0:a0 + erster.col_offset].decode("utf-8"))
            absaetze = neu.split("\n") if art == "notiz" else [neu]
            # unveränderte Absätze wörtlich übernehmen (kein Umbruch-Rauschen im Diff)
            stuecke = []
            for i, absatz in enumerate(absaetze):
                if i < len(args) and args[i].value == absatz:
                    a = args[i]
                    stuecke.append(roh[anfang[a.lineno - 1] + a.col_offset:
                                       anfang[a.end_lineno - 1] + a.end_col_offset].decode("utf-8"))
                else:
                    stuecke.append(_literale([absatz], spalte))
            code = (",\n" + " " * spalte).join(stuecke)
            ersatz.append((a0 + erster.col_offset, anfang[letzter.end_lineno - 1] + letzter.end_col_offset,
                           code.encode("utf-8"), ort, neu))
        for a, e, code, ort, neu in sorted(ersatz, reverse=True):
            roh = roh[:a] + code + roh[e:]
            print(f"  Text zurückgeführt nach {ort}: „{neu[:70]}{'…' if len(neu) > 70 else ''}“")
        if ersatz:
            ast.parse(roh.decode("utf-8"))             # Quelltext muss gültig bleiben
            pathlib.Path(datei).write_text(roh.decode("utf-8"), encoding="utf-8")
    return fehl


def _eigenschaft_wert(block: str, name: str) -> str | None:
    m = re.search(r'\(property "%s" %s' % (name, _QSTR), block)
    return m.group(1) if m else None


def _eigene_uuid(block: str) -> tuple[int, int] | None:
    """Lage der UUID des Blocks selbst (nicht die seiner Pins)."""
    return next(((a, e) for a, e, kopf in _kinder(block) if kopf == "uuid"), None)


def _teil_angleichen(hand: str, gen: str, ref: str, fehler: list, hinweise: list) -> str:
    """Bauteil der Handlage: Lage behalten, elektrische Angaben und UUID aus dem Generator."""
    lib_h, lib_g = (re.search(r'\(lib_id "([^"]+)"\)', x).group(1) for x in (hand, gen))
    if lib_h != lib_g:
        fehler.append(f"{ref}: Symbol {lib_h} in der Handlage, {lib_g} in SOLL")
        return hand
    for name in ("Value", "Footprint"):
        w_h, w_g = _eigenschaft_wert(hand, name), _eigenschaft_wert(gen, name)
        if w_g is not None and w_h != w_g:
            if name == "Value":
                hinweise.append(f"{ref}: Wert aus SOLL „{w_g}“ (in KiCad „{w_h}“; Werte gehören in den Generator)")
            hand = re.sub(r'(\(property "%s" )%s' % (name, _QSTR), lambda m: m.group(1) + f'"{w_g}"', hand, count=1)
    for name in ("in_bom", "dnp", "exclude_from_sim", "on_board"):
        m = re.search(r"\(%s (yes|no)\)" % name, gen)
        if m:
            hand = re.sub(r"\(%s (yes|no)\)" % name, m.group(0), hand, count=1)
    a_h, a_g = _eigene_uuid(hand), _eigene_uuid(gen)
    if a_h and a_g:
        hand = hand[:a_h[0]] + gen[a_g[0]:a_g[1]] + hand[a_h[1]:]
    return hand


def _aus_handlage(hand: str, gen: str, name: str) -> tuple[str, list[str], list[str]]:
    """Zeichnung aus der Handlage, Symbolbibliothek, Schriftfeld und Bauteilangaben aus dem Generator."""
    fehler, hinweise = [], []
    kg_ = _kinder(gen, gen.index("(kicad_sch"))
    einzeln = {kopf: gen[a:e] for a, e, kopf in kg_ if kopf in ("lib_symbols", "title_block")}
    teile, blaetter = {}, set()
    for a, e, kopf in kg_:
        if kopf == "symbol":
            ref = _eigenschaft_wert(gen[a:e], "Reference")
            if not ref.startswith("#"):
                teile[ref] = gen[a:e]
        elif kopf == "sheet":
            blaetter.add(re.search(r'\(uuid "([^"]+)"\)', gen[a:e]).group(1))
    stuecke, pos, gesehen = [], 0, set()
    for a, e, kopf in _kinder(hand, hand.index("(kicad_sch")):
        block = hand[a:e]
        if kopf in einzeln:
            block = einzeln[kopf]
        elif kopf == "symbol":
            ref = _eigenschaft_wert(block, "Reference")
            if not ref.startswith("#"):
                if ref in teile:
                    block = _teil_angleichen(block, teile[ref], ref, fehler, hinweise)
                    gesehen.add(ref)
                else:
                    fehler.append(f"{ref} steht in der Handlage, aber nicht mehr in SOLL")
        elif kopf == "sheet":
            k = _eigene_uuid(block)
            uid = re.search(r'"([^"]+)"', block[k[0]:k[1]]).group(1) if k else ""
            if uid not in blaetter:
                fehler.append(f"Blattsymbol {uid} gibt es nicht mehr")
            blaetter.discard(uid)
        stuecke += [hand[pos:a], block]
        pos = e
    stuecke.append(hand[pos:])
    fehler += [f"{r} fehlt in der Handlage (neu in SOLL)" for r in sorted(set(teile) - gesehen)]
    fehler += [f"Blattsymbol {u_} fehlt in der Handlage" for u_ in sorted(blaetter)]
    return "".join(stuecke), [f"{name}: {f}" for f in fehler], [f"{name}: {h}" for h in hinweise]


def _handlagen(verzeichnis: pathlib.Path, projekt: str, blaetter: list[tuple[Blatt, str, str]],
               verwerfen: set[str]) -> tuple[dict[str, str], dict]:
    """Endgültige Blatttexte und neuer Stand. Zeichnung vom Generator oder aus der Handlage (neu erkannte
    Handänderungen werden übernommen, wenn die Netzliste stimmt); Texte vom Generator, in KiCad geänderte Texte
    werden in den Generator zurückgeführt. Bricht ab, ohne etwas zu schreiben, wenn eine Handlage nicht passt."""
    ordner = verzeichnis / HANDLAGE
    kopie = _argument("--handlage-aus")
    quelle_dir = pathlib.Path(kopie).expanduser().resolve() if kopie else verzeichnis
    if kopie and not quelle_dir.is_dir():
        raise SystemExit(f"--handlage-aus: {quelle_dir} ist kein Ordner")
    stand_datei = verzeichnis / STAND
    stand = json.loads(stand_datei.read_text(encoding="utf-8")) if stand_datei.exists() else {}
    texte, neu, quelle, fehler, hinweise = {}, [], {}, [], []
    rueck, nur_text, von_hand = [], [], {}
    for b, datei, gen in blaetter:
        st = stand.get(datei)
        st = st if isinstance(st, dict) else {"fingerabdruck": st} if st else {}
        weg = {datei, b.name} & verwerfen
        hand_datei, ziel = ordner / datei, quelle_dir / datei
        if weg and hand_datei.exists():
            hand_datei.unlink()
            print(f"{b.name}: Handlage verworfen, Zeichnung wieder vom Generator")
        hand = hand_datei.read_text(encoding="utf-8") if hand_datei.exists() else None
        gen_texte = {k: v[0] for k, v in b.textquellen.items()}
        von_hand[datei] = {} if weg else {k: v for k, v in st.get("von_hand", {}).items() if k in gen_texte}
        bisher_texte = st.get("texte") or gen_texte

        def jetzt() -> str:             # was ohne neue Handänderung geschrieben würde
            t = _aus_handlage(hand, gen, b.name)[0] if hand else gen
            return _texte_setzen(_texte_setzen(t, gen_texte), von_hand[datei])
        if ziel.exists() and not weg:
            alt = ziel.read_text(encoding="utf-8")
            fa = _fingerabdruck(alt)
            bisher = st.get("fingerabdruck") or _fingerabdruck(jetzt())
            if fa != bisher or (kopie and fa != _fingerabdruck(jetzt())):
                hand_texte = _texte(alt)
                for k, inhalt in hand_texte.items():
                    vorher = von_hand[datei].get(k, bisher_texte.get(k, gen_texte.get(k)))
                    if k in gen_texte and inhalt != vorher:
                        rueck.append((datei, k, b.textquellen[k][1], gen_texte[k], inhalt))
                    elif k not in gen_texte and k not in bisher_texte:
                        hinweise.append(f"{b.name}: neuer Text nur in der Zeichnung, nicht im Generator: „{inhalt[:60]}“")
                for k in sorted(set(gen_texte) - set(hand_texte)):
                    hinweise.append(f"{b.name}: Text in KiCad gelöscht, im Generator noch vorhanden: „{gen_texte[k][:60]}“")
                if _fingerabdruck(alt, False) == _fingerabdruck(jetzt(), False):
                    nur_text.append(b.name)  # Lage unverändert: keine Handlage nötig
                else:
                    hand = alt
                    neu.append((b.name, datei))
        if hand is None:
            ausgabe = gen
        else:
            ausgabe, f, h = _aus_handlage(hand, gen, b.name)
            fehler += f
            hinweise += h
            quelle[datei] = hand
        # Texte gehören dem Generator; von Hand geänderte bleiben, bis sie im Generator stehen
        bleibt = {**von_hand[datei], **{k: t for d, k, _, _, t in rueck if d == datei}}
        texte[datei] = _texte_setzen(_texte_setzen(ausgabe, gen_texte), bleibt)
    if fehler:
        raise SystemExit("Handlage passt nicht zur Schaltung, nichts geschrieben:\n  " + "\n  ".join(fehler)
                         + "\nZeichnung in KiCad nachziehen oder mit --handlage-verwerfen <Blatt> zurücksetzen.")
    if quelle:
        abw = _pruefe_texte(projekt, texte, [b for b, _, _ in blaetter])
        if abw:
            namen = ", ".join(n for n, _ in neu) or "–"
            raise SystemExit(f"Mit Handlage ergibt sich eine andere Netzliste als SOLL (neu von Hand geändert: {namen}); "
                             "nichts geschrieben:\n  " + "\n  ".join(abw)
                             + "\nÄnderung in KiCad korrigieren oder mit --handlage-verwerfen <Blatt> verwerfen.")
    for name, datei in neu:
        ordner.mkdir(exist_ok=True)
        (ordner / datei).write_text(quelle[datei], encoding="utf-8")
        print(f"{name}: Handänderung erkannt, Netzliste wie SOLL → übernommen nach {HANDLAGE}/{datei}")
    for name in nur_text:
        print(f"{name}: nur Texte von Hand geändert")
    for datei in sorted(set(quelle) - {d for _, d in neu}):
        print(f"{datei}: Zeichnung aus {HANDLAGE}/{datei}")
    fehl = _rueckfuehren([(k, herkunft, alt, t) for _, k, herkunft, alt, t in rueck])
    for d, k, herkunft, _, t in rueck:
        if k in fehl:
            von_hand[d][k] = t
            print(f"  Text bleibt von Hand ({fehl[k]}): „{t[:70]}“ – im Generator nachziehen")
    for h in hinweise:
        print(f"  Hinweis {h}")
    stand_neu = {d: {"fingerabdruck": _fingerabdruck(t), "texte": _texte(t), "von_hand": von_hand.get(d, {})}
                 for d, t in texte.items()}
    return texte, stand_neu


def _pruefe_texte(projekt: str, texte: dict[str, str], blaetter: list[Blatt]) -> list[str]:
    """Netzliste der Blatttexte (in einem Zwischenordner) gegen SOLL."""
    with tempfile.TemporaryDirectory() as tmp:
        for datei, text in texte.items():
            (pathlib.Path(tmp) / datei).write_text(text, encoding="utf-8")
        return _netz_abweichungen(pathlib.Path(tmp) / f"{projekt}.kicad_sch", blaetter)


# ------------------------------------------------------------------------------------------------------------------
# Prüfung
# ------------------------------------------------------------------------------------------------------------------
def soll_netze(blaetter: list[Blatt]) -> dict[str, list[str]]:
    """Erwartete Netze als Pin-Gruppen; Schlüssel: global (Power, exportiert) oder Blatt/Netz (lokal)."""
    netze: dict[str, list[str]] = {}
    for b in blaetter:
        for ref, (_, _, _, belegung) in b.soll.items():
            for nr, netz in belegung.items():
                if netz == "NC":
                    continue
                schluessel = netz if (netz in POWER or netz in b.export) else f"{b.name}/{netz}"
                netze.setdefault(schluessel, []).append(f"{ref}.{nr}")
    return {n: sorted(v) for n, v in netze.items()}


def _netz_abweichungen(root: pathlib.Path, blaetter: list[Blatt]) -> list[str]:
    """Netzliste aus KiCad (kicad-cli) gegen SOLL; liefert die Abweichungen als Textzeilen."""
    with tempfile.TemporaryDirectory() as tmp:
        net = pathlib.Path(tmp) / "x.net"
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(net), str(root)],
                       capture_output=True)
        teil = net.read_text()
    teil = teil[teil.index("(nets"):]
    ist = {}
    for blk in re.split(r'\n\t\t\(net\n', teil)[1:]:
        name = re.search(r'\(name "([^"]+)"\)', blk).group(1)
        k = sorted(f"{r}.{pn}" for r, pn in re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', blk)
                   if not r.startswith("#"))
        if k and not name.startswith("unconnected"):
            ist[name] = k
    soll = soll_netze(blaetter)
    ist_gruppen = {frozenset(v): n for n, v in ist.items()}
    abw, gemeldet = [], set()
    for n, v in sorted(soll.items()):
        if ist_gruppen.pop(frozenset(v), None) is None:
            name, pins = max(ist.items(), key=lambda kv: len(set(kv[1]) & set(v)))
            gemeldet.add(name)
            fehlt, mehr = sorted(set(v) - set(pins)), sorted(set(pins) - set(v))
            abw.append(f"ABWEICHUNG {n}: im ähnlichsten KiCad-Netz {name} fehlen {fehlt or '–'}, zusätzlich {mehr or '–'}")
    abw += [f"ZUSÄTZLICHES NETZ in KiCad {n}: {sorted(g)}" for g, n in ist_gruppen.items() if n not in gemeldet]
    return abw


def pruefe_projekt(root: pathlib.Path, blaetter: list[Blatt]) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        erc = pathlib.Path(tmp) / "erc.txt"
        subprocess.run(["kicad-cli", "sch", "erc", "--severity-all", "-o", str(erc), str(root)], capture_output=True)
        bericht = erc.read_text()
    m = re.search(r"ERC messages: (\d+)\s+Errors (\d+)\s+Warnings (\d+)", bericht)
    print(f"ERC: {m.group(0) if m else bericht[:300]}")
    if m and m.group(1) != "0":
        print("\n".join(z for z in bericht.splitlines() if z.startswith("[") or z.startswith("    @")
                        or z.startswith("*****"))[:5000])
    abw = _netz_abweichungen(root, blaetter)
    for z in abw:
        print(f"  {z}")
    print(f"Netzliste: {len(soll_netze(blaetter))} Netze soll, Abweichungen: {len(abw)}")
    return 1 if abw or (m and m.group(1) != "0") else 0

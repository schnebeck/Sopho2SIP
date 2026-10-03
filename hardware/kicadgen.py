# SPDX-License-Identifier: GPL-3.0-or-later
"""Kleiner Schaltplan-Generator für KiCad 9/10 (Sopho2SIP-Hardware).

Ein Schaltplan entsteht aus zwei getrennten Angaben:
  SOLL     – je Bauteil: Symbol, Wert, Footprint, {Pin: Netz}. Das ist die elektrische Wahrheit.
  Zeichnung – Lage der Bauteile, Leitungen, Labels, Rahmen (Methoden von Blatt).
pruefe_projekt() exportiert mit kicad-cli die Netzliste und vergleicht ihre Pin-Gruppen mit SOLL – über
hierarchische Blätter hinweg. Eine Zeichnung kann also umgestaltet werden, ohne unbemerkt Verbindungen zu ändern.

Netzarten in SOLL:
  Versorgungsnetze (Schlüssel von POWER)  → global über alle Blätter (Power-Symbole, Wert = Netzname)
  Netze in Blatt.export                   → hierarchisches Label; im Wurzelblatt mit gleichnamigen Blattpins verbunden
  alle anderen                            → lokal im Blatt
"""
from __future__ import annotations

import json
import math
import pathlib
import re
import subprocess
import tempfile
import uuid

LIB = pathlib.Path("/usr/share/kicad/symbols")
POWER = {"GND": "power:GND", "+3V3": "power:+3V3", "+5V": "power:+5V", "+3.3VA": "power:+3.3VA",
         "GNDA": "power:GNDA", "GND_ISO": "power:GND", "+3V3_ISO": "power:+3V3", "VBUS": "power:VBUS"}
EIGENE_SYMBOLE: dict[str, str] = {}          # lib_id → fertiger Symbolblock (z. B. CM4-Stecker)


# ------------------------------------------------------------------------------------------------------------------
# Bibliothek
# ------------------------------------------------------------------------------------------------------------------
def u() -> str:
    return str(uuid.uuid4())


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
        basis = re.sub(r'\(property "%s".*?\n\t\t\)' % re.escape(p.group(1)), lambda _m, s=p.group(0): s, basis,
                       count=1, flags=re.S)
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
        self.uuid = u()
        self.teile: list[tuple] = []          # (ref, lib_id, wert, fp, x, y, rot, spiegel, texte)
        self.pinpos: dict[tuple[str, str], tuple[float, float]] = {}
        self.segmente: list[tuple[tuple[float, float], tuple[float, float]]] = []
        self.labels: list[tuple[str, tuple[float, float], str]] = []
        self.power: list[tuple[str, tuple[float, float], int, bool]] = []
        self.flaggen: list[tuple[float, float]] = []
        self.nc: list[tuple[float, float]] = []
        self.rahmen: list[tuple[float, float, float, float, str]] = []
        self.texte: list[tuple[float, float, str, float]] = []
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
    def rahmen_(self, x0, y0, x1, y1, titel) -> None:
        self.rahmen.append((x0, y0, x1, y1, titel))

    def text(self, x, y, s, groesse=1.27) -> None:
        self.texte.append((x, y, s, groesse))

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
         f'\t\t(in_bom {"no" if ref.startswith("#") else "yes"})\n\t\t(on_board yes)\n'
         f'\t\t(dnp {"yes" if wert == "DNP" else "no"})\n\t\t(uuid "{u()}")\n')
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
    for x0, y0, x1, y1, titel in b.rahmen:
        (x0, y0), (x1, y1) = v((x0, y0)), v((x1, y1))
        t.append(f'\t(rectangle (start {x0} {y0}) (end {x1} {y1}) (stroke (width 0.3) (type dash) (color 72 72 72 1)) '
                 f'(fill (type none)) (uuid "{u()}"))\n')
        t.append(f'\t(text "{titel}" (exclude_from_sim no) (at {rd(x0 + 2)} {rd(y0 + 5)} 0) (effects (font (size 2.2 2.2) bold) '
                 f'(justify left bottom)) (uuid "{u()}"))\n')
    for x, y, s, g in b.texte:
        x, y = v((x, y))
        t.append(f'\t(text "{s}" (exclude_from_sim no) (at {x} {y} 0) (effects (font (size {g} {g}) italic) '
                 f'(justify left bottom)) (uuid "{u()}"))\n')
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


def schreibe_projekt(verzeichnis: pathlib.Path, projekt: str, wurzel: Blatt) -> pathlib.Path:
    """Wurzelblatt und alle Kindblätter schreiben; liefert den Pfad des Wurzelblatts."""
    verzeichnis.mkdir(parents=True, exist_ok=True)
    root = verzeichnis / f"{projekt}.kicad_sch"
    root.write_text(schreibe_blatt(wurzel, projekt, f"/{wurzel.uuid}"), encoding="utf-8")
    blaetter = [[wurzel.uuid, "Root"]]
    for bl in wurzel.blaetter:
        k: Blatt = bl["kind"]
        (verzeichnis / k.datei).write_text(schreibe_blatt(k, projekt, f"/{wurzel.uuid}/{k.uuid}", wurzel),
                                           encoding="utf-8")
        blaetter.append([k.uuid, k.name])
    schreibe_bibliothek(verzeichnis)
    (verzeichnis / f"{projekt}.kicad_pro").write_text(
        json.dumps({"meta": {"filename": f"{projekt}.kicad_pro", "version": 1}, "sheets": blaetter}, indent=2) + "\n",
        encoding="utf-8")
    return root


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


def pruefe_projekt(root: pathlib.Path, blaetter: list[Blatt]) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        erc = pathlib.Path(tmp) / "erc.txt"
        net = pathlib.Path(tmp) / "x.net"
        subprocess.run(["kicad-cli", "sch", "erc", "--severity-all", "-o", str(erc), str(root)], capture_output=True)
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(net), str(root)],
                       capture_output=True)
        bericht = erc.read_text()
        m = re.search(r"ERC messages: (\d+)\s+Errors (\d+)\s+Warnings (\d+)", bericht)
        print(f"ERC: {m.group(0) if m else bericht[:300]}")
        if m and m.group(1) != "0":
            print("\n".join(z for z in bericht.splitlines() if z.startswith("[") or z.startswith("    @")
                            or z.startswith("*****"))[:5000])
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
        abw = []
        for n, v in sorted(soll.items()):
            if ist_gruppen.pop(frozenset(v), None) is None:
                abw.append(n)
                naechstes = max(ist.items(), key=lambda kv: len(set(kv[1]) & set(v)))
                print(f"  ABWEICHUNG {n}:\n    soll {v}\n    ähnlichstes ist-Netz {naechstes[0]}: {naechstes[1]}")
        for g, n in ist_gruppen.items():
            abw.append(n)
            print(f"  ZUSÄTZLICHES NETZ in KiCad {n}: {sorted(g)}")
        print(f"Netzliste: {len(soll)} Netze soll, {len(ist)} ist, Abweichungen: {len(abw)}")
        return 1 if abw or (m and m.group(1) != "0") else 0

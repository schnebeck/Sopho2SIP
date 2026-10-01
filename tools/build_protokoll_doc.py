#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Erzeugt docs/protokoll.html (Protokollspezifikation mit SVG-Grafiken) aus docs/protokoll.tpl.html.

Die Grafiken werden hier als Daten beschrieben und zu Inline-SVG gerendert (nur Standardbibliothek).
Aufruf: tools/build_protokoll_doc.py   → schreibt docs/protokoll.html
"""
import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
TPL = ROOT / "docs" / "protokoll.tpl.html"
OUT = ROOT / "docs" / "protokoll.html"

E = html.escape


def marker_defs(pfx: str) -> str:
    return (f'<defs>'
            f'<marker id="{pfx}-a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" class="d-ah"/></marker>'
            f'<marker id="{pfx}-r" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" class="d-ah-req"/></marker>'
            f'</defs>')


def figure(svg: str, caption: str, wide: bool = False) -> str:
    cls = "fig wide" if wide else "fig"
    return f'<figure class="{cls}"><div class="fig-scroll">{svg}</div><figcaption>{caption}</figcaption></figure>'


# --- Sequenzdiagramm -----------------------------------------------------------------------------------
def sequenz(pfx: str, teilnehmer: list[tuple[str, str]], schritte: list, aria: str, breite: int = 820) -> str:
    """teilnehmer: [(kurz, beschriftung)], schritte:
       ('m', von, nach, hex, name, art)   art: 'evt' Meldung (bestätigt), 'req' Auftrag, 'exp' erwartet
       ('a', text)                         Aktion des Menschen (linke Randspalte)
       ('g', text)                         Zeitsprung/Trenner
    """
    rand = 170                                    # linke Spalte für Aktionen
    n = len(teilnehmer)
    x = {k: rand + 60 + i * ((breite - rand - 120) / max(1, n - 1)) for i, (k, _) in enumerate(teilnehmer)}
    kopf, zeile = 64, 38
    y = kopf + 18
    teile = []
    for s in schritte:
        if s[0] == "m":
            von, nach, hx, name, art = s[1:]
            x1, x2 = x[von], x[nach]
            rechts = x2 > x1
            mk = f"{pfx}-r" if art == "req" else f"{pfx}-a"
            linie = "d-req" if art == "req" else "d-evt"
            if art == "exp":
                linie += " d-exp"
            ende = x2 - (4 if rechts else -4)
            teile.append(f'<line x1="{x1:.0f}" y1="{y + 14}" x2="{ende:.0f}" y2="{y + 14}" class="{linie}" marker-end="url(#{mk})"/>')
            mitte = (x1 + x2) / 2
            teile.append(f'<text x="{mitte:.0f}" y="{y + 8}" text-anchor="middle" class="d-mono">{E(hx)}</text>')
            teile.append(f'<text x="{mitte:.0f}" y="{y + 29}" text-anchor="middle" class="d-lbl">{E(name)}</text>')
            y += zeile
        elif s[0] == "a":
            teile.append(f'<rect x="8" y="{y + 2}" width="{rand - 24}" height="24" rx="3" class="d-act"/>')
            teile.append(f'<text x="{8 + (rand - 24) / 2:.0f}" y="{y + 18}" text-anchor="middle" class="d-actt">{E(s[1])}</text>')
            y += 30
        elif s[0] == "g":
            teile.append(f'<line x1="{rand}" y1="{y + 10}" x2="{breite - 10}" y2="{y + 10}" class="d-gap"/>')
            teile.append(f'<text x="{(rand + breite) / 2:.0f}" y="{y + 14}" text-anchor="middle" class="d-gapt">{E(s[1])}</text>')
            y += 26
    hoehe = y + 16
    kopfzeilen = []
    for k, label in teilnehmer:
        kopfzeilen.append(f'<rect x="{x[k] - 70:.0f}" y="12" width="140" height="34" rx="4" class="d-box"/>')
        kopfzeilen.append(f'<text x="{x[k]:.0f}" y="34" text-anchor="middle" class="d-head">{E(label)}</text>')
        kopfzeilen.append(f'<line x1="{x[k]:.0f}" y1="46" x2="{x[k]:.0f}" y2="{hoehe - 6}" class="d-life"/>')
    kopfzeilen.append(f'<text x="8" y="34" class="d-colh">Handlung am Telefon</text>')
    return (f'<svg viewBox="0 0 {breite} {hoehe}" role="img" aria-label="{E(aria)}" class="diagram">'
            f'{marker_defs(pfx)}{"".join(kopfzeilen)}{"".join(teile)}</svg>')


# --- Rahmenaufbau --------------------------------------------------------------------------------------
def rahmenbild() -> str:
    felder = [("Klasse", "1 Byte", "k"), ("Länge L", "1 Byte", "l"), ("Typ", "Byte 0", "t"),
              ("Leitung", "Byte 1", "t"), ("Daten", "Byte 2 … L−1", "d")]
    breiten = [110, 110, 110, 110, 300]
    x0, y0, h = 20, 34, 46
    teile, x = [], x0
    for (name, sub, art), w in zip(felder, breiten):
        teile.append(f'<rect x="{x}" y="{y0}" width="{w}" height="{h}" class="d-cell d-cell-{art}"/>')
        teile.append(f'<text x="{x + w / 2}" y="{y0 + 20}" text-anchor="middle" class="d-head">{E(name)}</text>')
        teile.append(f'<text x="{x + w / 2}" y="{y0 + 37}" text-anchor="middle" class="d-lbl">{E(sub)}</text>')
        x += w
    # Klammer über Nutzdaten
    nx0, nx1 = x0 + 220, x
    teile.append(f'<path d="M{nx0 + 2},{y0 - 6} v-8 H{nx1 - 2} v8" class="d-brace"/>')
    teile.append(f'<text x="{(nx0 + nx1) / 2}" y="{y0 - 18}" text-anchor="middle" class="d-lbl">L Bytes Nutzdaten</text>')
    # Beispiel
    bsp = [("02", "k"), ("05", "l"), ("32", "t"), ("01", "t"), ("98", "d"), ("08", "d"), ("00", "d")]
    y1 = y0 + h + 44
    teile.append(f'<text x="{x0}" y="{y1 - 10}" class="d-colh">Beispiel: Meldung DISCONNECTED, Ursache leer</text>')
    x = x0
    for b, art in bsp:
        teile.append(f'<rect x="{x}" y="{y1}" width="54" height="34" class="d-cell d-cell-{art}"/>')
        teile.append(f'<text x="{x + 27}" y="{y1 + 22}" text-anchor="middle" class="d-mono d-big">{b}</text>')
        x += 54
    erkl = [("02 = Meldung vom Telefon", 0), ("5 Bytes folgen", 1), ("Typ 32 DISCONNECTED", 2),
            ("Leitung 01", 3), ("[98] · IE 08 Ursache, Länge 0", 4)]
    for text, i in erkl:
        cx = x0 + 27 + i * 54
        ty = y1 + 56 + i * 16
        teile.append(f'<line x1="{cx}" y1="{y1 + 36}" x2="{cx}" y2="{ty - 4}" class="d-tick"/>')
        teile.append(f'<line x1="{cx}" y1="{ty - 4}" x2="{x0 + 5 * 54 + 16}" y2="{ty - 4}" class="d-tick"/>')
        teile.append(f'<text x="{x0 + 5 * 54 + 22}" y="{ty}" class="d-lbl">{E(text)}</text>')
    return (f'<svg viewBox="0 0 780 {y1 + 140}" role="img" class="diagram" '
            f'aria-label="Rahmenaufbau: Klasse, Länge, dann Länge Bytes Nutzdaten mit Typ, Leitung und Daten; '
            f'Beispiel 02 05 32 01 98 08 00">{"".join(teile)}</svg>')


# --- Systemüberblick -----------------------------------------------------------------------------------
def architektur() -> str:
    pfx = "ar"
    boxen = [("Sopho iS3000", "Anlage, unverändert", 20, 60), ("ErgoLine D340", "Leitungsmodem", 230, 60),
             ("Gateway-Daemon", "Raspberry Pi", 470, 60), ("SIP-Server", "Nextcloud-App, Softphones", 690, 60),
             ("UCA222", "USB-Audio", 470, 190)]
    t = [marker_defs(pfx)]
    for name, sub, x, y in boxen:
        t.append(f'<rect x="{x}" y="{y}" width="170" height="56" rx="5" class="d-box"/>')
        t.append(f'<text x="{x + 85}" y="{y + 24}" text-anchor="middle" class="d-head">{E(name)}</text>')
        t.append(f'<text x="{x + 85}" y="{y + 42}" text-anchor="middle" class="d-lbl">{E(sub)}</text>')

    def pfeil(x1, y1, x2, y2, oben, unten="", req=False, beide=True):
        cls = "d-req" if req else "d-evt"
        mk = f"{pfx}-r" if req else f"{pfx}-a"
        start = f' marker-start="url(#{mk})"' if beide else ""
        t.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="{cls}" marker-end="url(#{mk})"{start}/>')
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        if oben:
            t.append(f'<text x="{mx}" y="{my - 8}" text-anchor="middle" class="d-lbl">{E(oben)}</text>')
        if unten:
            t.append(f'<text x="{mx}" y="{my + 17}" text-anchor="middle" class="d-mono">{E(unten)}</text>')

    pfeil(194, 88, 226, 88, "UPN")
    pfeil(404, 88, 466, 88, "DB9 seriell", "1200 8O1", req=True)
    pfeil(644, 88, 686, 88, "SIP")
    # Audio: D340 -> UCA222 -> Daemon
    t.append(f'<polyline points="315,120 315,218 466,218" class="d-evt" fill="none" marker-end="url(#{pfx}-a)" marker-start="url(#{pfx}-a)"/>')
    t.append(f'<text x="390" y="210" text-anchor="middle" class="d-lbl">X_OUT / X_IN</text>')
    t.append(f'<text x="330" y="160" class="d-lbl">Audio-Buchse</text>')
    t.append(f'<line x1="555" y1="186" x2="555" y2="120" class="d-evt" marker-end="url(#{pfx}-a)" marker-start="url(#{pfx}-a)"/>')
    t.append(f'<text x="563" y="158" class="d-lbl">ALSA</text>')
    t.append(f'<rect x="466" y="4" width="178" height="40" rx="4" class="d-focus"/>')
    t.append(f'<text x="555" y="28" text-anchor="middle" class="d-lbl">Diese Spezifikation</text>')
    return (f'<svg viewBox="0 0 880 262" role="img" class="diagram" aria-label="Systemüberblick: Anlage über UPN an '
            f'die D340, D340 seriell mit 1200 8O1 und über die Audio-Buchse an den Gateway-Daemon, Daemon per SIP an '
            f'SIP-Server und Nextcloud-App">{"".join(t)}</svg>')


# --- Zustandsautomat -----------------------------------------------------------------------------------
def zustaende() -> str:
    pfx = "za"
    knoten = {"RUHE": (80, 170), "KLINGELT": (330, 60), "WÄHLTON": (250, 280), "WAHL": (430, 280),
              "RUFT": (610, 280), "VERBUNDEN": (760, 170), "AUSGELÖST": (760, 400)}
    t = [marker_defs(pfx)]
    bw, bh = 128, 40

    def kante(a, b, text, req=False, dx=0, dy=-8, anker="middle"):
        (x1, y1), (x2, y2) = knoten[a], knoten[b]
        # Randpunkte der Boxen annähern
        import math
        vx, vy = x2 - x1, y2 - y1
        d = math.hypot(vx, vy)
        ux, uy = vx / d, vy / d
        def rand(ux, uy):
            tx = (bw / 2) / abs(ux) if ux else 1e9
            ty = (bh / 2) / abs(uy) if uy else 1e9
            return min(tx, ty)
        r1, r2 = rand(ux, uy), rand(ux, uy)
        sx, sy = x1 + ux * (r1 + 3), y1 + uy * (r1 + 3)
        ex, ey = x2 - ux * (r2 + 6), y2 - uy * (r2 + 6)
        cls, mk = ("d-req", f"{pfx}-r") if req else ("d-evt", f"{pfx}-a")
        t.append(f'<line x1="{sx:.0f}" y1="{sy:.0f}" x2="{ex:.0f}" y2="{ey:.0f}" class="{cls}" marker-end="url(#{mk})"/>')
        mx, my = (sx + ex) / 2 + dx, (sy + ey) / 2 + dy
        t.append(f'<text x="{mx:.0f}" y="{my:.0f}" text-anchor="{anker}" class="d-mono">{E(text)}</text>')

    kante("RUHE", "KLINGELT", "30 RINGING", dx=-10, dy=-6, anker="end")
    kante("KLINGELT", "VERBUNDEN", "31 CONNECTED", dx=18, dy=-4, anker="start")
    kante("RUHE", "WÄHLTON", "36 DIALTONE", dx=-8, dy=4, anker="end")
    kante("WÄHLTON", "WAHL", "19 MORE_INFO", dy=-10)
    kante("WAHL", "RUFT", "3e PROCEEDING", dy=-10)
    kante("RUFT", "VERBUNDEN", "31 CONNECTED", dx=14, dy=10, anker="start")
    kante("VERBUNDEN", "AUSGELÖST", "32 DISCONNECTED", dx=10, anker="start")
    # Rückweg AUSGELÖST -> RUHE
    x1, y1 = knoten["AUSGELÖST"]
    rx, ry = knoten["RUHE"]
    t.append(f'<polyline points="{x1 - bw / 2 - 3},{y1} {rx},{y1} {rx},{ry + bh / 2 + 6}" class="d-evt" fill="none" marker-end="url(#{pfx}-a)"/>')
    t.append(f'<text x="{(x1 + rx) / 2:.0f}" y="{y1 - 8}" text-anchor="middle" class="d-mono">39 RELEASED</text>')
    t.append(f'<text x="{(x1 + rx) / 2:.0f}" y="{y1 + 18}" text-anchor="middle" class="d-lbl">auch direkt aus KLINGELT, WÄHLTON, WAHL, RUFT</text>')
    # PC-Aufträge als Beschriftung an den Knoten
    auftraege = [("KLINGELT", "Auftrag 14 annehmen", 0, -30), ("RUHE", "Auftrag 11 belegen", 0, 46),
                 ("WÄHLTON", "Auftrag 19 wählen", 0, 46), ("VERBUNDEN", "Auftrag 13 auflegen", 0, -30)]
    for k, txt, dx, dy in auftraege:
        x, y = knoten[k]
        t.append(f'<text x="{x + dx}" y="{y + dy}" text-anchor="middle" class="d-reqt">{E(txt)}</text>')
    for k, (x, y) in knoten.items():
        t.append(f'<rect x="{x - bw / 2}" y="{y - bh / 2}" width="{bw}" height="{bh}" rx="20" class="d-state"/>')
        t.append(f'<text x="{x}" y="{y + 5}" text-anchor="middle" class="d-head">{E(k)}</text>')
    return (f'<svg viewBox="0 0 900 460" role="img" class="diagram" aria-label="Zustandsautomat eines Anrufs: '
            f'Ruhe, klingelt oder Wählton, Wahl, ruft, verbunden, ausgelöst, zurück in Ruhe; Übergänge durch '
            f'Meldungen 30, 36, 19, 3e, 31, 32, 39 und PC-Aufträge 14, 11, 19, 13">{"".join(t)}</svg>')


# --- Abläufe -------------------------------------------------------------------------------------------
TN = [("pc", "PC / Daemon"), ("d", "ErgoLine D340")]

EINGEHEND = [
    ("a", "Anruf trifft ein"),
    ("m", "d", "pc", "02 12 30 01 98 6c 0d 30 31 …", "RINGING · Anrufer „01“ + 01700000000", "evt"),
    ("a", "Hörer abgenommen"),
    ("m", "d", "pc", "02 03 3b 01 0a", "FACILITY_EIN · HÖRER (off hook)", "evt"),
    ("m", "d", "pc", "02 02 31 01", "CONNECTED", "evt"),
    ("m", "d", "pc", "02 03 3b 01 30", "FACILITY_EIN · DTMF", "evt"),
    ("g", "Gespräch, 22 s"),
    ("a", "Hörer aufgelegt"),
    ("m", "d", "pc", "02 03 3a 01 30", "FACILITY_AUS · DTMF", "evt"),
    ("m", "d", "pc", "02 05 32 01 98 08 00", "DISCONNECTED · Ursache leer", "evt"),
    ("m", "d", "pc", "02 05 39 01 98 08 00", "RELEASED", "evt"),
    ("m", "d", "pc", "02 03 3a 01 0a", "FACILITY_AUS · HÖRER (on hook)", "evt"),
]

ABGEHEND = [
    ("a", "abheben, Nummer tippen"),
    ("m", "d", "pc", "02 02 36 01", "DIALTONE (erst bei Wahlende)", "evt"),
    ("m", "d", "pc", "02 03 3b 01 0a", "FACILITY_EIN · HÖRER", "evt"),
    ("m", "d", "pc", "02 12 19 01 98 70 0d 30 31 …", "MORE_INFO · Ziel „01“ + Nummer", "evt"),
    ("m", "d", "pc", "02 02 3e 01", "PROCEEDING (5,8 s später)", "evt"),
    ("a", "Gegenseite nimmt an"),
    ("m", "d", "pc", "02 02 31 01", "CONNECTED", "evt"),
    ("m", "d", "pc", "02 03 3b 01 30", "FACILITY_EIN · DTMF", "evt"),
    ("a", "Gegenseite legt auf"),
    ("m", "d", "pc", "02 06 32 01 98 08 01 8f", "DISCONNECTED · Ursache 8f", "evt"),
    ("m", "d", "pc", "02 03 3a 01 30", "FACILITY_AUS · DTMF", "evt"),
    ("a", "Hörer aufgelegt (8 s)"),
    ("m", "d", "pc", "02 05 39 01 98 08 00", "RELEASED", "evt"),
    ("m", "d", "pc", "02 03 3a 01 0a", "FACILITY_AUS · HÖRER", "evt"),
]

PC_EINGEHEND = [
    ("m", "pc", "d", "01 02 01 00", "ANMELDEN", "req"),
    ("m", "d", "pc", "04 00", "ACK nach 100 ms", "evt"),
    ("m", "d", "pc", "02 04 01 01 02 00", "READY (Bereitmeldung, vermutet)", "evt"),
    ("a", "Anruf trifft ein"),
    ("m", "d", "pc", "02 12 30 01 98 6c …", "RINGING · Anrufer", "evt"),
    ("m", "pc", "d", "01 02 14 00", "ANNEHMEN", "req"),
    ("m", "d", "pc", "04 00", "ACK", "evt"),
    ("m", "d", "pc", "02 03 3b 01 0a · 02 02 31 01", "HÖRER ein (Freisprechen) · CONNECTED", "evt"),
    ("g", "Gespräch, 4 s"),
    ("m", "pc", "d", "01 02 13 00", "AUFLEGEN", "req"),
    ("m", "d", "pc", "04 00", "ACK", "evt"),
    ("m", "d", "pc", "02 05 32 … · 02 05 39 … · 02 03 3a 01 0a", "DISCONNECTED · RELEASED · HÖRER aus", "evt"),
]

PC_WAHL = [
    ("m", "pc", "d", "01 02 11 00", "BELEGEN (nur im Ruhezustand)", "req"),
    ("m", "d", "pc", "04 00", "ACK", "evt"),
    ("m", "d", "pc", "02 03 3b 01 0a", "FACILITY_EIN · HÖRER (kein DIALTONE!)", "evt"),
    ("m", "pc", "d", "01 13 19 00 98 70 0e 81 30 31 …", "WAHL „01“ + 01700000000", "req"),
    ("m", "d", "pc", "04 00", "ACK (nach 360 ms)", "evt"),
    ("m", "d", "pc", "02 12 19 01 98 70 0d 30 31 …", "MORE_INFO · Ziel bestätigt", "evt"),
    ("m", "d", "pc", "02 02 3e 01", "PROCEEDING", "evt"),
    ("a", "Gegenseite nimmt an"),
    ("m", "d", "pc", "02 02 31 01", "CONNECTED", "evt"),
    ("m", "d", "pc", "02 03 3b 01 30", "FACILITY_EIN · DTMF", "evt"),
    ("g", "Gespräch"),
    ("m", "pc", "d", "01 02 13 00", "AUFLEGEN", "req"),
    ("m", "d", "pc", "04 00", "ACK", "evt"),
    ("m", "d", "pc", "3a…30 · 32 · 39 · 3a…0a", "DTMF aus · DISCONNECTED · RELEASED · HÖRER aus", "evt"),
]

FEHLER = [
    ("m", "pc", "d", "unverständliche Bytes", "z. B. Text, falsche Rate", "req"),
    ("g", "≈ 1,5 s Stille"),
    ("m", "d", "pc", "05 00", "ERR (bestätigt)", "evt"),
    ("g", "15 s ohne Empfang"),
    ("m", "pc", "d", "01 02 00 00", "KEEPALIVE", "req"),
    ("m", "d", "pc", "04 00", "ACK (bestätigt)", "evt"),
]

VERPASST = [
    ("a", "Anruf trifft ein"),
    ("m", "d", "pc", "02 12 30 01 98 6c 0d 30 31 …", "RINGING · Anrufer „01“ + 01700000000", "evt"),
    ("g", "klingelt 11 s, niemand nimmt ab"),
    ("a", "Anrufer legt auf"),
    ("m", "d", "pc", "02 06 39 01 98 08 01 8f", "RELEASED · Ursache 8f (Gegenseite)", "evt"),
]


def main() -> None:
    teile = {
        "ARCH": figure(architektur(), "Der Daemon sitzt zwischen der seriellen PC-Schnittstelle der D340 und SIP. "
                       "Diese Spezifikation beschreibt nur die serielle Strecke (Mitte).", wide=True),
        "RAHMEN": figure(rahmenbild(), "Jeder Rahmen beginnt mit Klasse und Länge. Die Länge zählt nur die Nutzdaten; "
                         "es gibt kein Start- oder Endzeichen und keine Prüfsumme."),
        "SEQ_EIN": figure(sequenz("s1", TN, EINGEHEND, "Eingehender Anruf, am Telefon angenommen und aufgelegt: "
                          "Meldungen RINGING, Hörer ab, CONNECTED, DTMF, dann DTMF aus, DISCONNECTED, RELEASED, Hörer auf"),
                          "Eingehender Anruf, am Telefon angenommen und aufgelegt. Mitschnitt "
                          "<code>serial_20260930_163534.log</code>, alle Rahmen bestätigt."),
        "SEQ_VERPASST": figure(sequenz("s6", TN, VERPASST, "Eingehender Anruf, nicht angenommen: auf RINGING folgt "
                               "direkt RELEASED mit Ursache 8f, ohne DISCONNECTED"),
                               "Verpasster Anruf: Legt der Anrufer auf, bevor jemand abnimmt, folgt auf RINGING direkt "
                               "RELEASED mit Ursache <span class=\"hex\">8f</span>, ohne DISCONNECTED und ohne Hörermeldung. "
                               "Bestätigt (<code>logs/test_20261001_130201_pi_angenommen_verpasst.log</code>)."),
        "SEQ_AUS": figure(sequenz("s2", TN, ABGEHEND, "Abgehender Anruf am Telefon gewählt, Gegenseite legt auf"),
                          "Abgehender Anruf, am Telefon gewählt; die Gegenseite legt auf. Abheben und Einzelziffern "
                          "werden nicht gemeldet, die Nummer kommt als Block. Bestätigt."),
        "SEQ_PC_EIN": figure(sequenz("s3", TN, PC_EINGEHEND, "PC meldet sich an, nimmt einen eingehenden Anruf an und legt auf"),
                             "Vom PC gesteuert: anmelden, annehmen, auflegen. Am Gerät erprobt (2026-10-01, "
                             "<code>logs/test_20261001_085744_annehmen_auflegen.log</code>)."),
        "SEQ_PC_WAHL": figure(sequenz("s4", TN, PC_WAHL, "PC belegt die Leitung, wählt extern, Gegenseite nimmt an, PC legt auf"),
                              "Vom PC gesteuert: belegen, wählen, auflegen. Am Gerät erprobt (2026-10-01, "
                              "<code>logs/test_20261001_150042_waehlen_extern.log</code>). Nach dem Belegen meldet das "
                              "Telefon nur „Hörer ab“, keinen Wählton; der Anruf entsteht erst mit MORE_INFO."),
        "SEQ_FEHLER": figure(sequenz("s5", TN, FEHLER, "Unverständliche Eingaben beantwortet das Telefon nach 1,5 s mit 05 00; nach 15 s Stille sendet der PC Keepalive"),
                             "Zeitverhalten: Fehlerantwort und Keepalive."),
        "ZUSTAND": figure(zustaende(), "Zustände eines Anrufs aus Sicht des Daemons. Schwarze Pfeile sind Meldungen "
                          "des Telefons, farbige Beschriftungen die Aufträge, mit denen der Daemon den Übergang auslöst.", wide=True),
    }
    text = TPL.read_text(encoding="utf-8")
    for k, v in teile.items():
        text = text.replace("{{" + k + "}}", v)
    if "{{" in text:
        raise SystemExit("unersetzte Platzhalter in der Vorlage")
    OUT.write_text(text, encoding="utf-8")
    print(f"geschrieben: {OUT} ({len(text) // 1024} KB)")


if __name__ == "__main__":
    main()

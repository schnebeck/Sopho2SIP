#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Erzeugt docs/audio_verkabelung.html (Schaltplan als Inline-SVG, Stil wie docs/protokoll.html).

Aufruf: tools/build_audio_doc.py [ARTIFACT_DATEI]
Mit ARTIFACT_DATEI zusätzlich eine Fassung ohne <html>/<head>/<body>-Gerüst (zum Veröffentlichen als Artifact).
"""
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "audio_verkabelung.html"
ART = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None

s = []
def add(x): s.append(x)
def line(x1, y1, x2, y2, cls): add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="{cls}"/>')
def poly(pts, cls): add(f'<polyline points="{" ".join(f"{x},{y}" for x, y in pts)}" class="{cls}" fill="none"/>')
def text(x, y, t, cls, anchor="start"): add(f'<text x="{x}" y="{y}" text-anchor="{anchor}" class="{cls}">{t}</text>')
def dot(x, y): add(f'<circle cx="{x}" cy="{y}" r="3.2" class="s-dot"/>')
def term(x, y): add(f'<circle cx="{x}" cy="{y}" r="3.6" class="s-term"/>')

def spule(x, y, rechts, cls):
    sweep = 1 if rechts else 0
    d = f"M{x},{y} " + " ".join(f"a9,11 0 0 {sweep} 0,22" for _ in range(4))
    add(f'<path d="{d}" class="{cls}" fill="none"/>')

def masse(x, y):
    line(x, y, x, y + 8, "s-gnd")
    line(x - 11, y + 8, x + 11, y + 8, "s-gnd")
    line(x - 7, y + 12, x + 7, y + 12, "s-gnd")
    line(x - 3, y + 16, x + 3, y + 16, "s-gnd")

def kondensator_h(xm, y, cls):          # im waagerechten Leiter, Platten senkrecht
    line(xm - 4, y - 12, xm - 4, y + 12, "s-plate")
    line(xm + 4, y - 12, xm + 4, y + 12, "s-plate")

def widerstand_h(x1, x2, y):
    add(f'<rect x="{x1}" y="{y - 7}" width="{x2 - x1}" height="14" class="s-cmp"/>')

def widerstand_v(x, y1, y2):
    add(f'<rect x="{x - 7}" y="{y1}" width="14" height="{y2 - y1}" class="s-cmp"/>')

W, H = 1000, 530
# Trennlinie
line(489, 44, 489, 494, "s-bar")
text(489, 34, "galvanische Trennung", "d-colh", "middle")
text(349, 514, "Telefonseite · Bezug GNDA (Pin 3)", "d-lbl", "middle")
text(649, 514, "PC-Seite · Bezug Cinch-Schirm", "d-lbl", "middle")

# D340
add('<rect x="20" y="50" width="190" height="430" rx="6" class="d-box"/>')
text(115, 78, "ErgoLine D340", "d-head", "middle")
text(115, 96, "Audio-Buchse RJ11, 6P6C", "d-lbl", "middle")
pins = [(1, "X_OUT", "Ausgang"), (2, "X_IN", "Eingang"), (3, "GNDA", "Masse"), (4, "n. c.", ""), (5, "n. c.", ""), (6, "n. c.", "")]
for i, (n, name, sub) in enumerate(pins):
    y = 130 + 40 * i
    text(36, y + 4, f"{n}", "d-mono s-pinnr")
    text(58, y + 4, name, "d-head" if n <= 3 else "d-lbl")
    if sub:
        text(120, y + 4, sub, "d-lbl")
    if n <= 3:
        term(210, y)

# Aufnahme: Pin 1 -> C1 -> T1 -> INPUT L
line(210, 130, 326, 130, "s-rec")
kondensator_h(330, 130, "s-rec")
line(334, 130, 470, 130, "s-rec")
text(330, 108, "C1 · 1 µF", "d-mono", "middle")
spule(470, 130, True, "s-rec")
line(481, 128, 481, 220, "s-core"); line(497, 128, 497, 220, "s-core")
spule(508, 130, False, "s-rec")
line(470, 218, 470, 230, "s-gnd"); masse(470, 230)
line(508, 130, 810, 130, "s-rec")
line(508, 218, 810, 218, "s-gnd")
text(489, 110, "T1 · 600 : 600 Ω", "d-mono", "middle")
text(650, 118, "Aufnahme  ·  Telefon → PC", "s-rect", "middle")

# Pin 3 -> Masse
line(210, 210, 240, 210, "s-gnd"); line(240, 210, 240, 226, "s-gnd"); masse(240, 226)
text(240, 262, "GNDA", "d-lbl", "middle")

# Wiedergabe: OUTPUT L -> T2 -> R1/R2 -> C2 -> Pin 2
poly([(210, 170), (270, 170), (270, 370), (306, 370)], "s-play")
kondensator_h(310, 370, "s-play")
line(314, 370, 380, 370, "s-play")
text(310, 346, "C2 · 1 µF", "d-mono", "middle")
widerstand_h(380, 430, 370)
text(405, 392, "R1 · 10 kΩ", "d-mono", "middle")
line(430, 370, 470, 370, "s-play")
dot(360, 370)
line(360, 370, 360, 392, "s-play")
widerstand_v(360, 392, 436)
text(346, 410, "R2 · 1 kΩ", "d-mono", "end")
text(346, 426, "Teiler ≈ −21 dB", "d-lbl", "end")
line(360, 436, 360, 452, "s-gnd"); masse(360, 452)
spule(470, 370, True, "s-play")
line(481, 368, 481, 460, "s-core"); line(497, 368, 497, 460, "s-core")
spule(508, 370, False, "s-play")
line(470, 458, 470, 470, "s-gnd"); masse(470, 470)
line(508, 370, 810, 370, "s-play")
line(508, 458, 810, 458, "s-gnd")
text(489, 350, "T2 · 600 : 600 Ω", "d-mono", "middle")
text(650, 358, "Wiedergabe  ·  PC → Telefon", "s-playt", "middle")

# UCA222
add('<rect x="810" y="50" width="170" height="440" rx="6" class="d-box"/>')
text(895, 78, "Behringer UCA222", "d-head", "middle")
text(895, 96, "USB-Audio, Cinch", "d-lbl", "middle")
for ytop, ybot, name in ((130, 218, "INPUT L"), (370, 458, "OUTPUT L")):
    term(810, ytop); term(810, ybot)
    text(822, ytop + 4, "Mitte", "d-lbl"); text(822, ybot + 4, "Schirm", "d-lbl")
    cy = (ytop + ybot) / 2
    add(f'<circle cx="930" cy="{cy}" r="19" class="s-rca"/><circle cx="930" cy="{cy}" r="6" class="s-rca-pin"/>')
    text(930, cy + 38, name, "d-head", "middle")
    text(930, cy + 54, "weiß (links)", "d-lbl", "middle")
    poly([(862, ytop), (905, ytop), (924, cy - 3)], "s-thin")
    poly([(862, ybot), (905, ybot), (914, cy + 12)], "s-thin")

svg = (f'<svg viewBox="0 0 {W} {H}" role="img" class="diagram" aria-label="Schaltplan: X_OUT über C1 und Übertrager T1 '
       f'an den Eingang der UCA222; Ausgang der UCA222 über Übertrager T2, Spannungsteiler R1/R2 und C2 an X_IN; '
       f'telefonseitig Bezug GNDA, PC-seitig Cinch-Schirm, galvanisch getrennt">{"".join(s)}</svg>')

CSS = (ROOT / "docs" / "protokoll.tpl.html").read_text(encoding="utf-8")
CSS = re.search(r"<style>(.*?)</style>", CSS, re.S).group(1)
CSS = CSS.replace("/* Layout: Datenblatt", "/* Layout wie docs/protokoll.html (Datenblatt)")
CSS = CSS.replace("  --req: #b0470c;            /* Aufträge PC → Telefon */",
                  "  --req: #b0470c;            /* Wiedergabe PC → Telefon */\n  --rec: #0d7a84;            /* Aufnahme Telefon → PC */")
CSS = CSS.replace("--req: #f08a4b; --ok:", "--req: #f08a4b; --rec: #4cc6cf; --ok:")
CSS += """
.s-rec { stroke: var(--rec); stroke-width: 2; fill: none; }
.s-play { stroke: var(--req); stroke-width: 2; fill: none; }
.s-gnd { stroke: var(--fg); stroke-width: 1.5; fill: none; }
.s-thin { stroke: var(--muted); stroke-width: 1; fill: none; }
.s-plate { stroke: var(--fg); stroke-width: 3; }
.s-core { stroke: var(--fg); stroke-width: 2.2; }
.s-cmp { fill: var(--panel); stroke: var(--fg); stroke-width: 1.6; }
.s-bar { stroke: var(--muted); stroke-width: 1.2; stroke-dasharray: 6 5; }
.s-dot { fill: var(--fg); }
.s-term { fill: var(--panel); stroke: var(--fg); stroke-width: 1.5; }
.s-rca { fill: var(--panel); stroke: var(--fg); stroke-width: 2; }
.s-rca-pin { fill: var(--fg); }
.s-pinnr { fill: var(--muted); }
.s-rect { fill: var(--rec); font: 600 12.5px var(--cond); letter-spacing: 0.03em; }
.s-playt { fill: var(--req); font: 600 12.5px var(--cond); letter-spacing: 0.03em; }
.st-w { color: var(--req); }
ol.schritte { max-width: 72ch; padding-left: 1.4em; }
ol.schritte li { margin-bottom: 8px; }
"""

BODY = f"""<div class="wrap">
<header class="kopf">
  <div class="eyebrow">Sopho2SIP · Hardware</div>
  <h1>Audio-Verkabelung D340</h1>
  <p class="lead">Wie die Audio-Buchse der ErgoLine D340 über zwei 600-Ω-Übertrager an die USB-Soundkarte UCA222
  angeschlossen wird: getrennt nach Aufnahme und Wiedergabe, galvanisch entkoppelt und zunächst leise eingespeist.</p>
  <div class="meta">
    <span>Stand <b>2026-10-01</b></span>
    <span>Telefon <b>ErgoLine D340</b></span>
    <span>Soundkarte <b>Behringer UCA222</b></span>
    <span>Übertrager <b>2 × 600 : 600 Ω</b></span>
  </div>
  <div class="legende"><div><span class="st st-v">vorläufig</span>Pegel und Impedanz der Audio-Buchse sind noch nicht gemessen;
  Kondensatoren und Teiler sind vorsichtig gewählt.</div></div>
</header>

<h2 id="schaltplan">Schaltplan</h2>
<figure class="fig wide"><div class="fig-scroll">{svg}</div>
<figcaption>Oben die Aufnahme (Telefon → PC), unten die Wiedergabe (PC → Telefon). Jeder Übertrager trennt die
Telefonseite (Bezug GNDA, Pin 3) von der PC-Seite (Bezug Cinch-Schirm). Das Massezeichen steht immer für GNDA.
GNDA und Cinch-Schirm werden nirgends verbunden.</figcaption></figure>

<h2 id="vorher">Vor dem Anschließen</h2>
<ul class="checks">
<li><b>Richtige Buchse.</b> Unten am Telefon sitzen zwei RJ11-Buchsen. Die „Static Interface“ führt auf Pin 1 +5 V.
An der Audio-Buchse darf zwischen Pin 1 und Pin 3 keine 5 V anliegen.</li>
<li><b>Sechspolig bestückter Stecker (6P6C).</b> Viele RJ11-Kabel sind nur vierpolig bestückt (6P4C); dann fehlen die
äußeren Kontakte 1 und 6 und damit ausgerechnet X_OUT. Belegung mit dem Durchgangsprüfer gegen die Buchse prüfen.</li>
<li><b>Nur der linke Kanal.</b> Je Richtung genügt die weiße (linke) Cinch-Buchse der UCA222; die roten bleiben frei.</li>
</ul>

<h2 id="messen">Messen</h2>
<div class="col"><p>Multimeter auf Gleichspannung, Minus an Pin 3 (GNDA). Die Werte entscheiden, ob C1 und C2 zwingend
nötig sind; eingebaut werden sie in jedem Fall.</p></div>
<div class="tbl"><table>
<thead><tr><th>Messung</th><th>Zustand</th><th>Frage</th><th>Wert</th></tr></thead>
<tbody>
<tr><td>Pin 1 – Pin 3</td><td>Ruhe</td><td>Gleichspannung auf X_OUT?</td><td>–</td></tr>
<tr><td>Pin 2 – Pin 3</td><td>Ruhe</td><td>Vorspannung auf X_IN (wie bei Mikrofon-Eingängen)?</td><td>–</td></tr>
<tr><td>Pin 1 – Pin 3</td><td>Gespräch, „Sprache über Zusatzgerät“ = Ein</td><td>ändert sich etwas, sobald die Buchse aktiv ist?</td><td>–</td></tr>
<tr><td>Pin 2 – Pin 3</td><td>Gespräch, „Sprache über Zusatzgerät“ = Ein</td><td>dito</td><td>–</td></tr>
</tbody></table></div>

<h2 id="teile">Stückliste</h2>
<div class="tbl"><table>
<thead><tr><th>Teil</th><th>Wert</th><th>Hinweis</th></tr></thead>
<tbody>
<tr><td>T1, T2</td><td>NF-Übertrager 600 Ω : 600 Ω</td><td>Polung egal, Mittelanzapfungen frei lassen</td></tr>
<tr><td>C1, C2</td><td>1 µF, ungepolt: Folie (MKT), bipolarer Elko oder Keramik X7R/X5R (z. B. 0805)</td><td>hält Gleichspannung von den Wicklungen fern; ab 10 V genügt. Keramik reicht hier, weil kaum Signalspannung am Kondensator liegt; SMD auf Lochraster/Adapter löten, Kabel zugentlasten</td></tr>
<tr><td>R1</td><td>10 kΩ, ¼ W</td><td>Längswiderstand des Teilers</td></tr>
<tr><td>R2</td><td>1 kΩ, ¼ W</td><td>Querwiderstand des Teilers gegen GNDA; zusammen etwa −21 dB</td></tr>
<tr><td>Stecker</td><td>RJ11 6P6C</td><td>Pin 1–3 belegt</td></tr>
<tr><td>Kabel</td><td>2 × Cinch</td><td>INPUT L und OUTPUT L der UCA222</td></tr>
</tbody></table></div>

<h2 id="reihenfolge">Reihenfolge beim Test</h2>
<ol class="schritte">
<li>Nur die <b>Aufnahme</b> aufbauen (Pin 1 → C1 → T1 → INPUT L). Nichts ins Telefon einspeisen.</li>
<li>Am Telefon „TAPI: Sprache über Zusatzgerät“ einschalten, anrufen lassen, abheben und mit <code>arecord</code> aufnehmen.
Pegel und Klang beurteilen.</li>
<li>Die <b>Wiedergabe</b> mit Teiler anschließen (OUTPUT L → T2 → R1/R2 → C2 → Pin 2). Lautstärke in
<code>alsamixer</code> zunächst niedrig.</li>
<li>Leisen Testton abspielen und die Gegenseite fragen, ob er ankommt. Erst dann lauter stellen oder den Teiler anpassen.</li>
<li>Messwerte und endgültige Werte in <code>docs/hardware.md</code> eintragen.</li>
</ol>

<h2 id="warum">Warum so</h2>
<ul class="checks">
<li><b>Übertrager</b> trennen Telefon und PC im Audioweg. Die einzige leitende Verbindung bleibt die Masse der seriellen
Leitung; Brummschleifen über den Audioweg sind damit ausgeschlossen.</li>
<li><b>Kondensatoren</b>, weil die Wicklungen nur einige Dutzend Ohm Gleichstromwiderstand haben. Ein Gleichanteil an der
Buchse würde den Ausgang belasten und den Kern sättigen. Die Art ist unkritisch: Der Kondensator liegt in Reihe vor
einer Last von über 10 kΩ, sein Blindwiderstand (530 Ω bei 300 Hz) nimmt nur wenige Prozent des Signals weg.</li>
<li><b>Spannungsteiler</b>, weil der zulässige Pegel an X_IN unbekannt ist. Die Soundkarte liefert Line-Pegel; lieber
leise beginnen und dann nachregeln.</li>
<li>Die UCA222 belastet den Übertrager mit einigen Kiloohm. Das Telefon sieht daher eine leichte Last, wie bei einem
Aufnahmegerät, für das die Buchse gedacht ist.</li>
</ul>

<footer>Sopho2SIP · Hardware-Dokumentation · Protokoll der PC-Schnittstelle: <code>docs/protokoll.html</code></footer>
</div>"""

HEAD = f"""<title>Audio-Verkabelung D340</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@500;600;700&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&display=swap">
<style>{CSS}</style>"""

OUT.write_text(f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
{HEAD}
</head>
<body>
{BODY}
</body>
</html>
""", encoding="utf-8")
if ART:
    ART.write_text(HEAD + "\n" + BODY + "\n", encoding="utf-8")
print("geschrieben:", OUT, ART or "")

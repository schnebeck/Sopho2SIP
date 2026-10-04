#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Richtet Hersteller-STEP-Modelle auf die KiCad-Footprints aus und schreibt sie ausgerichtet nach 3d/ausgerichtet/.

  hardware/bibliothek/richte_3d_aus.py

Die Herstellermodelle (3d/*.stp|step) dürfen meist nicht weitergegeben werden und liegen deshalb nicht im Repo
(.gitignore); Bezugsquellen in 3d/QUELLEN.md. Das CM4-Modell lädt das Skript selbst (Raspberry Pi, SHA-256 geprüft).

Verfahren: Die Anschlussenden (Pins/Beinchen) sind die tiefsten Punkte des Modells. Für alle 24 achsparallelen
Drehungen werden diese Punkte mit den Padmitten des Footprints verglichen; die beste Drehung und Verschiebung wird
auf alle Punkte (CARTESIAN_POINT) und Richtungen (DIRECTION) der STEP-Datei angewendet. Ergebnis: Modell in
Footprint-Koordinaten (x rechts, y oben = −y der Platine, z nach oben, Auflagefläche bei z = 0).
"""
from __future__ import annotations

import hashlib
import itertools
import pathlib
import re
import subprocess
import zipfile

import pcbnew

HIER = pathlib.Path(__file__).resolve().parent
QUELLE, ZIEL = HIER / "3d", HIER / "3d" / "ausgerichtet"
KICAD_FP = pathlib.Path("/usr/share/kicad/footprints")

CM4_URL = "https://datasheets.raspberrypi.com/cm4/CM4-step.zip"
CM4_SHA256 = "667649c0728b260ea7ce6b595eb0458f53bd5eef5a3249d3a8b5415de81e23a5"

# Modell → (Footprint-Bibliothek, Footprint, Hochachse im Herstellermodell, Pinlänge unter der Auflage (THT) oder None)
# Hochachse aus den Maßen: RJ45 17 mm entlang x (13,5 + 3,5), RJ12 17,7 mm entlang z, SMD-Teile flach entlang y
MODELLE = {
    "DF40C-100DS.stp": ("Connector_Hirose_DF40", "Hirose_DF40C-100DS-0.4V_2x50_P0.4mm", (0, 1, 0), None),
    "ECS-2520MV-120-BN-TR.step": ("Oscillator", "Oscillator_SMD_ECS_2520MV-xxx-xx-4Pin_2.5x2.0mm", (0, 1, 0), None),
    "SM-LP-5001.STEP": ("Sopho2SIP", "Bourns_SM-LP-5001", (0, 1, 0), None),
}


def _footprint(lib: str, name: str):
    pfad = HIER / "sopho2sip.pretty" if lib == "Sopho2SIP" else KICAD_FP / f"{lib}.pretty"
    return pcbnew.FootprintLoad(str(pfad), name)


def _pads(fp) -> list[tuple[float, float]]:
    """Padmitten in Modellkoordinaten (y nach oben)."""
    return [(pcbnew.ToMM(p.GetPosition().x), -pcbnew.ToMM(p.GetPosition().y)) for p in fp.Pads()
            if p.GetNumber() and p.IsOnCopperLayer()]


def _punkte(text: str) -> tuple[list, list]:
    """(Eckpunkte der Geometrie, alle Punkte inkl. Kreismitten)."""
    s = re.sub(r"\s+", "", text)
    cp = {m.group(1): tuple(map(float, m.group(2, 3, 4)))
          for m in re.finditer(r"#(\d+)=CARTESIAN_POINT\('[^']*',\(([-\d.E+]+),([-\d.E+]+),([-\d.E+]+)\)\)", s)}
    ecken = [cp[m.group(1)] for m in re.finditer(r"=VERTEX_POINT\('[^']*',#(\d+)\)", s) if m.group(1) in cp]
    return ecken, list(cp.values())


def kicad_punkte(lib: str, name: str, modell: pathlib.Path) -> list[tuple[float, float, float]]:
    """Geometrie so, wie KiCad das Modell liest (Baugruppen aufgelöst): Testplatine mit nur diesem Footprint,
    VRML-Export, Punkte in mm im Modellkoordinatensystem."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        b = pcbnew.BOARD()
        fp = _footprint(lib, name)
        fp.SetPosition(pcbnew.VECTOR2I(0, 0))
        fp.Models().clear()
        m = pcbnew.FP_3DMODEL(); m.m_Filename = str(modell)
        fp.Models().push_back(m)
        b.Add(fp)
        for x1, y1, x2, y2 in ((-30, -30, 30, -30), (30, -30, 30, 30), (30, 30, -30, 30), (-30, 30, -30, -30)):
            s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetLayer(pcbnew.Edge_Cuts)
            s.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
            s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
            b.Add(s)
        pcbnew.SaveBoard(f"{tmp}/t.kicad_pcb", b)
        subprocess.run(["kicad-cli", "pcb", "export", "vrml", "--units", "mm", "--models-dir", f"{tmp}/m", "-o",
                        f"{tmp}/t.wrl", f"{tmp}/t.kicad_pcb"], check=True, capture_output=True)
        pts = []
        for w in pathlib.Path(f"{tmp}/m").glob("*.wrl"):
            for blk in re.findall(r"point\s*\[(.*?)\]", w.read_text(encoding="latin-1"), re.S):
                z = [float(v) * 2.54 for v in re.findall(r"[-\d.eE+]+", blk)]   # VRML-Modelle in 0,1 Zoll
                pts += [tuple(z[i:i + 3]) for i in range(0, len(z) - 2, 3)]
        return pts


def kicad_winkel(m) -> list[int]:
    """KiCad-Modellwinkel (x, y, z in Grad) für eine achsparallele Drehmatrix: empirisch aus dem VRML-Export
    bestimmt (alle 64 Kombinationen aus 0/90/180/270°), Ergebnis in 3d/ausgerichtet/winkel.json zwischengespeichert."""
    import json, math, tempfile
    cache = ZIEL / "winkel.json"
    tabelle = json.loads(cache.read_text()) if cache.exists() else {}
    if not tabelle:
        with tempfile.TemporaryDirectory() as tmp:
            for a, b, c in itertools.product((0, 90, 180, 270), repeat=3):
                brett = pcbnew.BOARD()
                fp = _footprint("Oscillator", "Oscillator_SMD_ECS_2520MV-xxx-xx-4Pin_2.5x2.0mm")
                fp.Models().clear()
                mo = pcbnew.FP_3DMODEL(); mo.m_Filename = "${KICAD10_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_1812_4532Metric.step"
                mo.m_Rotation = pcbnew.VECTOR3D(a, b, c); fp.Models().push_back(mo); brett.Add(fp)
                pcbnew.SaveBoard(f"{tmp}/t.kicad_pcb", brett)
                subprocess.run(["kicad-cli", "pcb", "export", "vrml", "--units", "mm", "--models-dir", f"{tmp}/m",
                                "-f", "-o", f"{tmp}/t.wrl", f"{tmp}/t.kicad_pcb"], check=True, capture_output=True)
                r = re.search(r"rotation ([-\d.e]+) ([-\d.e]+) ([-\d.e]+) ([-\d.e]+)",
                              pathlib.Path(f"{tmp}/t.wrl").read_text())
                if r:
                    x, y, z, w = map(float, r.groups())
                    n = math.sqrt(x * x + y * y + z * z) or 1
                    x, y, z = x / n, y / n, z / n
                    co, si, k = math.cos(w), math.sin(w), 1 - math.cos(w)
                    mat = [[co + x * x * k, x * y * k - z * si, x * z * k + y * si],
                           [y * x * k + z * si, co + y * y * k, y * z * k - x * si],
                           [z * x * k - y * si, z * y * k + x * si, co + z * z * k]]
                else:
                    mat = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
                schluessel = json.dumps([[round(v) for v in zeile] for zeile in mat])
                tabelle.setdefault(schluessel, [a, b, c])
        cache.write_text(json.dumps(tabelle, indent=1))
    return tabelle[json.dumps([list(map(int, zeile)) for zeile in m])]


def _drehungen():
    """Alle 24 achsparallelen Drehmatrizen (Determinante +1)."""
    for perm in itertools.permutations(range(3)):
        for vz in itertools.product((1, -1), repeat=3):
            m = [[0] * 3 for _ in range(3)]
            for i in range(3):
                m[i][perm[i]] = vz[i]
            det = (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                   + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
            if det == 1:
                yield m


def _mal(m, p):
    return tuple(sum(m[i][j] * p[j] for j in range(3)) for i in range(3))


def _cluster(punkte, abstand=0.5):
    zentren: list[list[float]] = []
    for x, y in punkte:
        for z in zentren:
            if abs(z[0] / z[2] - x) < abstand and abs(z[1] / z[2] - y) < abstand:
                z[0] += x; z[1] += y; z[2] += 1
                break
        else:
            zentren.append([x, y, 1])
    return [(a / n, b / n) for a, b, n in zentren]


def ausrichtung(ecken, alle, pads, oben, tht):
    """Drehung m (Hochachse → +z, Drehung in der Ebene frei), Verschiebung (tx, ty), tiefstes z, Padabweichung."""
    pxs, pys = [p[0] for p in pads], [p[1] for p in pads]
    pad_mitte = ((min(pxs) + max(pxs)) / 2, (min(pys) + max(pys)) / 2)
    pad_ausdehnung = (max(pxs) - min(pxs), max(pys) - min(pys))
    zmax_e = max(ecken, key=lambda p: sum(o * v for o, v in zip(oben, p)))
    best = None
    for m in _drehungen():
        if _mal(m, oben) != (0, 0, 1):
            continue
        q = [_mal(m, e) for e in ecken]
        zmin = min(p[2] for p in q)
        xs, ys = [p[0] for p in q], [p[1] for p in q]
        if tht:   # Pinbild: Projektion entlang der Hochachse muss das Padbild treffen
            if m[2] not in ([1, 0, 0], [0, 1, 0], [0, 0, 1], [-1, 0, 0], [0, -1, 0], [0, 0, -1]):
                continue
            q = [_mal(m, e) for e in alle]        # alle Punkte: Kreismitten liegen genau auf der Pinachse
            zentren = _cluster([(p[0], p[1]) for p in q], 0.25)
            beste_t = None
            for c in zentren[:400]:
                tx, ty = pads[0][0] - c[0], pads[0][1] - c[1]
                treffer = sum(1 for a, b in pads
                              if any(abs(u[0] + tx - a) < 0.3 and abs(u[1] + ty - b) < 0.3 for u in zentren))
                if beste_t is None or treffer > beste_t[0]:
                    beste_t = (treffer, tx, ty)
            treffer, tx, ty = beste_t
            fehler = len(pads) - treffer + 0.0
        else:     # SMD: Gehäusemitte auf Padmitte, lange Seite wie die Padanordnung
            tx = pad_mitte[0] - (min(xs) + max(xs)) / 2
            ty = pad_mitte[1] - (min(ys) + max(ys)) / 2
            aus = (max(xs) - min(xs), max(ys) - min(ys))
            fehler = abs((aus[0] - aus[1]) - (pad_ausdehnung[0] - pad_ausdehnung[1])) / 10
        if best is None or fehler < best[0] - 1e-6:
            best = (fehler, m, tx, ty, zmin)
    return best


def _bohrungen(fp) -> list[tuple[float, float, float]]:
    """(x, y, Radius) aller Bohrungen (auch Rastzapfen) in Modellkoordinaten."""
    return [(pcbnew.ToMM(p.GetPosition().x), -pcbnew.ToMM(p.GetPosition().y), pcbnew.ToMM(p.GetDrillSize().x) / 2)
            for p in fp.Pads() if p.GetDrillSize().x > 0]


def ausrichtung_tht(punkte, bohrungen, pinlaenge):
    """Alles, was unter die Platine ragt (Pins, Zapfen, Schirmlaschen), muss in einer Bohrung stecken.
    Bewertung je Lage: Punkte unter der Platine in Bohrungen minus 5 × Punkte daneben; Platine liegt pinlaenge
    über dem tiefsten Punkt. Ergebnis: (Fehlerpunkte, m, tx, ty, zmin)."""
    best = None
    groesste = max(bohrungen, key=lambda h: h[2])
    for m in _drehungen():
        q = [_mal(m, p) for p in punkte]
        zmin = min(p[2] for p in q)
        # Schnitt knapp unter der Platine: alle Pins, Zapfen und Laschen gehen hier durch, der Gehäuseboden nicht
        unten = [p for p in q if zmin + pinlaenge - 1.0 < p[2] < zmin + pinlaenge - 0.3]
        if not unten:
            continue
        raster: dict = {}
        for p in unten:
            raster.setdefault((round(p[0] / 0.5), round(p[1] / 0.5)), []).append(p)
        kandidaten = []
        for zellen in sorted(raster.values(), key=len, reverse=True)[:40]:
            cx = sum(p[0] for p in zellen) / len(zellen); cy = sum(p[1] for p in zellen) / len(zellen)
            for hx, hy, _ in bohrungen:
                kandidaten.append((hx - cx, hy - cy))
        for tx, ty in kandidaten:
            drin = draussen = 0
            for p in unten:
                x, y = p[0] + tx, p[1] + ty
                if any((x - hx) ** 2 + (y - hy) ** 2 <= (r + 0.15) ** 2 for hx, hy, r in bohrungen):
                    drin += 1
                else:
                    draussen += 1
            wert = drin - 5 * draussen
            if best is None or wert > best[0]:
                best = (wert, m, tx, ty, zmin, draussen)
    wert, m, tx, ty, zmin, draussen = best
    # Feinabgleich: Schwerpunkt der Punkte je Bohrung auf die Bohrungsmitte
    q = [_mal(m, p) for p in punkte]
    unten = [p for p in q if zmin + pinlaenge - 1.0 < p[2] < zmin + pinlaenge - 0.3]
    for _ in range(3):
        d = []
        for hx, hy, r in bohrungen:
            n = [p for p in unten if (p[0] + tx - hx) ** 2 + (p[1] + ty - hy) ** 2 <= (r + 0.3) ** 2]
            if len(n) > 3:
                d.append((sum(p[0] for p in n) / len(n) + tx - hx, sum(p[1] for p in n) / len(n) + ty - hy))
        if d:
            tx -= sum(v[0] for v in d) / len(d); ty -= sum(v[1] for v in d) / len(d)
    return draussen, m, tx, ty, zmin


def transformiere(text: str, m, t) -> str:
    def punkt(mt):
        p = _mal(m, tuple(float(v) for v in mt.group(2, 3, 4)))
        p = (p[0] + t[0], p[1] + t[1], p[2] + t[2])
        return f"{mt.group(1)}({p[0]:.6f},{p[1]:.6f},{p[2]:.6f})"

    def richtung(mt):
        d = _mal(m, tuple(float(v) for v in mt.group(2, 3, 4)))
        return f"{mt.group(1)}({d[0]:.6f},{d[1]:.6f},{d[2]:.6f})"

    zahl = r"\s*([-\d.E+]+)\s*"
    text = re.sub(r"(CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*)\(%s,%s,%s\)" % (zahl, zahl, zahl), punkt, text)
    return re.sub(r"(DIRECTION\s*\(\s*'[^']*'\s*,\s*)\(%s,%s,%s\)" % (zahl, zahl, zahl), richtung, text)


# Von Hand bestimmt (Rastzapfen Ø 3 mm, Abstand 11,43 mm, im Modell bei x = ±5,71, y = 0,17 entlang z,
# Zapfenwurzel = Auflage bei z = −6,4): keine Drehung, Zapfen auf die Footprint-Zapfen (−1,27|6,35), (10,16|6,35)
# Lage aller Herstellermodelle als KiCad-Modellparameter (Datei bleibt unverändert). Jede Lage ist im Rendering geprüft
# (von unten, vorn, seitlich): Pins/Anschlüsse auf bzw. in den Pads, Körper auf der Platine, Steckseite zur Kante.
#  RJ45: keine Drehung (Kontakte oben, Lasche unten wie „tab down“); Rastzapfen im Modell bei x = −5,6/+5,55,
#        y = 0,1 → auf die Zapfenbohrungen; Pins 3,5 mm unter der Platine.
#  RJ10/RJ12: keine Drehung; Rastzapfen x = ±5,0 bzw. ±6,0, y = −0,5 → auf die Footprint-Zapfen; Gehäuseboden
#        3,0 mm über der Zapfenspitze.
#  Übertrager, Oszillator: Hochachse im Modell = y → 270° um x; Mitte schon auf der Padmitte.
#  DF40: 270° um x und 270° um z; Steckerlänge im Modell außermittig (−17,41…5,18) → 6,115 mm Versatz.
FEST = {
    "7499010211A.stp": ("RJ45_Wuerth_7499010211A_Horizontal", (0, 0, 0), (4.475, -6.47, 7.125)),
    "615004143821.stp": ("RJ10_Wuerth_615004143821_Horizontal", (0, 0, 0), (-1.51, -1.8, 7.7)),
    "615006138421.stp": ("RJ12_Wuerth_615006138421_Horizontal", (0, 0, 0), (-2.55, -4.34, 7.45)),
    "SM-LP-5001.STEP": ("Bourns_SM-LP-5001", (270, 0, 0), (0, 0, 0)),
    "ECS-2520MV-120-BN-TR.step": ("Oscillator_SMD_ECS_2520MV-xxx-xx-4Pin_2.5x2.0mm", (270, 0, 0), (0, 0, 0)),
    "DF40C-100DS.stp": ("Hirose_DF40C-100DS-0.4V_2x50_P0.4mm", (270, 0, 270), (6.115, 0, 0.05)),
}


def cm4() -> None:
    """Offizielles CM4-Modell: Ursprung an die linke obere Modulecke (Draufsicht wie Datenblatt), Unterseite der
    Modulplatine auf z = 1,5 mm (Stapelhöhe DF40C-100DS)."""
    zipdatei = QUELLE / "CM4-step.zip"
    if not zipdatei.exists():
        subprocess.run(["curl", "-sSL", "-o", str(zipdatei), CM4_URL], check=True)
    if hashlib.sha256(zipdatei.read_bytes()).hexdigest() != CM4_SHA256:
        raise SystemExit("CM4-step.zip: Prüfsumme falsch")
    text = zipfile.ZipFile(zipdatei).read("CM4.step").decode("latin-1")
    # im Modell: Platine x 0…55, y 16…56, Unterseite z ≈ 0,01; Antenne bei x = 0, oben (y groß)
    (ZIEL / "CM4.step").write_text(transformiere(text, [[1, 0, 0], [0, 1, 0], [0, 0, 1]], (0.0, -56.0, 1.49)),
                                   encoding="latin-1")
    print("CM4.step: Modulecke links oben = Ursprung, Unterseite 1,5 mm über dem Träger")


def main() -> int:
    ZIEL.mkdir(parents=True, exist_ok=True)
    for datei, (lib, name, oben, sitz) in {}.items():   # automatische Ausrichtung: s. FEST (geprüfte Lagen)
        quelle = QUELLE / datei
        if not quelle.exists():
            print(f"{datei}: fehlt (Bezugsquelle siehe 3d/QUELLEN.md)")
            continue
        text = quelle.read_text(encoding="latin-1")
        if sitz is not None:      # Steckverbinder (meist Baugruppen): KiCad-Sicht, alle Lagen probieren
            fehler, m, tx, ty, zmin = ausrichtung_tht(kicad_punkte(lib, name, quelle), _bohrungen(_footprint(lib, name)),
                                                      sitz)
        else:
            ecken, alle = _punkte(text)
            fehler, m, tx, ty, zmin = ausrichtung(ecken, alle, _pads(_footprint(lib, name)), oben, False)
        tz = -zmin - (sitz or 0.0)               # SMD: Unterkante auf 0; THT: Pinspitze auf −Pinlänge
        if sitz is not None:
            # Baugruppen-STEP nicht umschreiben (Teilkoordinatensysteme): Datei unverändert, Lage als Modellparameter
            import json
            winkel = kicad_winkel(m)
            (ZIEL / f"{name}.step").write_bytes(quelle.read_bytes())
            lage = json.loads((ZIEL / "lage.json").read_text()) if (ZIEL / "lage.json").exists() else {}
            lage[name] = {"rotate": winkel, "offset": [round(tx, 3), round(ty, 3), round(tz, 3)]}
            (ZIEL / "lage.json").write_text(json.dumps(lage, indent=2) + "\n")
            print(f"{datei} → {name}.step  Punkte unter der Platine außerhalb von Bohrungen: {fehler}, Winkel {winkel}, "
                  f"Versatz {lage[name]['offset']}")
            continue
        (ZIEL / f"{name}.step").write_text(transformiere(text, m, (tx, ty, tz)), encoding="latin-1")
        art = "nicht getroffene Pads" if sitz else "Abweichung Gehäuse ↔ Padbild (mm/10)"
        print(f"{datei} → {name}.step  {art}: {fehler:.2f}, Drehung {m}")
    import json
    lage = {}
    for datei, (name, winkel, tr) in FEST.items():
        if (QUELLE / datei).exists():
            (ZIEL / f"{name}.step").write_bytes((QUELLE / datei).read_bytes())
            lage[name] = {"rotate": list(winkel), "offset": list(tr)}
            print(f"{datei} → {name}.step  feste Lage, Winkel {lage[name]['rotate']}, Versatz {list(tr)}")
    (ZIEL / "lage.json").write_text(json.dumps(lage, indent=2) + "\n")
    cm4()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

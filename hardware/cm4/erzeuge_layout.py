#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Erzeugt die Leiterplatte des CM4-Trägers (sopho2sip-cm4.kicad_pcb) aus der KiCad-Netzliste des Schaltplans.

  hardware/cm4/erzeuge_layout.py              → Platzierung, Umriss, Lagen, Flächen, Sperrzonen, Regeln
  hardware/cm4/erzeuge_layout.py --routen     → zusätzlich Differenzpaare und FreeRouting (Specctra DSN/SES)
  hardware/cm4/erzeuge_layout.py --pruefen    → DRC (kicad-cli) mit den JLCPCB-Regeln

Lagen (JLCPCB JLC04161H-7628, 1,6 mm): F.Cu Signale · In1.Cu GND · In2.Cu +3V3 · B.Cu Signale.
Isolierte Bereiche: GND_ISO (RS-232, DE9) und GNDA (Sprechweg, RJ12) mit eigenen Flächen auf allen Lagen;
Trennstreifen ohne Kupfer zwischen den Bereichen. Unter der CM4-Antenne kein Kupfer (Datenblatt: mind. 8 × 15 mm).
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import tempfile

import pcbnew

HIER = pathlib.Path(__file__).resolve().parent
NAME = "sopho2sip-cm4"
KICAD_FP = pathlib.Path("/usr/share/kicad/footprints")
EIGENE_FP = HIER.parent / "bibliothek" / "sopho2sip.pretty"
MM = pcbnew.FromMM

# ------------------------------------------------------------------------------------------------------------------
# Platine: 110 × 85 mm, Ursprung (100, 100); Rückseite (y = 100) mit allen Kabelbuchsen, Front (y = 185) mit µSD,
# LEDs und Tastern. CM4 links, Antenne zur linken Kante.
# ------------------------------------------------------------------------------------------------------------------
X0, Y0, BREITE, TIEFE = 100.0, 100.0, 110.0, 85.0
MX, MY = 101.0, 126.0
# Lage auf dem A4-Blatt (297 × 210 mm): mittig über dem Schriftfeld; konstruiert wird in den Koordinaten oben
BLATT_X, BLATT_Y = 93.0, 45.0                                   # linke obere Ecke des CM4 (Draufsicht wie Datenblatt)

# Bereiche (Polygone im Uhrzeigersinn)
BEREICH_ISO = [(148, 100), (186.5, 100), (186.5, 138.5), (157, 138.5), (157, 123.5), (148, 123.5)]
BEREICH_GNDA = [(187.5, 100), (210, 100), (210, 126), (187.5, 126)]
TRENNSTREIFEN = [  # (x1, y1, x2, y2) Mittellinien der kupferfreien Trennstreifen
    (148, 100, 148, 123.5), (148, 123.5, 157, 123.5), (157, 123.5, 157, 138.5), (157, 138.5, 186.5, 138.5),
    (187.0, 100, 187.0, 138.5), (187.0, 126, 210, 126)]
TRENNBREITE = 1.0
ANTENNE = (100.0, 133.0, 109.5, 148.0)                  # Sperrzone unter der CM4-Antenne (Modul x 0–6,5 / y 9–20)

# 3D-Modelle für Bibliotheks-Footprints ohne Modell (ausgerichtet durch hardware/bibliothek/richte_3d_aus.py)
_M = "${KIPRJMOD}/../bibliothek/3d/ausgerichtet"
MODELL_ERSATZ = {
    "J14": f"{_M}/RJ45_Wuerth_7499010211A_Horizontal.step",
    "J11": f"{_M}/Hirose_DF40C-100DS-0.4V_2x50_P0.4mm.step",
    "U6": f"{_M}/Oscillator_SMD_ECS_2520MV-xxx-xx-4Pin_2.5x2.0mm.step",
    "F1": "${KICAD10_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_1812_4532Metric.step",   # Bauform wie die Polyfuse
}

# Platzierung: Referenz → (x, y, Drehung); alle Bauteile oben
PLATZ = {
    # CM4: Stecker und Bohrungen nach Datenblatt (Mitte Stecker 25,0 / 3,04 bzw. 36,96 mm, Bohrungen 3,5 mm)
    "J11": (MX + 25.0, MY + 3.04, 180), "J12": (MX + 25.0, MY + 36.96, 180),
    "M1": (MX, MY, 0),                                  # CM4 selbst (Platzhalter, 3D-Modell 1,5 mm über J11/J12)
    "H5": (MX + 3.5, MY + 3.5, 0), "H6": (MX + 51.5, MY + 3.5, 0),
    "H7": (MX + 3.5, MY + 36.5, 0), "H8": (MX + 51.5, MY + 36.5, 0),
    "C40": (118.0, 122.5, 0), "C41": (122.5, 123.5, 0),
    # Versorgung / USB-C (hinten links)
    "J10": (108.0, 103.73, 180), "U10": (108.0, 112.5, 0), "R10": (103.0, 111.0, 90), "R11": (103.0, 114.5, 90),
    "F1": (116.5, 110.5, 0), "D12": (116.5, 116.0, 0), "C42": (122.0, 113.5, 90),
    "H1": (103.5, 121.5, 0),
    # Ethernet (hinten, über den Ethernet-Pins des CM4)
    "J14": (137.4, 117.29, 180), "U12": (134.5, 124.2, 0), "C45": (129.0, 123.6, 0),
    "R15": (144.5, 110.0, 90), "R16": (144.5, 114.0, 90),
    # RS-232 isoliert (hinter dem DE9)
    "J3": (161.01, 108.9, 180), "U5": (165.0, 125.5, 0),
    "C35": (159.8, 121.5, 90), "C36": (170.5, 121.0, 90), "C37": (171.0, 125.5, 0), "C38": (171.0, 129.0, 0),
    "C39": (165.0, 118.6, 0), "U3": (171.0, 138.5, 90), "C33": (178.5, 133.5, 90), "C34": (181.5, 133.5, 90),
    "C30": (165.0, 143.5, 90), "C31": (176.5, 143.5, 90), "C32": (179.5, 143.5, 90),
    # Sprechweg (rechts hinten): Telefonseite GNDA oben, Codecseite GND unten
    "J2": (195.45, 110.8, 180), "T1": (192.0, 126.0, 90), "T2": (204.0, 126.0, 90),
    "C21": (193.0, 116.5, 90), "R4": (197.0, 116.5, 90), "C24": (200.0, 116.5, 90), "R5": (203.0, 116.5, 90),
    "C22": (192.0, 136.0, 90), "C23": (204.0, 136.0, 90),
    "H2": (207.0, 140.0, 0),
    # Codec
    "U2": (191.0, 151.0, 0), "U6": (182.5, 146.5, 0), "C27": (182.5, 143.5, 0), "R20": (182.5, 154.5, 90),
    "C12": (186.5, 146.5, 90), "C14": (195.5, 146.0, 90), "C15": (198.0, 146.0, 90), "C16": (201.0, 146.0, 90),
    "C17": (196.0, 154.5, 90), "C18": (186.0, 155.0, 90), "C25": (199.0, 154.5, 90), "C26": (196.0, 151.0, 90),
    "U4": (203.5, 160.0, 0), "C19": (199.0, 160.0, 90), "C20": (207.5, 160.0, 90),
    # µSD (Front links)
    "J13": (110.0, 175.4, 0), "U11": (121.0, 170.0, 0), "C43": (121.0, 173.5, 0), "C44": (124.5, 170.0, 90),
    "R14": (124.5, 173.5, 90), "JP10": (119.73, 181.0, 90),
    # Front: LEDs (für Lichtleiter) und Taster
    "Q10": (135.0, 175.5, 0), "R13": (135.0, 179.5, 0), "D11": (135.0, 183.0, 0),
    "R12": (140.0, 179.5, 0), "D10": (140.0, 183.0, 0),
    "R6": (150.0, 179.5, 0), "D1": (150.0, 183.0, 0), "R7": (155.0, 179.5, 0), "D2": (155.0, 183.0, 0),
    "R8": (160.0, 179.5, 0), "D3": (160.0, 183.0, 0),
    "SW1": (172.0, 180.0, 0), "SW2": (184.0, 180.0, 0), "SW3": (196.0, 180.0, 0), "R9": (196.0, 175.6, 0),
    # Lüfter (Anschluss neben dem CM4; Lüfter sitzt im Deckel über dem Modul)
    "J15": (160.0, 150.5, 0), "D13": (167.5, 150.5, 90), "C46": (170.5, 150.5, 90),
    "Q11": (163.5, 155.5, 0), "R17": (159.5, 159.0, 0), "R18": (163.5, 159.0, 0),
    "H3": (128.5, 181.5, 0), "H4": (206.5, 181.5, 0),
}


# ------------------------------------------------------------------------------------------------------------------
# Netzliste (KiCad, aus dem Schaltplan exportiert)
# ------------------------------------------------------------------------------------------------------------------
def netzliste() -> tuple[dict, dict]:
    with tempfile.TemporaryDirectory() as tmp:
        ziel = pathlib.Path(tmp) / "n.net"
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(ziel),
                        str(HIER / f"{NAME}.kicad_sch")], check=True, capture_output=True)
        s = ziel.read_text(encoding="utf-8")
    teile = {}
    komponenten = s.split("(libparts")[0]
    for block in komponenten.split("(comp\n")[1:] if "(comp\n" in komponenten else re.split(r"\(comp\s", komponenten)[1:]:
        ref = re.search(r'\(ref "([^"]+)"\)', block).group(1)
        wert = re.search(r'\(value "([^"]*)"\)', block).group(1)
        fp = re.search(r'\(footprint "([^"]*)"\)', block).group(1)
        blatt = re.search(r'\(sheetpath\s+\(names "([^"]*)"\)\s+\(tstamps "([^"]*)"\)', block)
        ts = re.search(r'\(tstamps "([^"]+)"\)\s*\)\s*$', block.strip() + ")") or \
            re.findall(r'\(tstamps "([^"]+)"\)', block)
        ts = ts.group(1) if hasattr(ts, "group") else ts[-1]
        name = re.search(r'\(name "Sheetname"\)\s+\(value "([^"]*)"\)', block)
        datei = re.search(r'\(name "Sheetfile"\)\s+\(value "([^"]*)"\)', block)
        teile[ref] = {"wert": wert, "fp": fp, "pfad": blatt.group(2) + ts, "blatt": name.group(1) if name else "",
                      "datei": datei.group(1) if datei else ""}
    netze = {}
    for m in re.finditer(r'\(net\s+\(code "?\d+"?\)\s+\(name "([^"]+)"\)(.*?)\n\t\t\)', s, re.S):
        knoten = re.findall(r'\(node\s+\(ref "([^"]+)"\)\s+\(pin "([^"]+)"\)', m.group(2))
        netze[m.group(1)] = knoten
    return teile, netze


# ------------------------------------------------------------------------------------------------------------------
# Hilfen
# ------------------------------------------------------------------------------------------------------------------
LAGE = {"F.Cu": pcbnew.F_Cu, "In1.Cu": pcbnew.In1_Cu, "In2.Cu": pcbnew.In2_Cu, "B.Cu": pcbnew.B_Cu,
        "F.SilkS": pcbnew.F_SilkS, "B.SilkS": pcbnew.B_SilkS, "Edge.Cuts": pcbnew.Edge_Cuts,
        "F.Fab": pcbnew.F_Fab, "Dwgs.User": pcbnew.Dwgs_User}


def punkt(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(y))


def footprint_laden(fpid: str):
    lib, name = fpid.split(":")
    pfad = EIGENE_FP if lib == "Sopho2SIP" else KICAD_FP / f"{lib}.pretty"
    fp = pcbnew.FootprintLoad(str(pfad), name)
    if fp is None:
        raise SystemExit(f"Footprint fehlt: {fpid}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def polygon(pts):
    kette = pcbnew.SHAPE_LINE_CHAIN()
    for x, y in pts:
        kette.Append(MM(x), MM(y))
    kette.SetClosed(True)
    return kette


def zone(board, netz, lage, pts, prioritaet=0, abstand=0.3, name="", loecher=()):
    z = pcbnew.ZONE(board)
    z.SetLayer(lage)
    z.Outline().AddOutline(polygon(pts))
    for loch in loecher:
        z.Outline().AddHole(polygon(loch), 0)
    if netz:
        z.SetNet(board.FindNet(netz))
    z.SetAssignedPriority(prioritaet)
    z.SetLocalClearance(MM(abstand))
    z.SetMinThickness(MM(0.2))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(MM(0.3))
    z.SetThermalReliefSpokeWidth(MM(0.35))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    if name:
        z.SetZoneName(name)
    board.Add(z)
    return z


def sperrzone(board, pts, name, lagen=("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"), bauteile=False):
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(True)
    z.SetDoNotAllowZoneFills(True)
    z.SetDoNotAllowPads(bauteile)
    z.SetDoNotAllowFootprints(bauteile)
    ls = pcbnew.LSET()
    for l in lagen:
        ls.AddLayer(LAGE[l])
    z.SetLayerSet(ls)
    z.Outline().AddOutline(polygon(pts))
    z.SetZoneName(name)
    board.Add(z)


def streifen(x1, y1, x2, y2, b):
    """Rechteck um eine waagerechte oder senkrechte Mittellinie."""
    h = b / 2
    if x1 == x2:
        return [(x1 - h, min(y1, y2) - h), (x1 + h, min(y1, y2) - h), (x1 + h, max(y1, y2) + h),
                (x1 - h, max(y1, y2) + h)]
    return [(min(x1, x2) - h, y1 - h), (max(x1, x2) + h, y1 - h), (max(x1, x2) + h, y1 + h),
            (min(x1, x2) - h, y1 + h)]


def linie(board, lage, x1, y1, x2, y2, breite=0.15):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(punkt(x1, y1)); s.SetEnd(punkt(x2, y2))
    s.SetLayer(LAGE[lage]); s.SetWidth(MM(breite))
    board.Add(s)


def bogen(board, lage, mx, my, sx, sy, winkel, breite=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_ARC)
    s.SetCenter(punkt(mx, my)); s.SetStart(punkt(sx, sy)); s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(winkel, pcbnew.DEGREES_T))
    s.SetLayer(LAGE[lage]); s.SetWidth(MM(breite))
    board.Add(s)


def text(board, s, x, y, groesse=1.0, lage="F.SilkS", winkel=0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s); t.SetPosition(punkt(x, y)); t.SetLayer(LAGE[lage])
    t.SetTextSize(pcbnew.VECTOR2I(MM(groesse), MM(groesse))); t.SetTextThickness(MM(groesse * 0.15))
    t.SetTextAngleDegrees(winkel)
    board.Add(t)


# ------------------------------------------------------------------------------------------------------------------
# Aufbau
# ------------------------------------------------------------------------------------------------------------------
def umriss(board):
    r = 2.0
    x1, y1, x2, y2 = X0, Y0, X0 + BREITE, Y0 + TIEFE
    for a, b, c, d in ((x1 + r, y1, x2 - r, y1), (x2, y1 + r, x2, y2 - r), (x2 - r, y2, x1 + r, y2),
                       (x1, y2 - r, x1, y1 + r)):
        linie(board, "Edge.Cuts", a, b, c, d, 0.1)
    for mx, my, sx, sy in ((x1 + r, y1 + r, x1, y1 + r), (x2 - r, y1 + r, x2 - r, y1),
                           (x2 - r, y2 - r, x2, y2 - r), (x1 + r, y2 - r, x1 + r, y2)):
        bogen(board, "Edge.Cuts", mx, my, sx, sy, 90)


def lagen(board):
    board.SetCopperLayerCount(4)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(MM(1.6))
    for lid, name, typ in ((pcbnew.In1_Cu, "In1.Cu", pcbnew.LT_POWER), (pcbnew.In2_Cu, "In2.Cu", pcbnew.LT_POWER)):
        board.SetLayerType(lid, typ)


def bestuecken(board, teile, netze):
    pin_netz = {(r, p): n for n, kn in netze.items() for r, p in kn}
    for n in netze:
        board.Add(pcbnew.NETINFO_ITEM(board, n))
    fehlt = sorted(set(teile) - set(PLATZ))
    if fehlt:
        raise SystemExit(f"keine Platzierung für: {fehlt}")
    for ref, t in sorted(teile.items()):
        fp = footprint_laden(t["fp"])
        fp.SetReference(ref); fp.SetValue(t["wert"])
        fp.SetDNP(t["wert"] == "DNP")
        fp.SetPath(pcbnew.KIID_PATH(t["pfad"]))
        fp.SetSheetname(t["blatt"]); fp.SetSheetfile(t["datei"])
        x, y, rot = PLATZ[ref]
        fp.SetPosition(punkt(x, y)); fp.SetOrientationDegrees(rot)
        for pad in fp.Pads():
            netz = pin_netz.get((ref, pad.GetNumber()))
            if netz:
                pad.SetNet(board.FindNet(netz))
                if ref == "J10" and netz == "GND":
                    pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)   # Stifte neben den Rastnasen
        if ref in MODELL_ERSATZ:              # 3D-Modelle, die der KiCad-Bibliothek fehlen
            fp.Models().clear()
            m = pcbnew.FP_3DMODEL(); m.m_Filename = MODELL_ERSATZ[ref]
            lage = HIER.parent / "bibliothek" / "3d" / "ausgerichtet" / "lage.json"
            stamm = pathlib.Path(MODELL_ERSATZ[ref]).stem
            if lage.exists() and stamm in json.loads(lage.read_text()):
                d = json.loads(lage.read_text())[stamm]
                m.m_Rotation = pcbnew.VECTOR3D(*d["rotate"]); m.m_Offset = pcbnew.VECTOR3D(*d["offset"])
            fp.Models().push_back(m)
        # Bestückungsdruck nur mit eigenen Beschriftungen; Referenzen bleiben auf F.Fab (Bestückungsplan)
        fp.Reference().SetLayer(pcbnew.F_Fab)
        board.Add(fp)


def ausrichten(board):
    """Übertrager und ADuM so drehen, dass ihre Telefonseite im isolierten Bereich liegt."""
    fps = {f.GetReference(): f for f in board.GetFootprints()}

    def seite_ok(ref, netze_oben):
        fp = fps[ref]
        oben = [p for p in fp.Pads() if p.GetNetname().split("/")[-1] in netze_oben]
        return all(p.GetPosition().y < fp.GetPosition().y for p in oben)

    for ref, netze_oben in (("T1", {"GNDA", "T1_PRI"}), ("T2", {"GNDA", "T2_SEK"}),
                            ("U3", {"GND_ISO", "+3V3_ISO", "ISO_TXD", "ISO_RXD"})):
        if not seite_ok(ref, netze_oben):
            fps[ref].SetOrientationDegrees(fps[ref].GetOrientationDegrees() + 180)
        if not seite_ok(ref, netze_oben):
            raise SystemExit(f"{ref}: Ausrichtung der isolierten Seite nicht möglich")


RAND = [(X0, Y0), (X0 + BREITE, Y0), (X0 + BREITE, Y0 + TIEFE), (X0, Y0 + TIEFE)]


def _ebenen(board, lagen_netze):
    """Flächen je Lage: Hauptnetz über die ganze Platine mit Aussparungen, darin die isolierten Bereiche
    (überlappungsfrei, damit der Router die Ebenen eindeutig zuordnen kann)."""
    for lage, netz in lagen_netze:
        lid = LAGE[lage]
        zone(board, netz, lid, RAND, 0, 0.3, f"{netz} {lage}", loecher=(BEREICH_ISO, BEREICH_GNDA))
        zone(board, "GND_ISO" if netz != "+3V3" else "+3V3_ISO", lid, BEREICH_ISO, 1, 0.5, f"ISO {lage}")
        zone(board, "GNDA", lid, BEREICH_GNDA, 1, 0.5, f"GNDA {lage}")


def aussenflaechen(board):
    """Masseflächen auf F.Cu/B.Cu – erst nach dem Routing, sonst sperren sie dem Router die Außenlagen."""
    _ebenen(board, (("F.Cu", "GND"), ("B.Cu", "GND")))
    # +5V vom Eingang (F1, C40) breit an die 5-V-Pins des CM4 (77–87, äußere Reihe von J11)
    zone(board, "+5V", pcbnew.F_Cu, [(112.0, 118.5), (123.0, 118.5), (123.0, 128.2), (112.0, 128.2)], 2, 0.2, "+5V CM4")


def flaechen(board):
    _ebenen(board, (("In1.Cu", "GND"), ("In2.Cu", "+3V3")))
    for i, (x1, y1, x2, y2) in enumerate(TRENNSTREIFEN, 1):
        sperrzone(board, streifen(x1, y1, x2, y2, TRENNBREITE), f"Trennung {i}")
    x1, y1, x2, y2 = ANTENNE
    sperrzone(board, [(x1, y1), (x2, y1), (x2, y2), (x1, y2)], "CM4-Antenne", bauteile=True)


def beschriftung(board):
    text(board, "Sopho2SIP · CM4-Träger 0.3", 180.0, 171.0, 1.2)
    text(board, "github.com/schnebeck/Sopho2SIP", 180.0, 173.5, 0.8)
    for s, x, y in (("PWR", 135.0, 181.3), ("ACT", 140.0, 181.3),
                    ("TEL", 150.0, 181.3), ("GESPR", 155.0, 181.3), ("STAT", 160.0, 181.3),
                    ("Annehmen", 172.0, 176.0), ("Konfig", 184.0, 176.0),
                    ("Ein/Aus", 196.0, 173.6), ("Lüfter", 160.5, 147.0), ("nRPIBOOT", 121.0, 178.3),
                    ("ISO RS-232", 177.0, 103.5), ("ISO Audio", 198.0, 114.2)):
        text(board, s, x, y, 0.8)
    for x1, y1, x2, y2 in TRENNSTREIFEN:
        linie(board, "Dwgs.User", x1, y1, x2, y2, 0.15)


# ------------------------------------------------------------------------------------------------------------------
# Regeln (JLCPCB, 4 Lagen, Standard) und Netzklassen in der Projektdatei
# ------------------------------------------------------------------------------------------------------------------
NETZKLASSEN = [
    {"name": "Default", "track_width": 0.127, "clearance": 0.127, "via_diameter": 0.55, "via_drill": 0.3},
    # 0,3 mm passt an die 0,4-mm-Pads der CM4-Stecker; nach dem Routing verbreitert eine +5V-Fläche die Zuleitung
    {"name": "Versorgung", "track_width": 0.3, "clearance": 0.15, "via_diameter": 0.7, "via_drill": 0.4},
    {"name": "ETH", "track_width": 0.2, "clearance": 0.15, "via_diameter": 0.55, "via_drill": 0.3,
     "diff_pair_width": 0.2, "diff_pair_gap": 0.17},
    {"name": "USB", "track_width": 0.22, "clearance": 0.15, "via_diameter": 0.55, "via_drill": 0.3,
     "diff_pair_width": 0.22, "diff_pair_gap": 0.13},
    {"name": "RS232", "track_width": 0.25, "clearance": 0.25, "via_diameter": 0.55, "via_drill": 0.3},
]
NETZMUSTER = [("*ETH_P?_?", "ETH"), ("*USB_?", "USB"), ("+5V", "Versorgung"), ("*VBUS", "Versorgung"),
              ("*RS232_*", "RS232")]


def netzklassen_setzen(board):
    """Netzklassen direkt in der Platine setzen (der DSN-Export für den Router liest sie von dort)."""
    ns = board.GetDesignSettings().m_NetSettings
    for k in NETZKLASSEN:
        nc = ns.GetDefaultNetclass() if k["name"] == "Default" else pcbnew.NETCLASS(k["name"])
        nc.SetTrackWidth(MM(k["track_width"])); nc.SetClearance(MM(k["clearance"]))
        nc.SetViaDiameter(MM(k["via_diameter"])); nc.SetViaDrill(MM(k["via_drill"]))
        if "diff_pair_width" in k:
            nc.SetDiffPairWidth(MM(k["diff_pair_width"])); nc.SetDiffPairGap(MM(k["diff_pair_gap"]))
        if k["name"] != "Default":
            ns.SetNetclass(k["name"], nc)
    for muster, klasse in NETZMUSTER:
        ns.SetNetclassPatternAssignment(muster, klasse)
    ns.RecomputeEffectiveNetclasses()
    board.SynchronizeNetsAndNetClasses(True)


def projekt_regeln():
    pro = HIER / f"{NAME}.kicad_pro"
    d = json.loads(pro.read_text(encoding="utf-8"))
    vorlage = {"bus_width": 12, "clearance": 0.15, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25,
               "diff_pair_width": 0.2, "line_style": 0, "microvia_diameter": 0.3, "microvia_drill": 0.1,
               "pcb_color": "rgba(0, 0, 0, 0.000)", "priority": 2147483647, "schematic_color": "rgba(0, 0, 0, 0.000)",
               "track_width": 0.15, "via_diameter": 0.55, "via_drill": 0.3, "wire_width": 6}
    klassen = []
    for i, k in enumerate(NETZKLASSEN):
        e = dict(vorlage); e.update(k)
        if k["name"] != "Default":
            e["priority"] = i
        klassen.append(e)
    d["net_settings"] = {"classes": klassen, "meta": {"version": 4},
                         "netclass_patterns": [{"netclass": k, "pattern": m} for m, k in NETZMUSTER]}
    d.setdefault("board", {})["design_settings"] = {
        "rules": {"min_clearance": 0.1, "min_track_width": 0.1, "min_via_diameter": 0.45, "min_via_annular_width": 0.1,
                  "min_through_hole_diameter": 0.3, "min_hole_to_hole": 0.5, "min_hole_clearance": 0.2,
                  "min_copper_edge_clearance": 0.3, "min_silk_clearance": 0.0, "min_text_height": 0.8,
                  "min_text_thickness": 0.12, "solder_mask_to_copper_clearance": 0.0,
                  "min_microvia_diameter": 0.2, "min_microvia_drill": 0.1, "max_error": 0.005},
        "defaults": {"board_outline_line_width": 0.1, "copper_line_width": 0.2, "silk_line_width": 0.15,
                     "silk_text_size_h": 1.0, "silk_text_size_v": 1.0, "silk_text_thickness": 0.15},
        "diff_pair_dimensions": [{"gap": 0.17, "via_gap": 0.25, "width": 0.2}, {"gap": 0.13, "via_gap": 0.25, "width": 0.22}],
        "track_widths": [0.15, 0.2, 0.25, 0.5, 0.8], "via_dimensions": [{"diameter": 0.55, "drill": 0.3},
                                                                        {"diameter": 0.7, "drill": 0.4}],
        "rule_severities": {"silk_over_copper": "ignore", "silk_overlap": "warning", "lib_footprint_mismatch": "ignore",
                            "lib_footprint_issues": "ignore", "footprint_type_mismatch": "ignore"}}
    pro.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (HIER / f"{NAME}.kicad_dru").write_text('''(version 1)
# JLCPCB, 4 Lagen, Standardfertigung (https://jlcpcb.com/capabilities/pcb-capabilities), Stand 2026-10
(rule "JLC Bahnbreite" (constraint track_width (min 0.09mm)))
(rule "JLC Abstand" (constraint clearance (min 0.09mm)))
(rule "JLC Restring" (constraint annular_width (min 0.075mm)))
(rule "JLC Bohrung" (constraint hole_size (min 0.15mm)))
(rule "JLC Bohrung zu Bohrung" (constraint hole_to_hole (min 0.25mm)))
(rule "JLC Kupfer zur Kante" (constraint edge_clearance (min 0.3mm)))
# USB-C GCT USB4105: Herstellerlayout, Pads dicht an den Rastnasen (bei JLC so gefertigt)
(rule "USB-C Herstellerlayout" (condition "A.Parent == 'J10' && B.Parent == 'J10'") (constraint hole_clearance (min 0.1mm)))
''', encoding="utf-8")


# ------------------------------------------------------------------------------------------------------------------
# Routing: FreeRouting (Specctra DSN → SES), Java 21; Werkzeug wird bei Bedarf geladen und per SHA-256 geprüft
# ------------------------------------------------------------------------------------------------------------------
# 1.9.0 statt 2.x: ohne Telemetrie, hält die Durchgangszahl ein (2.1 lief ohne Ende weiter), Java 17+
FREEROUTING = HIER.parent / ".werkzeug" / "freerouting-1.9.0.jar"
FREEROUTING_URL = "https://github.com/freerouting/freerouting/releases/download/v1.9.0/freerouting-1.9.0.jar"
FREEROUTING_SHA256 = "9084a4888937a7f31f857ecc12aa7a37407f51160e4d2892dff9c9bb47ae3102"


def freerouting_holen() -> pathlib.Path:
    if not FREEROUTING.exists():
        FREEROUTING.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["curl", "-sSL", "-o", str(FREEROUTING), FREEROUTING_URL], check=True)
    import hashlib
    if hashlib.sha256(FREEROUTING.read_bytes()).hexdigest() != FREEROUTING_SHA256:
        raise SystemExit(f"{FREEROUTING}: Prüfsumme falsch")
    return FREEROUTING


# ------------------------------------------------------------------------------------------------------------------
# Fanout: SMD-Pads der Ebenennetze bekommen je eine kurze Bahn und eine Durchkontaktierung zur Innenlage
# ------------------------------------------------------------------------------------------------------------------
EBENENNETZE = {"GND", "+3V3", "GND_ISO", "+3V3_ISO", "GNDA"}
VIA_D, VIA_BOHR, ABSTAND = 0.55, 0.3, 0.2


def _rechteck(bb, rand=0.0):
    return (pcbnew.ToMM(bb.GetLeft()) - rand, pcbnew.ToMM(bb.GetTop()) - rand,
            pcbnew.ToMM(bb.GetRight()) + rand, pcbnew.ToMM(bb.GetBottom()) + rand)


def _ueberlappt(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def fanout(board) -> tuple[int, list[str]]:
    hind = []                                       # (Rechteck, Netz, ist_via)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.IsOnCopperLayer():
                hind.append((_rechteck(pad.GetBoundingBox()), pad.GetNetname(), False))
    for tr in board.GetTracks():
        hind.append((_rechteck(tr.GetBoundingBox()), tr.GetNetname(), tr.GetClass() == "PCB_VIA"))
    sperr = [streifen(*s, TRENNBREITE) for s in TRENNSTREIFEN] + [[(ANTENNE[0], ANTENNE[1]), (ANTENNE[2], ANTENNE[3])]]
    sperr = [(min(x for x, _ in s), min(y for _, y in s), max(x for x, _ in s), max(y for _, y in s)) for s in sperr]
    rand = (X0 + 0.6, Y0 + 0.6, X0 + BREITE - 0.6, Y0 + TIEFE - 0.6)
    anzahl, fehlt = 0, []
    r = VIA_D / 2
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        fx, fy = pcbnew.ToMM(fp.GetPosition().x), pcbnew.ToMM(fp.GetPosition().y)
        bohrnetze = {p.GetNetname() for p in fp.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH}
        for pad in fp.Pads():
            netz = pad.GetNetname()
            if netz not in EBENENNETZE or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or netz in bohrnetze:
                continue
            px, py = pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)
            x0, y0, x1, y1 = _rechteck(pad.GetBoundingBox())
            hw, hh = (x1 - x0) / 2, (y1 - y0) / 2
            # Richtungen: vom Bauteil weg zuerst, dann quer, zuletzt zum Bauteil hin
            dx, dy = px - fx, py - fy
            weg = [(1 if dx >= 0 else -1, 0), (0, 1 if dy >= 0 else -1)]
            if abs(dy) > abs(dx):
                weg.reverse()
            richtungen = weg + [(-a, -b) for a, b in weg]
            erfolg = False
            kandidaten = [(zusatz, quer, ax, ay) for zusatz in (0.0, 0.3, 0.6, 1.0, 1.5, 2.0, 2.6)
                          for quer in (0.0, 0.4, -0.4, 0.8, -0.8) for ax, ay in richtungen]
            for zusatz, quer, ax, ay in kandidaten:
                if True:
                    ab = (hw if ax else hh) + r + ABSTAND + zusatz
                    vx, vy = px + ax * ab + (quer if ay else 0), py + ay * ab + (quer if ax else 0)
                    via_r = (vx - r - ABSTAND, vy - r - ABSTAND, vx + r + ABSTAND, vy + r + ABSTAND)
                    if not (rand[0] < vx < rand[2] and rand[1] < vy < rand[3]):
                        continue
                    if any(_ueberlappt(via_r, s) for s in sperr):
                        continue
                    # Bahn vom Pad zur Durchkontaktierung (0,2 mm breit) als Rechteck
                    bw = 0.1 + 0.15
                    # Bahn geknickt: erst gerade aus dem Pad heraus, dann seitlich zur Durchkontaktierung
                    kx, ky = (vx, py) if ax else (px, vy)
                    bahn = (min(px, kx) - bw, min(py, ky) - bw, max(px, kx) + bw, max(py, ky) + bw)
                    bahn2 = (min(kx, vx) - bw, min(ky, vy) - bw, max(kx, vx) + bw, max(ky, vy) + bw)
                    if any(n != netz and (_ueberlappt(via_r, h) or _ueberlappt(bahn, h) or _ueberlappt(bahn2, h))
                           for h, n, _ in hind if not (h[0] <= px <= h[2] and h[1] <= py <= h[3] and n == netz)):
                        continue
                    if any(v and _ueberlappt((vx - r - 0.25, vy - r - 0.25, vx + r + 0.25, vy + r + 0.25), h)
                           for h, n, v in hind):
                        continue
                    via = pcbnew.PCB_VIA(board)
                    via.SetPosition(punkt(vx, vy)); via.SetWidth(MM(VIA_D)); via.SetDrill(MM(VIA_BOHR))
                    via.SetNet(pad.GetNet()); via.SetLocked(True)
                    board.Add(via)
                    for (sx, sy), (ex, ey) in (((px, py), (kx, ky)), ((kx, ky), (vx, vy))):
                        if (sx, sy) == (ex, ey):
                            continue
                        bahn_ = pcbnew.PCB_TRACK(board)
                        bahn_.SetStart(punkt(sx, sy)); bahn_.SetEnd(punkt(ex, ey)); bahn_.SetWidth(MM(0.2))
                        bahn_.SetLayer(pcbnew.F_Cu); bahn_.SetNet(pad.GetNet()); bahn_.SetLocked(True)
                        board.Add(bahn_)
                        hind.append(((min(sx, ex) - 0.1, min(sy, ey) - 0.1, max(sx, ex) + 0.1, max(sy, ey) + 0.1),
                                     netz, False))
                    hind.append(((vx - r, vy - r, vx + r, vy + r), netz, True))
                    anzahl += 1
                    erfolg = True
                    break
                if erfolg:
                    break
            if not erfolg:
                fehlt.append(f"{fp.GetReference()}.{pad.GetNumber()}")
    return anzahl, fehlt


def dsn_ohne_ebenennetze(dsn: pathlib.Path) -> None:
    """Ebenennetze aus der Router-Aufgabe nehmen (sie hängen schon über Fanout an den Ebenen)."""
    s = dsn.read_text(encoding="utf-8")
    for netz in EBENENNETZE:
        s = re.sub(r'\n\s*\(net %s\n\s*\(pins[^)]*\)\s*\)' % re.escape(netz), "", s)
    # in den Klassenlisten (über mehrere Zeilen, bis „(circuit“) die Namen entfernen
    def klasse(m):
        teil = m.group(0)
        for netz in EBENENNETZE:
            teil = re.sub(r'(?<=\s)%s(?=[\s)])' % re.escape(netz), "", teil)
        return teil
    s = re.sub(r'\(class .*?\(circuit', klasse, s, flags=re.S)
    dsn.write_text(s, encoding="utf-8")


def routen(ziel: pathlib.Path, durchgaenge: int = 40) -> None:
    board = pcbnew.LoadBoard(str(ziel))
    netzklassen_setzen(board)
    dsn, ses = ziel.with_suffix(".dsn"), ziel.with_suffix(".ses")
    n, fehlt = fanout(board)
    print(f"Fanout: {n} Durchkontaktierungen" + (f", ohne Platz: {', '.join(fehlt)}" if fehlt else ""))
    if not pcbnew.ExportSpecctraDSN(board, str(dsn)):
        raise SystemExit("DSN-Export fehlgeschlagen")
    dsn_ohne_ebenennetze(dsn)
    jar = freerouting_holen()
    # FreeRouting 1.9 braucht eine Oberfläche: unsichtbar über Xvfb (Paket xvfb)
    subprocess.run(["xvfb-run", "-a", "java", "-Xmx6g", "-jar", str(jar), "-de", str(dsn), "-do", str(ses),
                    "-mp", str(durchgaenge), "-mt", "1"], check=True, timeout=3600)
    if not pcbnew.ImportSpecctraSES(board, str(ses)):
        raise SystemExit("SES-Import fehlgeschlagen")
    aussenflaechen(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(ziel), board)
    dsn.unlink(); ses.unlink()


def _beschriftung_entfernen(ziel: pathlib.Path) -> None:
    """Eigene Beschriftung (Texte auf F.Silkscreen, Trennlinien auf Dwgs.User) aus der Datei nehmen; die Python-
    Schnittstelle von KiCad 10 lässt Zeichnungselemente nicht durchlaufen."""
    s = ziel.read_text(encoding="utf-8")
    aus, i = [], 0
    while True:
        j = min((k for k in (s.find("\n\t(gr_text", i), s.find("\n\t(gr_line", i)) if k >= 0), default=-1)
        if j < 0:
            aus.append(s[i:]); break
        tiefe, k = 0, j + 2
        while True:
            if s[k] == "(":
                tiefe += 1
            elif s[k] == ")":
                tiefe -= 1
                if tiefe == 0:
                    break
            k += 1
        block = s[j:k + 1]
        weg = (re.search(r'\(layer "F\.Silk(S|screen)"\)', block) and "gr_text" in block[:12]) or \
              (re.search(r'\(layer "(Dwgs\.User|User\.Drawings)"\)', block) and "gr_line" in block[:12])
        aus.append(s[i:j] if weg else s[i:k + 1])
        i = k + 1
    ziel.write_text("".join(aus), encoding="utf-8")


def _verschieben_nach(board, x, y) -> None:
    bb = board.GetBoardEdgesBoundingBox()
    lx, ly = round(pcbnew.ToMM(bb.GetLeft()) + 0.05, 2), round(pcbnew.ToMM(bb.GetTop()) + 0.05, 2)
    if (lx, ly) != (x, y):
        board.Move(punkt(x - lx, y - ly))


def texte_waagerecht(board) -> None:
    """Alle Bauteiltexte in dieselbe Leserichtung (waagerecht, von unten lesbar)."""
    for fp in board.GetFootprints():
        texte = [fp.Reference(), fp.Value()] + [g for g in fp.GraphicalItems() if g.GetClass() == "PCB_TEXT"]
        for tx in texte:
            tx.SetTextAngleDegrees(0)
            tx.SetKeepUpright(True)


def modelle_erneuern(board) -> None:
    """3D-Modelle aus der Bibliothek bzw. MODELL_ERSATZ übernehmen (ohne Platzierung oder Routing zu ändern)."""
    lage_d = HIER.parent / "bibliothek" / "3d" / "ausgerichtet" / "lage.json"
    lage = json.loads(lage_d.read_text()) if lage_d.exists() else {}
    for fp in board.GetFootprints():
        ref, fpid = fp.GetReference(), fp.GetFPID()
        quelle = None
        if str(fpid.GetLibNickname()) == "Sopho2SIP":
            quelle = footprint_laden(f"Sopho2SIP:{fpid.GetLibItemName()}")
        if quelle is None and ref not in MODELL_ERSATZ:
            continue
        fp.Models().clear()
        if ref in MODELL_ERSATZ:
            m = pcbnew.FP_3DMODEL(); m.m_Filename = MODELL_ERSATZ[ref]
            d = lage.get(pathlib.Path(MODELL_ERSATZ[ref]).stem)
            if d:
                m.m_Rotation = pcbnew.VECTOR3D(*d["rotate"]); m.m_Offset = pcbnew.VECTOR3D(*d["offset"])
            fp.Models().push_back(m)
        else:
            for m in quelle.Models():
                fp.Models().push_back(m)


def nacharbeit(ziel: pathlib.Path) -> None:
    """Ohne neues Routing: GND-Pins des QFN-Codecs voll an die Fläche (Thermals fänden zwischen den
    Nachbarpads keinen Platz), Bestückungsattribute aus dem Schaltplan, Flächen neu füllen."""
    board = pcbnew.LoadBoard(str(ziel))
    _verschieben_nach(board, X0, Y0)               # zurück in die Konstruktionskoordinaten
    pcbnew.SaveBoard(str(ziel), board)
    _beschriftung_entfernen(ziel)
    board = pcbnew.LoadBoard(str(ziel))
    teile, _ = netzliste()
    for fp in board.GetFootprints():
        t = teile.get(fp.GetReference())
        if t:
            fp.SetDNP(t["wert"] == "DNP")
        if fp.GetReference() == "U2":
            for pad in fp.Pads():
                if pad.GetNetname() == "GND":
                    pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    beschriftung(board)
    texte_waagerecht(board)
    modelle_erneuern(board)
    _verschieben_nach(board, BLATT_X, BLATT_Y)
    board.BuildConnectivity()                     # nach dem Verschieben, sonst bleiben Inseln stehen
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(ziel), board)


def pruefen(ziel: pathlib.Path) -> int:
    """DRC mit den Projektregeln (JLCPCB); gibt die Zahl der Fehler und offenen Verbindungen aus."""
    with tempfile.TemporaryDirectory() as tmp:
        bericht = pathlib.Path(tmp) / "drc.json"
        subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all", "--schematic-parity",
                        "-o", str(bericht), str(ziel)], capture_output=True)
        d = json.loads(bericht.read_text(encoding="utf-8"))
    arten: dict[str, int] = {}
    for v in d["violations"]:
        arten[f'{v["severity"]}:{v["type"]}'] = arten.get(f'{v["severity"]}:{v["type"]}', 0) + 1
    offen = len(d.get("unconnected_items", []))
    paritaet = len(d.get("schematic_parity", []))
    print("DRC:", ", ".join(f"{k} {n}" for k, n in sorted(arten.items())) or "keine Verstöße")
    print(f"offene Verbindungen: {offen}, Abweichungen Schaltplan ↔ Platine: {paritaet}")
    return sum(n for k, n in arten.items() if k.startswith("error")) + offen + paritaet


def fertigung(ziel: pathlib.Path) -> None:
    """Fertigungsdaten für JLCPCB (Gerber, Bohrdaten, Bestückung) und 3D-Daten fürs Gehäuse nach fertigung/."""
    aus = HIER / "fertigung"
    aus.mkdir(exist_ok=True)
    lagen_ = "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"
    k = ["kicad-cli", "pcb", "export"]
    subprocess.run(k + ["gerbers", "--layers", lagen_, "--subtract-soldermask", "--no-x2", "-o", f"{aus}/gerber/",
                        str(ziel)], check=True, capture_output=True)
    subprocess.run(k + ["drill", "--format", "excellon", "--excellon-separate-th", "--generate-map", "--map-format",
                        "gerberx2", "-o", f"{aus}/gerber/", str(ziel)], check=True, capture_output=True)
    subprocess.run(k + ["pos", "--side", "front", "--format", "csv", "--units", "mm", "--exclude-dnp",
                        "-o", f"{aus}/bestueckung_oben.csv", str(ziel)], check=True, capture_output=True)
    subprocess.run(k + ["step", "--subst-models", "--force", "-o", f"{aus}/{NAME}.step", str(ziel)],
                   check=True, capture_output=True)
    subprocess.run(["kicad-cli", "pcb", "render", "--side", "top", "--width", "1600", "--height", "1200",
                    "--quality", "high", "-o", f"{aus}/{NAME}_oben.png", str(ziel)], check=True, capture_output=True)
    import shutil
    shutil.make_archive(str(aus / f"{NAME}_gerber"), "zip", aus / "gerber")
    print(f"Fertigungsdaten in {aus}")


def main() -> int:
    ziel = HIER / f"{NAME}.kicad_pcb"
    if "--nur-nacharbeit" in sys.argv:
        nacharbeit(ziel)
        return 1 if pruefen(ziel) else 0
    if "--nur-pruefen" in sys.argv:
        return 1 if pruefen(ziel) else 0
    if "--nur-fertigung" in sys.argv:
        fertigung(ziel)
        return 0
    teile, netze = netzliste()
    board = pcbnew.BOARD()
    lagen(board)
    umriss(board)
    bestuecken(board, teile, netze)
    ausrichten(board)
    flaechen(board)
    beschriftung(board)
    projekt_regeln()
    board.SetFileName(str(ziel))
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(ziel), board)
    print(f"{len(teile)} Bauteile, {len(netze)} Netze → {ziel.name}")
    if "--routen" in sys.argv:
        routen(ziel)
        nacharbeit(ziel)
    if "--pruefen" in sys.argv:
        return 1 if pruefen(ziel) else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

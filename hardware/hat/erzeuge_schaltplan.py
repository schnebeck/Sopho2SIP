#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Erzeugt den KiCad-Schaltplan des Sopho2SIP-HAT (Raspberry Pi 4) aus den KiCad-Standardbibliotheken.

  hardware/hat/erzeuge_schaltplan.py            → sopho2sip-hat.kicad_sch/.kicad_pro, netzliste.txt
  hardware/hat/erzeuge_schaltplan.py --pruefen  → zusätzlich ERC und Abgleich der KiCad-Netzliste mit SOLL

Zwei getrennte Teile:
  SOLL      – was womit verbunden ist (Bauteil, Pin → Netz). Das ist die elektrische Wahrheit.
  zeichne() – wie es aussieht: Lage der Bauteile, Leitungen, Labels zwischen Blöcken, Rahmen.
Die Prüfung exportiert die Netzliste mit kicad-cli und vergleicht sie Pin für Pin mit SOLL; jede Abweichung der
Zeichnung (fehlende Leitung, ungewollte Berührung) fällt dort auf.

Begründungen der Schaltung: hardware/hat/README.md.
"""
from __future__ import annotations

import math
import pathlib
import re
import subprocess
import sys
import tempfile
import uuid

LIB = pathlib.Path("/usr/share/kicad/symbols")
HIER = pathlib.Path(__file__).resolve().parent
NAME = "sopho2sip-hat"

FP_R, FP_C, FP_C10 = "Resistor_SMD:R_0603_1608Metric", "Capacitor_SMD:C_0603_1608Metric", "Capacitor_SMD:C_0805_2012Metric"
FP_LED = "LED_SMD:LED_0603_1608Metric"
FP_LOCH = "MountingHole:MountingHole_2.7mm_M2.5"

# ------------------------------------------------------------------------------------------------------------------
# SOLL: Referenz → (Symbol, Wert, Footprint, {Pin: Netz}); "NC" = bewusst offen
# Versorgung: GND, +3V3, +5V (Pi) · +3.3VA (Codec analog) · GNDA (Telefonseite Audio) · GND_ISO, +3V3_ISO (RS-232)
# ------------------------------------------------------------------------------------------------------------------
GND_PI = {n: "GND" for n in ("6", "9", "14", "20", "25", "30", "34", "39")}
SOLL = {
    "J1": ("Connector:Raspberry_Pi_2_3", "Raspberry Pi GPIO", "Connector_PinSocket_2.54mm:PinSocket_2x20_P2.54mm_Vertical",
           {"1": "+3V3", "17": "+3V3", "2": "+5V", "4": "+5V", **GND_PI, "3": "I2C_SDA", "5": "I2C_SCL",
            "27": "ID_SD", "28": "ID_SC", "7": "UART3_TXD", "29": "UART3_RXD",
            "12": "I2S_BCLK", "35": "I2S_LRCLK", "38": "I2S_DIN", "40": "I2S_DOUT",
            "16": "LED_TELEFON", "18": "LED_GESPRAECH", "22": "TASTE",
            **{n: "NC" for n in ("8", "10", "11", "13", "15", "19", "21", "23", "24", "26", "31", "32", "33", "36", "37")}}),
    # HAT-ID
    "U1": ("Memory_EEPROM:24LC32", "24LC32", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
           {"1": "GND", "2": "GND", "3": "GND", "4": "GND", "8": "+3V3", "5": "ID_SD", "6": "ID_SC", "7": "EEPROM_WP"}),
    "C1": ("Device:C", "100n", FP_C, {"1": "+3V3", "2": "GND"}),
    "R1": ("Device:R", "3k9", FP_R, {"1": "+3V3", "2": "ID_SD"}),
    "R2": ("Device:R", "3k9", FP_R, {"1": "+3V3", "2": "ID_SC"}),
    "R3": ("Device:R", "10k", FP_R, {"1": "+3V3", "2": "EEPROM_WP"}),
    "JP1": ("Jumper:SolderJumper_2_Open", "WP", "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm",
            {"1": "EEPROM_WP", "2": "GND"}),
    # Codec
    "U2": ("Audio:WM8731SEDS", "WM8731SEDS", "Package_SO:SSOP-28_5.3x10.2mm_P0.65mm",
           {"1": "+3V3", "27": "+3V3", "28": "GND", "14": "+3.3VA", "8": "+3.3VA", "15": "GND", "11": "GND",
            "2": "NC", "3": "I2S_BCLK", "4": "I2S_DOUT", "5": "I2S_LRCLK", "6": "I2S_DIN", "7": "I2S_LRCLK",
            "9": "HP_L", "10": "NC", "12": "NC", "13": "NC", "16": "VMID", "17": "NC", "18": "NC", "19": "NC",
            "20": "LINE_IN", "21": "GND", "22": "GND", "23": "I2C_SDA", "24": "I2C_SCL", "25": "XTI", "26": "XTO"}),
    "Y1": ("Device:Crystal", "12.288MHz", "Crystal:Crystal_SMD_HC49-SD", {"1": "XTI", "2": "XTO"}),
    "C10": ("Device:C", "22p", FP_C, {"1": "XTI", "2": "GND"}),
    "C11": ("Device:C", "22p", FP_C, {"1": "XTO", "2": "GND"}),
    "C12": ("Device:C", "100n", FP_C, {"1": "+3V3", "2": "GND"}),
    "C13": ("Device:C", "100n", FP_C, {"1": "+3V3", "2": "GND"}),
    "C14": ("Device:C", "100n", FP_C, {"1": "+3.3VA", "2": "GND"}),
    "C15": ("Device:C", "10u", FP_C10, {"1": "+3.3VA", "2": "GND"}),
    "C16": ("Device:C", "100n", FP_C, {"1": "+3.3VA", "2": "GND"}),
    "C17": ("Device:C", "10u", FP_C10, {"1": "VMID", "2": "GND"}),
    "C18": ("Device:C", "100n", FP_C, {"1": "VMID", "2": "GND"}),
    "U4": ("Regulator_Linear:AP2112K-3.3", "AP2112K-3.3", "Package_TO_SOT_SMD:SOT-23-5",
           {"1": "+5V", "3": "+5V", "2": "GND", "4": "NC", "5": "+3.3VA"}),
    "C19": ("Device:C", "1u", FP_C, {"1": "+5V", "2": "GND"}),
    "C20": ("Device:C", "1u", FP_C, {"1": "+3.3VA", "2": "GND"}),
    # Sprechweg
    "J2": ("Connector:RJ12", "D340 Audio", "Connector_RJ:RJ12_Amphenol_54601-x06_Horizontal",
           {"1": "X_OUT", "2": "X_IN", "3": "GNDA", "4": "NC", "5": "NC", "6": "NC"}),
    "C21": ("Device:C", "1u", FP_C10, {"1": "X_OUT", "2": "T1_PRI"}),
    "T1": ("Device:Transformer_1P_1S", "600:600", "", {"1": "T1_PRI", "2": "GNDA", "4": "T1_SEK", "3": "GND"}),
    "C22": ("Device:C", "1u", FP_C, {"1": "T1_SEK", "2": "LINE_IN"}),
    "C23": ("Device:C", "10u", FP_C10, {"1": "HP_L", "2": "T2_PRI"}),
    "T2": ("Device:Transformer_1P_1S", "600:600", "", {"1": "T2_PRI", "2": "GND", "4": "T2_SEK", "3": "GNDA"}),
    "R4": ("Device:R", "0R", FP_R, {"1": "T2_SEK", "2": "X_IN_TEILER"}),
    "R5": ("Device:R", "DNP", FP_R, {"1": "X_IN_TEILER", "2": "GNDA"}),
    "C24": ("Device:C", "1u", FP_C10, {"1": "X_IN_TEILER", "2": "X_IN"}),
    # RS-232 isoliert
    "U3": ("Isolator:ADuM5211", "ADuM5211", "Package_SO:SSOP-20_5.3x7.2mm_P0.65mm",
           {"1": "+3V3", "9": "+5V", "2": "GND", "5": "GND", "6": "GND", "10": "GND", "8": "GND",
            "4": "UART3_TXD", "3": "UART3_RXD", "7": "NC", "14": "NC",
            "12": "+3V3_ISO", "20": "+3V3_ISO", "13": "GND_ISO", "11": "GND_ISO", "15": "GND_ISO", "16": "GND_ISO",
            "19": "GND_ISO", "17": "ISO_TXD", "18": "ISO_RXD"}),
    "C30": ("Device:C", "100n", FP_C, {"1": "+3V3", "2": "GND"}),
    "C31": ("Device:C", "10u", FP_C10, {"1": "+5V", "2": "GND"}),
    "C32": ("Device:C", "100n", FP_C, {"1": "+5V", "2": "GND"}),
    "C33": ("Device:C", "10u", FP_C10, {"1": "+3V3_ISO", "2": "GND_ISO"}),
    "C34": ("Device:C", "100n", FP_C, {"1": "+3V3_ISO", "2": "GND_ISO"}),
    "U5": ("Interface_UART:MAX3232", "MAX3232E", "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
           {"16": "+3V3_ISO", "15": "GND_ISO", "1": "C1P", "3": "C1N", "4": "C2P", "5": "C2N", "2": "ISO_VP",
            "6": "ISO_VN", "11": "ISO_TXD", "12": "ISO_RXD", "14": "RS232_TXD", "13": "RS232_RXD", "10": "GND_ISO",
            "7": "NC", "8": "NC", "9": "NC"}),
    "C35": ("Device:C", "100n", FP_C, {"1": "C1P", "2": "C1N"}),
    "C36": ("Device:C", "100n", FP_C, {"1": "C2P", "2": "C2N"}),
    "C37": ("Device:C", "100n", FP_C, {"1": "ISO_VP", "2": "GND_ISO"}),
    "C38": ("Device:C", "100n", FP_C, {"1": "ISO_VN", "2": "GND_ISO"}),
    "C39": ("Device:C", "100n", FP_C, {"1": "+3V3_ISO", "2": "GND_ISO"}),
    "J3": ("Connector:DE9_Pins_MountingHoles", "D340 PC-Schnittstelle",
           "Connector_Dsub:DSUB-9_Pins_Horizontal_P2.77x2.84mm_EdgePinOffset7.70mm_Housed_MountingHolesOffset9.12mm",
           {"2": "RS232_RXD", "3": "RS232_TXD", "5": "GND_ISO", "SH": "GND_ISO",
            **{n: "NC" for n in ("1", "4", "6", "7", "8", "9")}}),
    # Bedienung, Mechanik
    "R6": ("Device:R", "330", FP_R, {"1": "LED_TELEFON", "2": "LED1_A"}),
    "D1": ("Device:LED", "grün", FP_LED, {"2": "LED1_A", "1": "GND"}),
    "R7": ("Device:R", "330", FP_R, {"1": "LED_GESPRAECH", "2": "LED2_A"}),
    "D2": ("Device:LED", "gelb", FP_LED, {"2": "LED2_A", "1": "GND"}),
    "SW1": ("Switch:SW_Push", "Taste", "Button_Switch_SMD:SW_SPST_TL3342", {"1": "TASTE", "2": "GND"}),
    **{h: ("Mechanical:MountingHole", "M2.5", FP_LOCH, {}) for h in ("H1", "H2", "H3", "H4")},
}

# Power-Symbol je Netz (der Wert des Symbols ist der Netzname)
POWER = {"GND": "power:GND", "+3V3": "power:+3V3", "+5V": "power:+5V", "+3.3VA": "power:+3.3VA",
         "GNDA": "power:GNDA", "GND_ISO": "power:GND", "+3V3_ISO": "power:+3V3"}


# ------------------------------------------------------------------------------------------------------------------
# Bibliothek
# ------------------------------------------------------------------------------------------------------------------
def u() -> str:
    return str(uuid.uuid4())


def block(text: str, start: int) -> str:
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
    bib, name = lib_id.split(":")
    if bib not in _cache:
        _cache[bib] = (LIB / f"{bib}.kicad_sym").read_text(encoding="utf-8")
    text = _cache[bib]
    i = text.find(f'(symbol "{name}"')
    if i < 0:
        raise KeyError(lib_id)
    sym = block(text, i)
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


def rd(v: float) -> float:
    return round(v, 2)


# ------------------------------------------------------------------------------------------------------------------
# Plan: Zeichenelemente
# ------------------------------------------------------------------------------------------------------------------
class Plan:
    def __init__(self) -> None:
        self.wurzel = u()
        self.teile: list[tuple] = []          # (ref, lib_id, wert, fp, x, y, rot, spiegel, texte)
        self.pinpos: dict[tuple[str, str], tuple[float, float]] = {}
        self.segmente: list[tuple[tuple[float, float], tuple[float, float]]] = []
        self.labels: list[tuple[str, tuple[float, float], str]] = []
        self.power: list[tuple[str, tuple[float, float], int]] = []
        self.flaggen: list[tuple[float, float]] = []
        self.nc: list[tuple[float, float]] = []
        self.rahmen: list[tuple[float, float, float, float, str]] = []
        self.texte: list[tuple[float, float, str, float]] = []
        self.striche: list[tuple[tuple[float, float], tuple[float, float]]] = []
        self.libs: dict[str, str] = {}

    def setze(self, ref: str, x: float, y: float, rot: int = 0, spiegel: str | None = None,
              ref_at=None, wert_at=None, links: bool = False) -> None:
        """ref_at/wert_at: (dx, dy[, Ausrichtung]) relativ zum Bauteil, waagerecht; sonst Lage aus der Bibliothek.
        Waagerecht liegende Zweipole (R/C gedreht) bekommen Name oben, Wert unten."""
        lib_id = SOLL[ref][0]
        sym = self.libs.setdefault(lib_id, lib_symbol(lib_id))
        if rot in (90, 270) and lib_id in ("Device:R", "Device:C"):
            d = 3.3 if lib_id == "Device:C" else 2.54
            ref_at = ref_at or (0, -d)
            wert_at = wert_at or (0, d + 0.25)
        elif lib_id in ("Device:R", "Device:C"):     # senkrecht: Name und Wert neben das Bauteil, nicht darüber
            dx, ausr = (-3.0, "right") if links else (3.0, "left")
            ref_at = ref_at or (dx, -1.27, ausr)
            wert_at = wert_at or (dx, 1.27, ausr)
        self.teile.append((ref, lib_id, SOLL[ref][1], SOLL[ref][2], rd(x), rd(y), rot, spiegel,
                           {"Reference": ref_at, "Value": wert_at}))
        for nr, (px, py, _a) in lib_pins(sym).items():
            dx, dy = transform(px, py, rot, spiegel)
            self.pinpos[(ref, nr)] = (rd(x + dx), rd(y + dy))

    def P(self, ref: str, nr: str) -> tuple[float, float]:
        return self.pinpos[(ref, nr)]

    def w(self, *punkte) -> None:
        pts = [(rd(x), rd(y)) for x, y in punkte]
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            if a[0] != b[0] and a[1] != b[1]:
                raise ValueError(f"schräge Leitung {a}–{b}")
            self.segmente.append((a, b))

    def lbl(self, netz: str, p, richtung: str) -> None:
        self.labels.append((netz, (rd(p[0]), rd(p[1])), richtung))

    def pw(self, netz: str, p, rot: int = 0, senkrecht: bool = False) -> None:
        self.power.append((netz, (rd(p[0]), rd(p[1])), rot, senkrecht))

    def flag(self, p) -> None:
        self.flaggen.append((rd(p[0]), rd(p[1])))

    def offen(self, *refs_pins) -> None:
        for ref, nr in refs_pins:
            self.nc.append(self.P(ref, nr))

    def rahmen_(self, x0, y0, x1, y1, titel) -> None:
        self.rahmen.append((x0, y0, x1, y1, titel))

    def text(self, x, y, s, groesse=1.27) -> None:
        self.texte.append((x, y, s, groesse))

    def trenn(self, x, y0, y1) -> None:
        self.striche.append(((x, y0), (x, y1)))

    def nc_alle(self, ref: str) -> None:
        self.offen(*[(ref, n) for n, netz in SOLL[ref][3].items() if netz == "NC"])

    def ab(self, ref: str, nr: str, netz: str, laenge: float = 2.54) -> None:
        """Kurzer Draht senkrecht nach unten zu einem Masse-/Versorgungssymbol."""
        x, y = self.P(ref, nr)
        self.w((x, y), (x, y + laenge))
        self.pw(netz, (x, y + laenge))


# ------------------------------------------------------------------------------------------------------------------
# Zeichnung (Koordinaten in mm auf dem 1,27-mm-Raster; A3 quer)
# ------------------------------------------------------------------------------------------------------------------
def zeichne(p: Plan) -> None:
    P, w = p.P, p.w

    # ===== Raspberry Pi =========================================================================================
    p.rahmen_(15, 15, 132, 126, "Raspberry Pi 4 (40-polige Leiste)")
    p.setze("J1", 71.12, 81.28)
    for nr, netz in (("12", "I2S_BCLK"), ("35", "I2S_LRCLK"), ("38", "I2S_DIN"), ("40", "I2S_DOUT"),
                     ("16", "LED_TELEFON"), ("18", "LED_GESPRAECH"), ("22", "TASTE")):
        x, y = P("J1", nr)
        w((x, y), (38.1, y))
        p.lbl(netz, (38.1, y), "l")
    for nr, netz in (("27", "ID_SD"), ("28", "ID_SC"), ("3", "I2C_SDA"), ("5", "I2C_SCL"),
                     ("7", "UART3_TXD"), ("29", "UART3_RXD")):
        x, y = P("J1", nr)
        w((x, y), (106.68, y))
        p.lbl(netz, (106.68, y), "r")
    x5, y5 = P("J1", "2")
    w((x5, y5), (x5, 43.18)); p.pw("+5V", (x5, 43.18))
    w((x5, 45.72), (58.42, 45.72)); p.flag((58.42, 45.72))
    x3, y3 = P("J1", "1")
    w((x3, y3), (x3, 43.18)); p.pw("+3V3", (x3, 43.18))
    w((x3, 45.72), (83.82, 45.72)); p.flag((83.82, 45.72))
    xg, yg = P("J1", "6")
    w((xg, yg), (xg, 119.38)); p.pw("GND", (xg, 119.38))
    w((xg, 116.84), (78.74, 116.84)); p.flag((78.74, 116.84))
    p.nc_alle("J1")
    p.text(18, 25, "UART3 = GPIO4/5 (PL011, kann 8O1) · I²S = GPIO18–21 · I²C1 = GPIO2/3")

    # ===== HAT-ID-EEPROM ========================================================================================
    p.rahmen_(15, 131, 132, 198, "HAT-ID-EEPROM")
    p.setze("U1", 76.2, 167.64, ref_at=(-5.08, -6.6), wert_at=(9.5, 7.6))
    p.setze("C1", 55.88, 156.21)
    for ref, x in (("R1", 93.98), ("R2", 104.14), ("R3", 114.3)):
        p.setze(ref, x, 156.21)
    p.setze("JP1", 114.3, 175.26, rot=270, ref_at=(3.0, -1.27, "left"), wert_at=(3.0, 1.27, "left"))
    w((50.8, 152.4), (114.3, 152.4)); p.pw("+3V3", (50.8, 152.4))
    for ref in ("C1", "R1", "R2", "R3"):
        x, y = P(ref, "1")
        w((x, 152.4), (x, y))
    x, y = P("U1", "8"); w((x, y), (x, 152.4))
    p.ab("C1", "2", "GND")
    for nr, netz, r in (("5", "ID_SD", "R1"), ("6", "ID_SC", "R2")):
        x, y = P("U1", nr)
        w((x, y), (119.38, y)); p.lbl(netz, (119.38, y), "r")
        rx, ry = P(r, "2"); w((rx, ry), (rx, y))
    x, y = P("U1", "7"); w((x, y), P("JP1", "1"))   # endet an R3 und JP1 (senkrecht darunter)
    rx, ry = P("R3", "2"); w((rx, ry), (rx, y))
    p.ab("JP1", "2", "GND")
    for nr in ("1", "2", "3"):
        x, y = P("U1", nr); w((x, y), (60.96, y))
    w((60.96, P("U1", "1")[1]), (60.96, 172.72)); p.pw("GND", (60.96, 172.72))
    p.ab("U1", "4", "GND")
    p.text(18, 142, "Adresse 0x50 (A0–A2 = GND); WP hoch = schreibgeschützt, JP1 schließen zum Programmieren")

    # ===== Bedienung ============================================================================================
    p.rahmen_(15, 203, 132, 280, "Bedienung")
    for (r, d, netz, y) in (("R6", "D1", "LED_TELEFON", 220.98), ("R7", "D2", "LED_GESPRAECH", 236.22)):
        p.setze(r, 55.88, y, rot=90)
        p.setze(d, 73.66, y, rot=180)
        p.lbl(netz, (40.64, y), "l"); w((40.64, y), P(r, "1"))
        w(P(r, "2"), P(d, "2"))
        x, yy = P(d, "1"); w((x, yy), (83.82, yy), (83.82, yy + 2.54)); p.pw("GND", (83.82, yy + 2.54))
    p.setze("SW1", 60.96, 251.46)
    p.lbl("TASTE", (40.64, 251.46), "l"); w((40.64, 251.46), P("SW1", "1"))
    x, y = P("SW1", "2"); w((x, y), (83.82, y), (83.82, y + 2.54)); p.pw("GND", (83.82, y + 2.54))
    p.text(92, 222, "D1: Telefon verbunden")
    p.text(92, 237, "D2: Gespräch")
    p.text(92, 252, "Annehmen/Auflegen")
    p.text(92, 255, "(Pull-up im Pi)")
    for i, h in enumerate(("H1", "H2", "H3", "H4")):
        p.setze(h, 27.94 + i * 12.7, 267.97)
    p.text(80, 269, "M2,5, Raster 58 × 49 mm")

    # ===== Codec ================================================================================================
    p.rahmen_(137, 15, 268, 150, "Audio-Codec WM8731")
    p.setze("U2", 203.2, 88.9)
    # Versorgung oben: +3V3 digital (links), +3.3VA analog (rechts)
    w((167.64, 50.8), (200.66, 50.8)); p.pw("+3V3", (167.64, 50.8))
    for nr in ("27", "1"):
        x, y = P("U2", nr); w((x, y), (x, 50.8))
    for ref, x in (("C12", 175.26), ("C13", 185.42)):
        p.setze(ref, x, 54.61)
        w(P(ref, "1"), (x, 50.8))
        p.ab(ref, "2", "GND")
    w((205.74, 50.8), (248.92, 50.8)); p.pw("+3.3VA", (248.92, 50.8))
    for nr in ("14", "8"):
        x, y = P("U2", nr); w((x, y), (x, 50.8))
    for ref, x in (("C14", 218.44), ("C15", 228.6), ("C16", 238.76)):
        p.setze(ref, x, 54.61)
        w(P(ref, "1"), (x, 50.8))
        p.ab(ref, "2", "GND")
    # Digitale Schnittstellen links
    for nr, netz in (("4", "I2S_DOUT"), ("5", "I2S_LRCLK"), ("6", "I2S_DIN"), ("3", "I2S_BCLK"),
                     ("23", "I2C_SDA"), ("24", "I2C_SCL")):
        x, y = P("U2", nr); w((x, y), (167.64, y)); p.lbl(netz, (167.64, y), "l")
    x7, y7 = P("U2", "7")
    w((x7, y7), (180.34, y7), (180.34, P("U2", "5")[1]))
    for nr in ("22", "21"):
        x, y = P("U2", nr); w((x, y), (180.34, y))
    w((180.34, P("U2", "22")[1]), (180.34, 96.52)); p.pw("GND", (180.34, 96.52))
    # Quarz mit Lastkondensatoren
    p.setze("Y1", 160.02, 107.95, rot=270, ref_at=(4.0, -1.27, "left"), wert_at=(4.0, 1.27, "left"))
    p.setze("C10", 152.4, 105.41, links=True)
    p.setze("C11", 167.64, 115.57)
    x, y = P("U2", "25"); w((x, y), (160.02, y), P("Y1", "1"))
    w((152.4, y), (160.02, y)); w(P("C10", "1"), (152.4, y))
    x, y = P("U2", "26"); yq = P("Y1", "2")[1]
    w((x, y), (175.26, y), (175.26, yq), P("Y1", "2")); w(P("C11", "1"), (167.64, yq))
    p.ab("C10", "2", "GND"); p.ab("C11", "2", "GND")
    # Masse unten
    for nr in ("28", "15", "11"):
        x, y = P("U2", nr); w((x, y), (x, 114.3))
    w((P("U2", "28")[0], 114.3), (P("U2", "11")[0], 114.3))
    w((203.2, 114.3), (203.2, 116.84)); p.pw("GND", (203.2, 116.84))
    # Analoge Ein-/Ausgänge rechts, VMID
    x, y = P("U2", "9"); w((x, y), (241.3, y)); p.lbl("HP_L", (241.3, y), "r")
    x, y = P("U2", "20"); w((x, y), (241.3, y)); p.lbl("LINE_IN", (241.3, y), "r")
    x, y = P("U2", "16"); w((x, y), (238.76, y))
    for ref, xc in (("C17", 228.6), ("C18", 238.76)):
        p.setze(ref, xc, y + 3.81)
        p.ab(ref, "2", "GND")
    p.nc_alle("U2")
    p.text(140, 25, "I²C 0x1A (CSB = MODE = GND) · dtoverlay=rpi-proto · Codec erzeugt die Takte (12,288 MHz)")
    p.text(224, 71, "LHPOUT treibt 600 Ω")
    # Analogversorgung
    p.text(222, 131, "Analogversorgung 3,3 V", 1.524)
    p.setze("U4", 190.5, 134.62, ref_at=(-6.35, -6.35), wert_at=(5.08, -6.35))
    p.setze("C19", 172.72, 135.89, links=True)
    p.setze("C20", 205.74, 135.89)
    xv, yv = P("U4", "1")
    w((165.1, yv), (xv, yv)); p.pw("+5V", (165.1, yv))
    xe, ye = P("U4", "3"); w((xe, ye), (177.8, ye), (177.8, yv))
    w(P("C19", "1"), (172.72, yv))
    xo, yo = P("U4", "5"); w((xo, yo), (213.36, yo)); p.pw("+3.3VA", (213.36, yo))
    w(P("C20", "1"), (205.74, yo))
    for ref in ("C19", "C20"):
        p.ab(ref, "2", "GND")
    p.ab("U4", "2", "GND")
    p.offen(("U4", "4"))

    # ===== Sprechweg ============================================================================================
    p.rahmen_(273, 15, 405, 150, "Sprechweg zur D340 (galvanisch getrennt)")
    p.setze("J2", 393.7, 81.28, rot=180)
    p.setze("T1", 325.12, 50.8, spiegel="y")
    p.setze("T2", 325.12, 116.84)
    p.setze("C21", 354.33, 45.72, rot=270)
    p.setze("C22", 304.8, 45.72, rot=270)
    p.setze("C23", 304.8, 111.76, rot=90)
    p.setze("R4", 344.17, 111.76, rot=90)
    p.setze("C24", 359.41, 111.76, rot=90)
    p.setze("R5", 351.79, 115.57, links=True)
    # Aufnahme: X_OUT → C21 → T1 → C22 → LINE_IN
    x, y = P("J2", "1"); w((x, y), (368.3, y), (368.3, 45.72), P("C21", "1"))
    w(P("C21", "2"), P("T1", "1"))
    x, y = P("T1", "2"); w((x, y), (340.36, y), (340.36, y + 2.54)); p.pw("GNDA", (340.36, y + 2.54))
    w((340.36, y), (345.44, y)); p.flag((345.44, y))
    w(P("T1", "4"), P("C22", "1"))
    x, y = P("C22", "2"); w((x, y), (281.94, y)); p.lbl("LINE_IN", (281.94, y), "l")
    x, y = P("T1", "3"); w((x, y), (312.42, y), (312.42, y + 2.54)); p.pw("GND", (312.42, y + 2.54))
    # Wiedergabe: HP_L → C23 → T2 → R4 (R5) → C24 → X_IN
    x, y = P("C23", "1"); w((281.94, y), (x, y)); p.lbl("HP_L", (281.94, y), "l")
    w(P("C23", "2"), P("T2", "1"))
    x, y = P("T2", "2"); w((x, y), (312.42, y), (312.42, y + 2.54)); p.pw("GND", (312.42, y + 2.54))
    w(P("T2", "4"), P("R4", "1"))
    w(P("R4", "2"), P("C24", "1"))
    x, y = P("C24", "2"); xi, yi = P("J2", "2")
    w((x, y), (373.38, y), (373.38, yi), (xi, yi))
    p.ab("R5", "2", "GNDA")
    x, y = P("T2", "3"); w((x, y), (340.36, y), (340.36, y + 2.54)); p.pw("GNDA", (340.36, y + 2.54))
    x, y = P("J2", "3"); w((x, y), (378.46, y), (378.46, y + 5.08)); p.pw("GNDA", (378.46, y + 5.08))
    p.offen(("J2", "4"), ("J2", "5"), ("J2", "6"))
    for y0, y1 in ((32, 39), (62, 104), (128, 142)):
        p.trenn(325.12, y0, y1)
    p.text(292, 146, "Pi-Seite (GND)")
    p.text(338, 146, "Telefonseite (GNDA)")
    p.text(276, 25, "oben Aufnahme (X_OUT → Codec), unten Wiedergabe (Codec → X_IN); R4 = 0R, R5 unbestückt")
    p.text(352, 70, "RJ12 1:1 zur Audio-Buchse")

    # ===== RS-232 ===============================================================================================
    p.rahmen_(137, 158, 405, 248, "RS-232 zur D340 (galvanisch getrennt)")
    p.setze("U3", 203.2, 203.2, ref_at=(-12.7, -14.6), wert_at=(-14.5, 15.0))
    p.setze("U5", 271.78, 203.2, ref_at=(-12.7, -27.3), wert_at=(12.7, -27.3))
    p.setze("J3", 345.44, 210.82, ref_at=(0, -16.5), wert_at=(0, -14.2))
    # Pi-Seite des ADuM5211
    x, y = P("U3", "3"); w((x, y), (177.8, y)); p.lbl("UART3_RXD", (177.8, y), "l")
    x, y = P("U3", "4"); w((x, y), (177.8, y)); p.lbl("UART3_TXD", (177.8, y), "l")
    x, y = P("U3", "8"); w((x, y), (185.42, y), (185.42, y + 2.54)); p.pw("GND", (185.42, y + 2.54))
    x1, y1 = P("U3", "1"); w((149.86, 172.72), (x1, 172.72), (x1, y1)); p.pw("+3V3", (149.86, 172.72))
    x9, y9 = P("U3", "9"); w((165.1, 180.34), (x9, 180.34), (x9, y9)); p.pw("+5V", (165.1, 180.34))
    p.setze("C30", 154.94, 176.53)
    p.setze("C31", 170.18, 184.15)
    p.setze("C32", 180.34, 184.15)
    for ref, schiene in (("C30", 172.72), ("C31", 180.34), ("C32", 180.34)):
        x, y = P(ref, "1"); w((x, y), (x, schiene))
        p.ab(ref, "2", "GND")
    x, y = P("U3", "2"); w((x, y), (x, 220.98), (193.04, 220.98), (193.04, 223.52)); p.pw("GND", (193.04, 223.52))
    # isolierte Seite des ADuM5211
    x, y = P("U3", "11"); w((x, y), (x, 220.98), (213.36, 220.98), (213.36, 223.52)); p.pw("GND_ISO", (213.36, 223.52))
    w((213.36, 220.98), (220.98, 220.98)); p.flag((220.98, 220.98))
    w((P("U3", "12")[0], 180.34), (238.76, 180.34)); p.pw("+3V3_ISO", (238.76, 180.34))
    w((215.9, 180.34), (215.9, 177.8)); p.flag((215.9, 177.8))
    for nr in ("12", "20"):
        x, y = P("U3", nr); w((x, y), (x, 180.34))
    p.setze("C33", 220.98, 184.15)
    p.setze("C34", 233.68, 184.15)
    for ref in ("C33", "C34"):
        x, y = P(ref, "1"); w((x, y), (x, 180.34))
        p.ab(ref, "2", "GND_ISO")
    x, y = P("U3", "13"); w((x, y), (218.44, y), (218.44, y + 2.54)); p.pw("GND_ISO", (218.44, y + 2.54))
    p.offen(("U3", "7"), ("U3", "14"))
    # ADuM5211 ⇄ MAX3232
    x, y = P("U3", "17"); xt, yt = P("U5", "11"); w((x, y), (233.68, y), (233.68, yt), (xt, yt))
    x, y = P("U3", "18"); xr, yr = P("U5", "12"); w((xr, yr), (238.76, yr), (238.76, y), (x, y))
    # MAX3232: Ladungspumpe, Versorgung, unbenutzter Eingang
    p.setze("C35", 246.38, 184.15)
    p.setze("C36", 297.18, 184.15)
    w(P("U5", "1"), P("C35", "1")); w(P("U5", "3"), P("C35", "2"))
    w(P("U5", "4"), P("C36", "1")); w(P("U5", "5"), P("C36", "2"))
    p.setze("C37", 300.99, P("U5", "2")[1], rot=90, ref_at=(-2.2, -3.4), wert_at=(2.6, -3.4))
    p.setze("C38", 300.99, P("U5", "6")[1], rot=90, ref_at=(-2.2, -3.75), wert_at=(2.6, -3.75))
    for nr, ref in (("2", "C37"), ("6", "C38")):
        w(P("U5", nr), P(ref, "1"))
        x, y = P(ref, "2"); w((x, y), (307.34, y)); p.pw("GND_ISO", (307.34, y), rot=90)
    xv, yv = P("U5", "16"); w((xv, yv), (xv, 165.1)); p.pw("+3V3_ISO", (xv, 165.1))
    p.setze("C39", 280.67, 168.91, rot=90)
    w((xv, 168.91), P("C39", "1"))
    x2, y2 = P("C39", "2"); w((x2, y2), (287.02, y2)); p.pw("GND_ISO", (287.02, y2), rot=90)
    p.ab("U5", "15", "GND_ISO")
    x, y = P("U5", "10"); w((x, y), (246.38, y)); p.pw("GND_ISO", (246.38, y), rot=270, senkrecht=True)
    p.offen(("U5", "7"), ("U5", "8"), ("U5", "9"))
    # MAX3232 ⇄ DE9
    x, y = P("U5", "14"); xj, yj = P("J3", "3"); w((x, y), (314.96, y), (314.96, yj), (xj, yj))
    w(P("U5", "13"), P("J3", "2"))
    x, y = P("J3", "5"); w((x, y), (x - 2.54, y)); p.pw("GND_ISO", (x - 2.54, y), rot=270)
    p.ab("J3", "SH", "GND_ISO")
    p.offen(*[("J3", n) for n in ("1", "4", "6", "7", "8", "9")])
    for y0, y1 in ((164, 186), (226, 246)):
        p.trenn(203.2, y0, y1)
    p.text(150, 246, "Pi-Seite (GND)")
    p.text(208, 246, "isolierte Seite (GND_ISO)")
    p.text(140, 239, "ADuM5211: Trenner mit isolierter 3,3-V-Versorgung (VSEL = GND_ISO) · dtoverlay=uart3")
    p.text(356, 223, "DE9-Stecker wie am PC:")
    p.text(356, 226, "2 RxD · 3 TxD · 5 GND")
    p.text(356, 229, "1:1-Kabel zur D340,")
    p.text(356, 232, "1200 Bd 8O1")


# ------------------------------------------------------------------------------------------------------------------
# Ausgabe
# ------------------------------------------------------------------------------------------------------------------
def eigenschaft(name, wert, x, y, winkel=0, versteckt=False, ausrichtung=None) -> str:
    hide = " (hide yes)" if versteckt else ""
    j = f" (justify {ausrichtung})" if ausrichtung else ""
    return (f'\t\t(property "{name}" "{wert}"\n\t\t\t(at {rd(x)} {rd(y)} {winkel:g})\n'
            f'\t\t\t(effects (font (size 1.27 1.27)){j}{hide})\n\t\t)\n')


def symbol_text(p: Plan, ref, lib_id, wert, fp, x, y, rot, spiegel, pinnummern, versteckt_ref=False,
                versteckt_wert=False, texte=None) -> str:
    sym = p.libs[lib_id]
    m = f"\t\t(mirror {spiegel})\n" if spiegel else ""
    s = (f'\t(symbol\n\t\t(lib_id "{lib_id}")\n\t\t(at {rd(x)} {rd(y)} {rot})\n{m}\t\t(unit 1)\n\t\t(exclude_from_sim no)\n'
         f'\t\t(in_bom {"no" if ref.startswith("#") else "yes"})\n\t\t(on_board yes)\n'
         f'\t\t(dnp {"yes" if wert == "DNP" else "no"})\n\t\t(uuid "{u()}")\n')
    for name, wertx, versteckt in (("Reference", ref, versteckt_ref), ("Value", wert, versteckt_wert)):
        # Textwinkel ist in KiCad relativ zur Bauteildrehung: bei 90°/270° ergibt 90° waagerechte Schrift
        waagerecht = 90 if rot in (90, 270) else 0
        vorgabe = (texte or {}).get(name)
        if vorgabe:
            dx, dy = vorgabe[0], vorgabe[1]
            s += eigenschaft(name, wertx, x + dx, y + dy, waagerecht, versteckt, vorgabe[2] if len(vorgabe) > 2 else None)
            continue
        lx, ly, la = lage(sym, name)
        dx, dy = transform(lx, ly, rot, spiegel)
        s += eigenschaft(name, wertx, x + dx, y + dy, waagerecht if rot in (90, 270) else la, versteckt)
    s += eigenschaft("Footprint", fp, x, y, versteckt=True)
    s += eigenschaft("Datasheet", "", x, y, versteckt=True)
    for n in pinnummern:
        s += f'\t\t(pin "{n}" (uuid "{u()}"))\n'
    s += (f'\t\t(instances\n\t\t\t(project "{NAME}"\n\t\t\t\t(path "/{p.wurzel}" (reference "{ref}") (unit 1))\n'
          f'\t\t\t)\n\t\t)\n\t)\n')
    return s


def auf_strecke(pt, a, b) -> bool:
    (x, y), (x1, y1), (x2, y2) = pt, a, b
    if x1 == x2 == x:
        return min(y1, y2) < y < max(y1, y2)
    if y1 == y2 == y:
        return min(x1, x2) < x < max(x1, x2)
    return False


def schreibe(p: Plan) -> str:
    anschluss: dict[tuple, set] = {}
    for (ref, nr), pt in p.pinpos.items():
        netz = SOLL[ref][3].get(nr)
        if netz and netz != "NC":
            anschluss.setdefault(pt, set()).add(f"{ref}.{nr}")
    # T-Stellen: Endpunkte, die im Inneren einer anderen Strecke liegen → Strecke dort teilen (KiCad braucht das)
    punkte = {pt for seg in p.segmente for pt in seg} | set(anschluss) | {lp for _, lp, _ in p.labels} \
        | {pp for _, pp, _, _ in p.power} | set(p.flaggen)
    segmente = list(dict.fromkeys(p.segmente))
    i = 0
    while i < len(segmente):
        a, b = segmente[i]
        teil = next((pt for pt in punkte if auf_strecke(pt, a, b)), None)
        if teil:
            segmente[i:i + 1] = [(a, teil), (teil, b)]
            continue
        i += 1
    grad: dict[tuple, int] = {}
    for a, b in segmente:
        grad[a] = grad.get(a, 0) + 1
        grad[b] = grad.get(b, 0) + 1
    for pt in set(anschluss) | {pp for _, pp, _, _ in p.power} | set(p.flaggen) | {lp for _, lp, _ in p.labels}:
        if pt in grad:
            grad[pt] += 1
    junctions = sorted(pt for pt, g in grad.items() if g >= 3)
    beruehrt = {pt for seg in segmente for pt in seg} | {lp for _, lp, _ in p.labels} | {pp for _, pp, _, _ in p.power}
    offen = sorted(", ".join(sorted(v)) for pt, v in anschluss.items() if pt not in beruehrt)
    if offen:
        raise SystemExit(f"Pins ohne Anschluss in der Zeichnung: {offen}")
    nc_ohne = [(r, n) for (r, n), pt in p.pinpos.items() if SOLL[r][3].get(n) == "NC" and pt not in p.nc]
    if nc_ohne:
        raise SystemExit(f"NC-Pins ohne Markierung: {nc_ohne}")

    t = []
    for ref, lib_id, wert, fp, x, y, rot, spiegel, texte in p.teile:
        t.append(symbol_text(p, ref, lib_id, wert, fp, x, y, rot, spiegel, sorted(lib_pins(p.libs[lib_id])),
                             texte=texte))
    for i, (netz, (x, y), rot, senkrecht) in enumerate(p.power, 1):
        lib_id = POWER[netz]
        p.libs.setdefault(lib_id, lib_symbol(lib_id))
        texte = None
        if rot in (90, 270) and not senkrecht:      # Wert waagerecht neben das gedrehte Symbol
            # bei 90° kippt KiCad die (relativ gespeicherte) Schrift auf 180° und kehrt dabei die Ausrichtung um
            texte = {"Value": (3.3, 0, "right") if rot == 90 else (-3.3, 0, "right")}
        t.append(symbol_text(p, f"#PWR{i:03d}", lib_id, netz, "", x, y, rot, None, ["1"], versteckt_ref=True,
                             texte=texte))
    p.libs.setdefault("power:PWR_FLAG", lib_symbol("power:PWR_FLAG"))
    for i, (x, y) in enumerate(p.flaggen, 1):
        t.append(symbol_text(p, f"#FLG{i:03d}", "power:PWR_FLAG", "PWR_FLAG", "", x, y, 0, None, ["1"],
                             versteckt_ref=True, versteckt_wert=True))
    for a, b in segmente:
        t.append(f'\t(wire (pts (xy {a[0]} {a[1]}) (xy {b[0]} {b[1]})) (stroke (width 0) (type default)) (uuid "{u()}"))\n')
    for x, y in junctions:
        t.append(f'\t(junction (at {x} {y}) (diameter 0) (color 0 0 0 0) (uuid "{u()}"))\n')
    for x, y in p.nc:
        t.append(f'\t(no_connect (at {x} {y}) (uuid "{u()}"))\n')
    ausr = {"l": (180, "right"), "r": (0, "left"), "u": (90, "left"), "d": (270, "right")}
    for netz, (x, y), richtung in p.labels:
        a, j = ausr[richtung]
        t.append(f'\t(label "{netz}" (at {x} {y} {a}) (effects (font (size 1.27 1.27)) (justify {j} bottom)) (uuid "{u()}"))\n')
    for x0, y0, x1, y1, titel in p.rahmen:
        t.append(f'\t(rectangle (start {x0} {y0}) (end {x1} {y1}) (stroke (width 0.3) (type dash) (color 72 72 72 1)) '
                 f'(fill (type none)) (uuid "{u()}"))\n')
        t.append(f'\t(text "{titel}" (exclude_from_sim no) (at {x0 + 2} {y0 + 5} 0) (effects (font (size 2.2 2.2) bold) '
                 f'(justify left bottom)) (uuid "{u()}"))\n')
    for x, y, s, g in p.texte:
        t.append(f'\t(text "{s}" (exclude_from_sim no) (at {x} {y} 0) (effects (font (size {g} {g}) italic) '
                 f'(justify left bottom)) (uuid "{u()}"))\n')
    for (x0, y0), (x1, y1) in p.striche:
        t.append(f'\t(polyline (pts (xy {x0} {y0}) (xy {x1} {y1})) (stroke (width 0.4) (type dash_dot) '
                 f'(color 194 0 0 1)) (uuid "{u()}"))\n')

    kopf = (f'(kicad_sch\n\t(version 20250114)\n\t(generator "sopho2sip")\n\t(generator_version "2.0")\n'
            f'\t(uuid "{p.wurzel}")\n\t(paper "A3")\n'
            f'\t(title_block\n\t\t(title "Sopho2SIP-HAT")\n\t\t(rev "0.2")\n\t\t(company "Sopho2SIP")\n'
            f'\t\t(comment 1 "Pi 4 ⇄ ErgoLine D340: RS-232 isoliert, Audio X_OUT/X_IN")\n'
            f'\t\t(comment 2 "Entwurf – Datenblätter vor Fertigung prüfen")\n\t)\n\t(lib_symbols\n')
    libteil = "".join("\t\t" + s.replace("\n", "\n\t\t") + "\n" for s in p.libs.values())
    fuss = '\t(sheet_instances\n\t\t(path "/" (page "1"))\n\t)\n\t(embedded_fonts no)\n)\n'
    return kopf + libteil + "\t)\n" + "".join(t) + fuss


def soll_netze() -> dict[str, list[str]]:
    netze: dict[str, list[str]] = {}
    for ref, (_, _, _, belegung) in SOLL.items():
        for nr, netz in belegung.items():
            if netz != "NC":
                netze.setdefault(netz, []).append(f"{ref}.{nr}")
    return {n: sorted(v) for n, v in netze.items()}


def pruefe(sch: pathlib.Path) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        erc = pathlib.Path(tmp) / "erc.txt"
        net = pathlib.Path(tmp) / "hat.net"
        subprocess.run(["kicad-cli", "sch", "erc", "--severity-all", "-o", str(erc), str(sch)], capture_output=True)
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(net), str(sch)],
                       capture_output=True)
        bericht = erc.read_text()
        m = re.search(r"ERC messages: (\d+)\s+Errors (\d+)\s+Warnings (\d+)", bericht)
        print(f"ERC: {m.group(0) if m else bericht[:300]}")
        if m and m.group(1) != "0":
            print("\n".join(z for z in bericht.splitlines() if z.startswith("[") or z.startswith("    @"))[:4000])
        teil = net.read_text()
        teil = teil[teil.index("(nets"):]
        ist = {}
        for b in re.split(r'\n\t\t\(net\n', teil)[1:]:
            name = re.search(r'\(name "([^"]+)"\)', b).group(1).lstrip("/")
            k = sorted(f"{r}.{pn}" for r, pn in re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', b)
                       if not r.startswith("#"))
            if k and not name.startswith("unconnected"):
                ist[name] = k
        # Vergleich der Pin-Gruppen (reine Leitungsnetze tragen in KiCad automatische Namen wie Net-(U5-VS-))
        soll = soll_netze()
        ist_gruppen = {frozenset(v): n for n, v in ist.items()}
        abw = []
        for n, v in sorted(soll.items()):
            gefunden = ist_gruppen.pop(frozenset(v), None)
            if gefunden is None:
                abw.append(n)
                naechstes = max(ist.items(), key=lambda kv: len(set(kv[1]) & set(v)))
                print(f"  ABWEICHUNG {n}:\n    soll {v}\n    ähnlichstes ist-Netz {naechstes[0]}: {naechstes[1]}")
            elif not gefunden.startswith("Net-") and gefunden != n:
                print(f"  Hinweis: {n} heißt in KiCad {gefunden}")
        for g, n in ist_gruppen.items():
            abw.append(n)
            print(f"  ZUSÄTZLICHES NETZ in KiCad {n}: {sorted(g)}")
        print(f"Netzliste: {len(soll)} Netze soll, {len(ist)} ist, Abweichungen: {len(abw)}")
        return 1 if abw or (m and m.group(1) != "0") else 0


def main() -> int:
    p = Plan()
    zeichne(p)
    fehlt = set(SOLL) - {t[0] for t in p.teile}
    if fehlt:
        raise SystemExit(f"nicht platziert: {sorted(fehlt)}")
    sch = HIER / f"{NAME}.kicad_sch"
    sch.write_text(schreibe(p), encoding="utf-8")
    (HIER / f"{NAME}.kicad_pro").write_text(
        '{\n  "meta": {"filename": "%s.kicad_pro", "version": 1},\n  "sheets": [["%s", "Root"]]\n}\n' % (NAME, p.wurzel),
        encoding="utf-8")
    (HIER / "netzliste.txt").write_text("# Netz: Pins (SOLL aus erzeuge_schaltplan.py)\n"
                                        + "".join(f"{n}: {' '.join(v)}\n" for n, v in sorted(soll_netze().items())),
                                        encoding="utf-8")
    print(f"{len(SOLL)} Bauteile, {len(soll_netze())} Netze, {len(p.segmente)} Leitungszüge → {sch.name}")
    return pruefe(sch) if "--pruefen" in sys.argv else 0


if __name__ == "__main__":
    raise SystemExit(main())

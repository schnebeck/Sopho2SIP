#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Erzeugt den KiCad-Schaltplan des Sopho2SIP-HAT (Raspberry Pi 4) aus den KiCad-Standardbibliotheken.

  hardware/hat/erzeuge_schaltplan.py            → sopho2sip-hat.kicad_sch / .kicad_pro
  kicad-cli sch erc hardware/hat/sopho2sip-hat.kicad_sch

Alle Verbindungen laufen über Netznamen (kurzer Draht am Pin + Label bzw. Power-Symbol), damit die Netzliste aus
der Tabelle unten eindeutig ist. Die Netzliste ist die Quelle; den Schaltplan in KiCad nur verschönern, nicht
umverdrahten – oder hier ändern und neu erzeugen.

Blöcke (Begründungen in hardware/hat/README.md):
  J1  40-polige Buchsenleiste zum Pi; UART3 (GPIO4/5, PL011 – der Mini-UART kann keine Parität, die D340 braucht 8O1)
  U1  HAT-ID-EEPROM 24LC32 an ID_SD/ID_SC
  U2  Audio-Codec WM8731 (I²C 0x1A, I²S, Quarz 12,288 MHz) – Overlay rpi-proto
  U3  ADuM5211: Digitaltrenner mit isolierter Versorgung für die RS-232-Seite
  U4  AP2112K-3.3: rauscharme 3,3 V für den Analogteil des Codecs
  U5  MAX3232 auf der isolierten Seite; J3 DE9-Stecker (Pi = DTE wie ein PC, 1:1-Kabel zur D340)
  T1/T2 600:600-Übertrager, J2 RJ12 zur Audio-Buchse der D340 (Pin 1 X_OUT, 2 X_IN, 3 GNDA)
"""
from __future__ import annotations

import pathlib
import re
import uuid

LIB = pathlib.Path("/usr/share/kicad/symbols")
HIER = pathlib.Path(__file__).resolve().parent
NAME = "sopho2sip-hat"
RASTER = 1.27
STUB = 2.54

# ------------------------------------------------------------------------------------------------------------------
# Bauteile: (Referenz, Bibliothek:Symbol, Wert, Footprint, (x, y) in mm, {Pin: Netz})
#   Netz "NC" = nicht angeschlossen (No-Connect-Marke); Netze mit + oder GND am Anfang sind Versorgungsnetze.
# ------------------------------------------------------------------------------------------------------------------
FP_R, FP_C, FP_C10 = "Resistor_SMD:R_0603_1608Metric", "Capacitor_SMD:C_0603_1608Metric", "Capacitor_SMD:C_0805_2012Metric"

GND_PI = {n: "GND" for n in ("6", "9", "14", "20", "25", "30", "34", "39")}
BAUTEILE = [
    ("J1", "Connector:Raspberry_Pi_2_3", "Raspberry Pi GPIO", "Connector_PinSocket_2.54mm:PinSocket_2x20_P2.54mm_Vertical",
     (60, 120), {"1": "+3V3", "17": "+3V3", "2": "+5V", "4": "+5V", **GND_PI,
                 "3": "I2C_SDA", "5": "I2C_SCL", "27": "ID_SD", "28": "ID_SC",
                 "7": "UART3_TXD", "29": "UART3_RXD",
                 "12": "I2S_BCLK", "35": "I2S_LRCLK", "38": "I2S_DIN", "40": "I2S_DOUT",
                 "16": "LED_TELEFON", "18": "LED_GESPRAECH", "22": "TASTE",
                 **{n: "NC" for n in ("8", "10", "11", "13", "15", "19", "21", "23", "24", "26", "31", "32", "33", "36", "37")}}),

    # --- HAT-ID-EEPROM ---------------------------------------------------------------------------------------------
    ("U1", "Memory_EEPROM:24LC32", "24LC32", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
     (60, 230), {"1": "GND", "2": "GND", "3": "GND", "4": "GND", "8": "+3V3", "5": "ID_SD", "6": "ID_SC", "7": "EEPROM_WP"}),
    ("R1", "Device:R", "3k9", FP_R, (95, 215), {"1": "+3V3", "2": "ID_SD"}),
    ("R2", "Device:R", "3k9", FP_R, (105, 215), {"1": "+3V3", "2": "ID_SC"}),
    ("R3", "Device:R", "10k", FP_R, (115, 215), {"1": "+3V3", "2": "EEPROM_WP"}),
    ("JP1", "Jumper:SolderJumper_2_Open", "EEPROM schreiben", "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm",
     (115, 245), {"1": "EEPROM_WP", "2": "GND"}),
    ("C1", "Device:C", "100n", FP_C, (35, 230), {"1": "+3V3", "2": "GND"}),

    # --- Codec WM8731 --------------------------------------------------------------------------------------------
    ("U2", "Audio:WM8731SEDS", "WM8731SEDS", "Package_SO:SSOP-28_5.3x10.2mm_P0.65mm",
     (200, 110), {"1": "+3V3", "27": "+3V3", "28": "GND", "14": "+3V3A", "8": "+3V3A", "15": "GND", "11": "GND",
                  "2": "NC", "3": "I2S_BCLK", "4": "I2S_DOUT", "5": "I2S_LRCLK", "6": "I2S_DIN", "7": "I2S_LRCLK",
                  "9": "HP_L", "10": "NC", "12": "NC", "13": "NC", "16": "VMID", "17": "NC", "18": "NC",
                  "19": "NC", "20": "LINE_IN", "21": "GND", "22": "GND", "23": "I2C_SDA", "24": "I2C_SCL",
                  "25": "XTI", "26": "XTO"}),
    ("Y1", "Device:Crystal", "12.288MHz", "Crystal:Crystal_SMD_HC49-SD", (200, 170), {"1": "XTI", "2": "XTO"}),
    ("C10", "Device:C", "22p", FP_C, (185, 185), {"1": "XTI", "2": "GND"}),
    ("C11", "Device:C", "22p", FP_C, (215, 185), {"1": "XTO", "2": "GND"}),
    ("C12", "Device:C", "100n", FP_C, (150, 75), {"1": "+3V3", "2": "GND"}),       # DBVDD
    ("C13", "Device:C", "100n", FP_C, (160, 75), {"1": "+3V3", "2": "GND"}),       # DCVDD
    ("C14", "Device:C", "100n", FP_C, (170, 75), {"1": "+3V3A", "2": "GND"}),      # AVDD
    ("C15", "Device:C", "10u", FP_C10, (180, 75), {"1": "+3V3A", "2": "GND"}),
    ("C16", "Device:C", "100n", FP_C, (190, 75), {"1": "+3V3A", "2": "GND"}),      # HPVDD
    ("C17", "Device:C", "10u", FP_C10, (150, 150), {"1": "VMID", "2": "GND"}),
    ("C18", "Device:C", "100n", FP_C, (160, 150), {"1": "VMID", "2": "GND"}),

    # --- Analogversorgung --------------------------------------------------------------------------------------------
    ("U4", "Regulator_Linear:AP2112K-3.3", "AP2112K-3.3", "Package_TO_SOT_SMD:SOT-23-5",
     (200, 235), {"1": "+5V", "3": "+5V", "2": "GND", "4": "NC", "5": "+3V3A"}),
    ("C19", "Device:C", "1u", FP_C, (175, 235), {"1": "+5V", "2": "GND"}),
    ("C20", "Device:C", "1u", FP_C, (225, 235), {"1": "+3V3A", "2": "GND"}),

    # --- Sprechweg zur D340 (J2 RJ12, Übertrager) -------------------------------------------------------------------
    ("J2", "Connector:RJ12", "D340 Audio", "Connector_RJ:RJ12_Amphenol_54601-x06_Horizontal",
     (420, 110), {"1": "X_OUT", "2": "X_IN", "3": "TEL_GNDA", "4": "NC", "5": "NC", "6": "NC"}),
    # Aufnahme: X_OUT → C21 → T1 → C22 → LLINEIN
    ("C21", "Device:C", "1u", FP_C10, (380, 80), {"1": "X_OUT", "2": "T1_PRI"}),
    ("T1", "Device:Transformer_1P_1S", "600:600", "", (340, 90), {"1": "T1_PRI", "2": "TEL_GNDA", "3": "T1_SEK", "4": "GND"}),
    ("C22", "Device:C", "1u", FP_C, (300, 80), {"1": "T1_SEK", "2": "LINE_IN"}),
    # Wiedergabe: LHPOUT → C23 → T2 → R4 (0R, Teiler-Option mit R5) → C24 → X_IN
    ("C23", "Device:C", "10u", FP_C10, (300, 150), {"1": "HP_L", "2": "T2_PRI"}),
    ("T2", "Device:Transformer_1P_1S", "600:600", "", (340, 160), {"1": "T2_PRI", "2": "GND", "3": "T2_SEK", "4": "TEL_GNDA"}),
    ("R4", "Device:R", "0R", FP_R, (370, 150), {"1": "T2_SEK", "2": "X_IN_TEILER"}),
    ("R5", "Device:R", "DNP", FP_R, (380, 175), {"1": "X_IN_TEILER", "2": "TEL_GNDA"}),
    ("C24", "Device:C", "1u", FP_C10, (395, 150), {"1": "X_IN_TEILER", "2": "X_IN"}),

    # --- Isolierte RS-232 zur D340 -------------------------------------------------------------------------------
    ("U3", "Isolator:ADuM5211", "ADuM5211", "Package_SO:SSOP-20_5.3x7.2mm_P0.65mm",
     (300, 245), {"1": "+3V3", "9": "+5V", "2": "GND", "5": "GND", "6": "GND", "10": "GND", "8": "GND",
                  "4": "UART3_TXD", "3": "UART3_RXD", "7": "NC", "14": "NC",
                  "12": "ISO_3V3", "20": "ISO_3V3", "13": "ISO_GND", "11": "ISO_GND", "15": "ISO_GND",
                  "16": "ISO_GND", "19": "ISO_GND", "17": "ISO_TXD", "18": "ISO_RXD"}),
    ("C30", "Device:C", "100n", FP_C, (255, 225), {"1": "+3V3", "2": "GND"}),      # VDD1
    ("C31", "Device:C", "10u", FP_C10, (265, 225), {"1": "+5V", "2": "GND"}),      # VDDP
    ("C32", "Device:C", "100n", FP_C, (275, 225), {"1": "+5V", "2": "GND"}),
    ("C33", "Device:C", "10u", FP_C10, (325, 285), {"1": "ISO_3V3", "2": "ISO_GND"}),   # VISO
    ("C34", "Device:C", "100n", FP_C, (335, 285), {"1": "ISO_3V3", "2": "ISO_GND"}),
    ("U5", "Interface_UART:MAX3232", "MAX3232", "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
     (390, 245), {"16": "ISO_3V3", "15": "ISO_GND", "1": "C1P", "3": "C1N", "4": "C2P", "5": "C2N",
                  "2": "ISO_VP", "6": "ISO_VN", "11": "ISO_TXD", "12": "ISO_RXD", "14": "RS232_TXD", "13": "RS232_RXD",
                  "10": "ISO_GND", "7": "NC", "8": "NC", "9": "NC"}),
    ("C35", "Device:C", "100n", FP_C, (355, 290), {"1": "C1P", "2": "C1N"}),
    ("C36", "Device:C", "100n", FP_C, (367.5, 290), {"1": "C2P", "2": "C2N"}),
    ("C37", "Device:C", "100n", FP_C, (380, 290), {"1": "ISO_VP", "2": "ISO_GND"}),
    ("C38", "Device:C", "100n", FP_C, (392.5, 290), {"1": "ISO_VN", "2": "ISO_GND"}),
    ("C39", "Device:C", "100n", FP_C, (405, 290), {"1": "ISO_3V3", "2": "ISO_GND"}),
    ("J3", "Connector:DE9_Pins_MountingHoles", "D340 PC-Schnittstelle",
     "Connector_Dsub:DSUB-9_Pins_Horizontal_P2.77x2.84mm_EdgePinOffset7.70mm_Housed_MountingHolesOffset9.12mm",
     (460, 245), {"2": "RS232_RXD", "3": "RS232_TXD", "5": "ISO_GND", "SH": "ISO_GND",
                  **{n: "NC" for n in ("1", "4", "6", "7", "8", "9")}}),

    # --- Bedienung -----------------------------------------------------------------------------------------------
    ("R6", "Device:R", "330", FP_R, (100, 300), {"1": "LED_TELEFON", "2": "LED1_A"}),
    ("D1", "Device:LED", "grün", "LED_SMD:LED_0603_1608Metric", (120, 300), {"2": "LED1_A", "1": "GND"}),
    ("R7", "Device:R", "330", FP_R, (100, 330), {"1": "LED_GESPRAECH", "2": "LED2_A"}),
    ("D2", "Device:LED", "gelb", "LED_SMD:LED_0603_1608Metric", (120, 330), {"2": "LED2_A", "1": "GND"}),
    ("SW1", "Switch:SW_Push", "Annehmen/Auflegen", "Button_Switch_SMD:SW_SPST_TL3342", (160, 315), {"1": "TASTE", "2": "GND"}),
]

PWR_FLAGS = ["+5V", "+3V3", "GND", "ISO_3V3", "ISO_GND"]     # Netze ohne treibenden Pin (Versorgung über J1 bzw. VISO)
LOECHER = [("H1", (40, 380)), ("H2", (55, 380)), ("H3", (70, 380)), ("H4", (85, 380))]
POWER_SYMBOLE = {"+5V": "power:+5V", "+3V3": "power:+3V3", "GND": "power:GND", "+3V3A": "power:+3.3VA"}

NOTIZEN = [
    ((30, 30), "Sopho2SIP-HAT: Raspberry Pi ⇄ ErgoLine D340 (PC-Schnittstelle RS-232, Audio-Buchse X_OUT/X_IN)"),
    ((30, 36), "Netze per Label; erzeugt von hardware/hat/erzeuge_schaltplan.py (nicht von Hand umverdrahten)"),
    ((30, 205), "HAT-ID-EEPROM (Raspberry-Pi-HAT-Spezifikation): WP offen = schreibgeschützt, JP1 schließen zum Schreiben"),
    ((140, 49), "Codec WM8731: I²C 0x1A (CSB=0, MODE=0), Quarz 12,288 MHz,"),
    ((140, 55), "dtoverlay=rpi-proto; LHPOUT treibt den 600-Ω-Übertrager"),
    ((280, 55), "Sprechweg: zwei 600:600-Übertrager trennen Telefon (TEL_GNDA) und Pi (GND) galvanisch"),
    ((280, 61), "R4/R5: Teiler-Option für X_IN (Standard R4 = 0R, R5 unbestückt); Pegel per Codec einstellbar"),
    ((240, 210), "RS-232 isoliert: ADuM5211 (Digitaltrenner + isolierte 3,3 V, VSEL=GND) + MAX3232; dtoverlay=uart3 (GPIO4/5)"),
    ((240, 216), "J3 = DE9-Stecker wie am PC: Pin 2 RxD, Pin 3 TxD, Pin 5 GND; 1:1-Kabel zur DE9-Buchse der D340 (1200 Bd 8O1)"),
    ((90, 285), "Bedienung: LEDs an GPIO23/24, Taste an GPIO25 (interner Pull-up)"),
]


# ------------------------------------------------------------------------------------------------------------------
def u() -> str:
    return str(uuid.uuid4())


def block(text: str, start: int) -> tuple[str, int]:
    tiefe = 0
    for j in range(start, len(text)):
        if text[j] == "(":
            tiefe += 1
        elif text[j] == ")":
            tiefe -= 1
            if tiefe == 0:
                return text[start:j + 1], j + 1
    raise ValueError("unvollständiger Block")


_cache: dict[str, str] = {}


def lib_symbol(lib_id: str) -> str:
    """Symbolblock aus der Bibliothek, mit aufgelöstem 'extends' (Schaltpläne enthalten nur flache Symbole)."""
    bib, name = lib_id.split(":")
    if bib not in _cache:
        _cache[bib] = (LIB / f"{bib}.kicad_sym").read_text(encoding="utf-8")
    text = _cache[bib]
    i = text.find(f'(symbol "{name}"')
    if i < 0:
        raise KeyError(lib_id)
    sym, _ = block(text, i)
    m = re.search(r'\(extends "([^"]+)"\)', sym)
    if m:
        basis = lib_symbol(f"{bib}:{m.group(1)}")
        basis_name = m.group(1)
        # Eigenschaften des abgeleiteten Symbols übernehmen, Grafik/Pins der Basis behalten
        eigen = {p.group(1): p.group(0) for p in re.finditer(r'\(property "([^"]+)".*?\n\t\t\)', sym, re.S)}
        for key, prop in eigen.items():
            basis = re.sub(r'\(property "%s".*?\n\t\t\)' % re.escape(key), lambda _m: prop, basis, count=1, flags=re.S)
        basis = basis.replace(f'(symbol "{bib}:{basis_name}"', f'(symbol "{name}"', 1)
        basis = basis.replace(f'(symbol "{basis_name}_', f'(symbol "{name}_')
        sym = basis.replace(f'(symbol "{name}"', f'(symbol "{bib}:{name}"', 1)
        return sym
    return sym.replace(f'(symbol "{name}"', f'(symbol "{lib_id}"', 1)


def pins(sym: str) -> dict[str, tuple[float, float, int, str]]:
    """Pinnummer → (x, y, Winkel, Typ) in Symbolkoordinaten (y nach oben)."""
    out = {}
    for m in re.finditer(r'\(pin (\w+) \w+\s*\(at ([-\d.]+) ([-\d.]+) (\d+)\).*?\(number "([^"]*)"', sym, re.S):
        out[m.group(5)] = (float(m.group(2)), float(m.group(3)), int(m.group(4)), m.group(1))
    return out


def r(v: float) -> float:
    return round(round(v / RASTER) * RASTER, 2)


def eigenschaft(name: str, wert: str, x: float, y: float, versteckt: bool = False, winkel: float = 0) -> str:
    hide = " (hide yes)" if versteckt else ""
    return (f'\t\t(property "{name}" "{wert}"\n\t\t\t(at {x} {y} {winkel:g})\n\t\t\t(effects (font (size 1.27 1.27))'
            f'{hide})\n\t\t)\n')


def lage(sym: str, name: str) -> tuple[float, float, float]:
    """Position einer Eigenschaft im Bibliothekssymbol (x, y nach oben, Winkel)."""
    m = re.search(r'\(property "%s" "[^"]*"\s*\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)' % name, sym)
    return (float(m.group(1)), float(m.group(2)), float(m.group(3) or 0)) if m else (3.81, 0.0, 0.0)


def instanz(ref: str, lib_id: str, wert: str, fp: str, x: float, y: float, pinnummern, wurzel: str,
            sichtbar: bool = True, sym: str = "") -> str:
    s = (f'\t(symbol\n\t\t(lib_id "{lib_id}")\n\t\t(at {x} {y} 0)\n\t\t(unit 1)\n\t\t(exclude_from_sim no)\n'
         f'\t\t(in_bom {"yes" if sichtbar else "no"})\n\t\t(on_board yes)\n\t\t(dnp {"yes" if wert == "DNP" else "no"})\n'
         f'\t\t(uuid "{u()}")\n')
    (rx, ry, ra), (vx, vy, va) = lage(sym, "Reference"), lage(sym, "Value")
    s += eigenschaft("Reference", ref, round(x + rx, 2), round(y - ry, 2), versteckt=not sichtbar, winkel=ra)
    s += eigenschaft("Value", wert, round(x + vx, 2), round(y - vy, 2), versteckt=not sichtbar, winkel=va)
    s += eigenschaft("Footprint", fp, x, y, versteckt=True)
    s += eigenschaft("Datasheet", "", x, y, versteckt=True)
    for n in pinnummern:
        s += f'\t\t(pin "{n}" (uuid "{u()}"))\n'
    s += (f'\t\t(instances\n\t\t\t(project "{NAME}"\n\t\t\t\t(path "/{wurzel}" (reference "{ref}") (unit 1))\n'
          f'\t\t\t)\n\t\t)\n\t)\n')
    return s


def main() -> int:
    wurzel = u()
    lib_ids = sorted({b[1] for b in BAUTEILE} | set(POWER_SYMBOLE.values()) | {"power:PWR_FLAG", "Mechanical:MountingHole"})
    libsyms = {lid: lib_symbol(lid) for lid in lib_ids}
    teile, netz_pins = [], {}
    pwr_zaehler = 0
    flag_gesetzt = set()

    def power(netz: str, x: float, y: float):
        nonlocal pwr_zaehler
        pwr_zaehler += 1
        teile.append(instanz(f"#PWR{pwr_zaehler:03d}", POWER_SYMBOLE[netz], netz, "", x, y, ["1"], wurzel, sichtbar=False,
                             sym=libsyms[POWER_SYMBOLE[netz]]))
        if netz in PWR_FLAGS and netz not in flag_gesetzt:
            flagge(netz, x, y)

    def flagge(netz: str, x: float, y: float):
        nonlocal pwr_zaehler
        pwr_zaehler += 1
        flag_gesetzt.add(netz)
        teile.append(instanz(f"#FLG{pwr_zaehler:03d}", "power:PWR_FLAG", "PWR_FLAG", "", x, y, ["1"], wurzel, sichtbar=False,
                             sym=libsyms["power:PWR_FLAG"]))

    for ref, lib_id, wert, fp, (bx, by), belegung in BAUTEILE:
        bx, by = r(bx), r(by)
        sym_pins = pins(libsyms[lib_id])
        fehlend = set(sym_pins) - set(belegung)
        if fehlend:
            raise SystemExit(f"{ref}: Pins ohne Netz: {sorted(fehlend)}")
        unbekannt = set(belegung) - set(sym_pins)
        if unbekannt:
            raise SystemExit(f"{ref}: unbekannte Pins: {sorted(unbekannt)}")
        teile.append(instanz(ref, lib_id, wert, fp, bx, by, sorted(sym_pins), wurzel, sym=libsyms[lib_id]))
        gezeichnet = set()
        for nummer, netz in belegung.items():
            px, py, winkel, typ = sym_pins[nummer]
            x0, y0 = round(bx + px, 2), round(by - py, 2)
            if netz == "NC":
                teile.append(f'\t(no_connect (at {x0} {y0}) (uuid "{u()}"))\n')
                continue
            netz_pins.setdefault(netz, []).append(f"{ref}.{nummer}")
            if (x0, y0, netz) in gezeichnet:
                continue
            gezeichnet.add((x0, y0, netz))
            dx = {0: -1, 180: 1, 90: 0, 270: 0}[winkel]
            dy = {0: 0, 180: 0, 90: 1, 270: -1}[winkel]
            x1, y1 = round(x0 + dx * STUB, 2), round(y0 + dy * STUB, 2)
            teile.append(f'\t(wire (pts (xy {x0} {y0}) (xy {x1} {y1})) (stroke (width 0) (type default)) (uuid "{u()}"))\n')
            if netz in POWER_SYMBOLE:
                power(netz, x1, y1)
            else:
                ausrichtung = {(-1, 0): (180, "right"), (1, 0): (0, "left"), (0, -1): (90, "left"), (0, 1): (270, "right")}
                a, j = ausrichtung[(dx, dy)]
                teile.append(f'\t(label "{netz}" (at {x1} {y1} {a}) (effects (font (size 1.27 1.27)) (justify {j} bottom))'
                             f' (uuid "{u()}"))\n')
                if netz in PWR_FLAGS and netz not in flag_gesetzt:
                    flagge(netz, x1, y1)

    for ref, (x, y) in LOECHER:
        teile.append(instanz(ref, "Mechanical:MountingHole", "M2.5", "MountingHole:MountingHole_2.7mm_M2.5", r(x), r(y), [], wurzel,
                             sym=libsyms["Mechanical:MountingHole"]))
    for (x, y), text in NOTIZEN:
        teile.append(f'\t(text "{text}" (exclude_from_sim no) (at {r(x)} {r(y)} 0) (effects (font (size 1.524 1.524)) '
                     f'(justify left bottom)) (uuid "{u()}"))\n')

    einzel = sorted(n for n, p in netz_pins.items() if len(p) < 2)
    if einzel:
        raise SystemExit(f"Netze mit nur einem Pin: {einzel}")

    kopf = (f'(kicad_sch\n\t(version 20250114)\n\t(generator "sopho2sip")\n\t(generator_version "1.0")\n'
            f'\t(uuid "{wurzel}")\n\t(paper "A2")\n'
            f'\t(title_block\n\t\t(title "Sopho2SIP-HAT")\n\t\t(rev "0.1")\n\t\t(company "Sopho2SIP")\n'
            f'\t\t(comment 1 "Pi 4 ⇄ ErgoLine D340: RS-232 isoliert, Audio X_OUT/X_IN")\n'
            f'\t\t(comment 2 "Entwurf – Datenblätter vor Fertigung prüfen")\n\t)\n'
            f'\t(lib_symbols\n')
    libteil = "".join("\t\t" + s.replace("\n", "\n\t\t") + "\n" for s in libsyms.values())
    fuss = '\t(sheet_instances\n\t\t(path "/" (page "1"))\n\t)\n\t(embedded_fonts no)\n)\n'
    (HIER / f"{NAME}.kicad_sch").write_text(kopf + libteil + "\t)\n" + "".join(teile) + fuss, encoding="utf-8")

    pro = HIER / f"{NAME}.kicad_pro"
    if not pro.exists():
        pro.write_text('{\n  "meta": {"filename": "%s.kicad_pro", "version": 1},\n  "sheets": [["%s", "Root"]]\n}\n'
                       % (NAME, wurzel), encoding="utf-8")
    (HIER / "netzliste.txt").write_text(
        "# Netz: Pins (erzeugt von erzeuge_schaltplan.py)\n"
        + "".join(f"{n}: {' '.join(sorted(p))}\n" for n, p in sorted(netz_pins.items())), encoding="utf-8")
    print(f"{len(BAUTEILE)} Bauteile, {len(netz_pins)} Netze → {HIER / (NAME + '.kicad_sch')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

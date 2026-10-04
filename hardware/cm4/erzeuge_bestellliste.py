#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bestellliste (Digikey) für den CM4-Träger aus der KiCad-Netzliste.

  hardware/cm4/erzeuge_bestellliste.py   → stueckliste_digikey.csv (für den Digikey-BOM-Manager)

Lagerbestand bei Digikey geprüft am 2026-10-03 für alle aktiven Bauteile und Steckverbinder (Spalte „Bestand“).
Keramikkondensatoren und Widerstände sind Standardteile; deren Bestand schwankt, der BOM-Manager schlägt
gleichwertige Ersatzteile vor (gleicher Wert, Bauform, Dielektrikum, Spannung ≥ angegeben).
"""
from __future__ import annotations

import csv
import pathlib
import re
import subprocess
import tempfile
from collections import defaultdict

HIER = pathlib.Path(__file__).resolve().parent
NAME = "sopho2sip-cm4"

# (Wert, Footprint-Ende) → (Hersteller, Herstellernummer, Digikey-Nummer, Bestand 2026-10-03, Hinweis)
TEILE = {
    ("CM4 Stecker 1", "DF40C-100DS-0.4V_2x50_P0.4mm"): ("Hirose", "DF40C-100DS-0.4V(51)", "H11615CT-ND", "177010", ""),
    ("CM4 Stecker 2", "P0.4mm_Pins101-200"): ("Hirose", "DF40C-100DS-0.4V(51)", "H11615CT-ND", "177010", ""),
    ("USB-C 5V/USB", "USB4105-xx-A_16P_TopMnt_Horizontal"): ("GCT", "USB4105-GF-A", "", "lieferbar", ""),
    ("2A", "Fuse_1812_4532Metric"): ("Bourns", "MF-MSMF200/8X-2", "", "1735", "Polyfuse 2 A, 8 V"),
    ("SMAJ5.0CA", "D_SMA"): ("Diodes", "SMAJ5.0CA-13-F", "SMAJ5.0CA-FDICT-ND", "105326", ""),
    ("USBLC6-2SC6", "SOT-23-6"): ("ST", "USBLC6-2SC6", "497-5235-1-ND", "147782", ""),
    ("AP22804AW5", "SOT-23-5"): ("Diodes", "AP22804AW5-7", "AP22804AW5-7DICT-ND", "121622", ""),
    ("microSD", "DM3AT-SF-PEJM5"): ("Hirose", "DM3AT-SF-PEJM5", "", "lieferbar", ""),
    ("7499010211A", "7499010211A_Horizontal"): ("Würth", "7499010211A", "732-4506-5-ND", "1736", "RJ45 10/100 mit Übertrager"),
    ("TPD4E05U06DQAR", "USON-10_2.5x1.0mm_P0.5mm"): ("TI", "TPD4E05U06DQAR", "", "normalerweise vorrätig", ""),
    ("TLV320AIC3204IRHBR", "EP3.45x3.45mm_ThermalVias"): ("TI", "TLV320AIC3204IRHBR", "296-23775-1-ND", "4894", ""),
    ("12MHz", "ECS_2520MV-xxx-xx-4Pin_2.5x2.0mm"): ("ECS", "ECS-2520MV-120-BN-TR", "XC2749CT-ND", "4500", ""),
    ("AP2112K-3.3", "SOT-23-5"): ("Diodes", "AP2112K-3.3TRG1", "AP2112K-3.3TRG1DICT-ND", "435354", ""),
    ("ADuM5211", "SSOP-20_5.3x7.2mm_P0.65mm"): ("Analog Devices", "ADUM5211ARSZ", "", "10190", ""),
    ("MAX3232E", "SOIC-16_3.9x9.9mm_P1.27mm"): ("TI", "MAX3232EIDR", "296-19752-1-ND", "26175", ""),
    ("D340 PC (4P4C)", "RJ10_Wuerth_615004143821_Horizontal"): ("Würth", "615004143821", "732-3169-ND", "3039",
                                                               "4P4C; Adapterkabel auf DE9 zur D340"),
    ("Raspberry Pi CM4 (z. B. CM4104032)", "CM4_Modul_Platzhalter"): ("Raspberry Pi", "CM4104032", "", "",
                                                                     "Variante wählen: Funk, RAM, eMMC/Lite"),
    ("D340 Audio", "RJ12_Wuerth_615006138421_Horizontal"): ("Würth", "615006138421", "732-2113-ND", "16652", "6P6C"),
    ("SM-LP-5001", "Bourns_SM-LP-5001"): ("Bourns", "SM-LP-5001E", "", "39228", "Übertrager 600:600"),
    ("Taste", "SW_SPST_TL3342"): ("E-Switch", "TL3342F160QG/TR", "EG2531CT-ND", "62116", ""),
    ("Konfig", "SW_SPST_TL3342"): ("E-Switch", "TL3342F160QG/TR", "EG2531CT-ND", "62116", ""),
    ("BSS84", "SOT-23"): ("Diodes", "BSS84-7-F", "", "lieferbar", ""),
    ("Ein/Aus", "SW_SPST_TL3342"): ("E-Switch", "TL3342F160QG/TR", "EG2531CT-ND", "62116", ""),
    ("AO3400A", "SOT-23"): ("Alpha & Omega", "AO3400A", "", "lieferbar", "Lüfterschalter"),
    ("MBR140SFT1G", "D_SOD-123F"): ("onsemi", "MBR140SFT1G", "MBR140SFT1GOSCT-ND", "31972", "Freilaufdiode"),
    ("Lüfter 5 V", "JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical"): ("JST", "B2B-PH-K-S(LF)(SN)", "455-1704-ND", "lieferbar",
                                                            "Gegenstück PHR-2 + Crimpkontakte SPH-002T-P0.5S"),
    ("100", "R_0603_1608Metric"): ("Yageo", "RC0603FR-07100RL", "", "", ""),
    ("100k", "R_0603_1608Metric"): ("Yageo", "RC0603FR-07100KL", "", "", ""),
    ("nRPIBOOT", "PinHeader_1x02_P2.54mm_Vertical"): ("Würth", "61300211121", "", "", "plus Kurzschlussbrücke"),
    ("grün", "LED_0603_1608Metric"): ("Würth", "150060GS75000", "732-4971-1-ND", "lieferbar", ""),
    ("grün ACT", "LED_0603_1608Metric"): ("Würth", "150060GS75000", "732-4971-1-ND", "lieferbar", ""),
    ("gelb", "LED_0603_1608Metric"): ("Würth", "150060YS75000", "", "", ""),
    ("rot PWR", "LED_0603_1608Metric"): ("Würth", "150060RS75000", "", "", ""),
    ("blau", "LED_0603_1608Metric"): ("Würth", "150060BS75000", "732-4966-1-ND", "", ""),
    ("47u", "C_1206_3216Metric"): ("Samsung", "CL31A476MQHNNNE", "1276-1167-1-ND", "1627", "X5R 6,3 V"),
    ("100n", "C_0603_1608Metric"): ("", "Standard 100 nF X7R 50 V 0603", "", "", "z. B. Samsung CL10B104KB8NNNC"),
    ("1u", "C_0603_1608Metric"): ("", "Standard 1 µF X7R 25 V 0603", "", "", ""),
    ("1u", "C_0805_2012Metric"): ("", "Standard 1 µF X7R 50 V 0805", "", "", "Koppelkondensator Sprechweg"),
    ("10u", "C_0805_2012Metric"): ("", "Standard 10 µF X5R 25 V 0805", "", "", "z. B. Samsung CL21A106KAYNNNE"),
    ("330", "R_0603_1608Metric"): ("Yageo", "RC0603FR-07330RL", "", "", ""),
    ("470", "R_0603_1608Metric"): ("Yageo", "RC0603FR-07470RL", "", "", ""),
    ("5k1", "R_0603_1608Metric"): ("Yageo", "RC0603FR-075K1L", "", "", ""),
    ("10k", "R_0603_1608Metric"): ("Yageo", "RC0603FR-0710KL", "", "", ""),
    ("12k", "R_0603_1608Metric"): ("Yageo", "RC0603FR-0712KL", "", "", ""),
    ("0R", "R_0603_1608Metric"): ("Yageo", "RC0603JR-070RL", "", "", ""),
}
NICHT_BESTELLEN = {"DNP", "M2.5", "CM4 M2.5"}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        ziel = pathlib.Path(tmp) / "n.net"
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(ziel),
                        str(HIER / f"{NAME}.kicad_sch")], check=True, capture_output=True)
        s = ziel.read_text(encoding="utf-8").split("(libparts")[0]
    gruppen: dict[tuple, list[str]] = defaultdict(list)
    fehlt = []
    for block in re.split(r"\(comp\s", s)[1:]:
        ref = re.search(r'\(ref "([^"]+)"\)', block).group(1)
        wert = re.search(r'\(value "([^"]*)"\)', block).group(1)
        fp = re.search(r'\(footprint "([^"]*)"\)', block).group(1)
        if wert in NICHT_BESTELLEN:
            continue
        treffer = [v for (w, f), v in TEILE.items() if w == wert and fp.endswith(f)]
        if not treffer:
            fehlt.append(f"{ref} {wert} {fp}")
            continue
        gruppen[(treffer[0], wert, fp.split(":")[1])].append(ref)
    if fehlt:
        raise SystemExit("ohne Bestelldaten: " + ", ".join(fehlt))
    schluessel = lambda r: (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r) or 0))
    zeilen = sorted(((sorted(refs, key=schluessel), d, w, f) for (d, w, f), refs in gruppen.items()),
                    key=lambda z: schluessel(z[0][0]))
    with open(HIER / "stueckliste_digikey.csv", "w", newline="", encoding="utf-8") as datei:
        aus = csv.writer(datei)
        aus.writerow(["Menge", "Referenzen", "Wert", "Hersteller", "Herstellernummer", "Digikey-Nummer",
                      "Bestand 2026-10-03", "Footprint", "Hinweis"])
        for refs, (herst, mpn, dk, bestand, hinweis), w, f in zeilen:
            aus.writerow([len(refs), ",".join(refs), w, herst, mpn, dk, bestand, f, hinweis])
    print(f"{sum(len(z[0]) for z in zeilen)} Bauteile in {len(zeilen)} Positionen → stueckliste_digikey.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

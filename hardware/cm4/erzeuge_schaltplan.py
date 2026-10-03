#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Erzeugt den hierarchischen KiCad-Schaltplan des Sopho2SIP-Trägers für das Raspberry Pi Compute Module 4.

  hardware/cm4/erzeuge_schaltplan.py            → sopho2sip-cm4.kicad_sch (Wurzel) + Blätter, .kicad_pro
  hardware/cm4/erzeuge_schaltplan.py --pruefen  → zusätzlich ERC und Abgleich der Netzliste mit SOLL (alle Blätter)

Wurzelblatt: Funktionsblöcke als hierarchische Blätter, über Blattpins verdrahtet.
  CM4            – beide 100-poligen Stecker, GPIO_VREF, Abblockung, nRPIBOOT-Jumper, Status-LEDs
  Versorgung/USB – USB-C (5 V + USB 2.0 für rpiboot/eMMC-Flashen), Polyfuse, TVS, ESD
  µSD            – Kartensockel für CM4 Lite (Lastschalter wie CM4-Datenblatt, Figure 3)
  Ethernet       – 10/100-MagJack mit LEDs, ESD (wie CM4-Datenblatt, Figure 2)
  Audio-Codec, Sprechweg, RS-232, Bedienung – dieselben Blöcke wie der HAT (hardware/hat/erzeuge_schaltplan.py)
Pinbelegung des CM4: Raspberry Pi „Compute Module 4 Datasheet“ (Tabelle der Pins 1–200), siehe CM4_PINS.
"""
from __future__ import annotations

import pathlib
import sys

HIER = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER.parent / "hat"))
import kicadgen as kg  # noqa: E402
from kicadgen import Blatt  # noqa: E402
import erzeuge_schaltplan as hat  # noqa: E402

NAME = "sopho2sip-cm4"
FP_R, FP_C, FP_C10 = hat.FP_R, hat.FP_C, hat.FP_C10
FP_C47 = "Capacitor_SMD:C_1206_3216Metric"
FP_LED = hat.FP_LED

# ------------------------------------------------------------------------------------------------------------------
# CM4-Pins (Datenblatt „Raspberry Pi Compute Module 4“, Pinout-Tabelle; Stecker 1 = 1–100, Stecker 2 = 101–200)
# ------------------------------------------------------------------------------------------------------------------
CM4_PINS = """
1 GND|2 GND|3 Ethernet_Pair3_P|4 Ethernet_Pair1_P|5 Ethernet_Pair3_N|6 Ethernet_Pair1_N|7 GND|8 GND|
9 Ethernet_Pair2_N|10 Ethernet_Pair0_N|11 Ethernet_Pair2_P|12 Ethernet_Pair0_P|13 GND|14 GND|15 Ethernet_nLED3|
16 Ethernet_SYNC_IN|17 Ethernet_nLED2|18 Ethernet_SYNC_OUT|19 Ethernet_nLED1|20 EEPROM_nWP|21 Pi_nLED_Activity|
22 GND|23 GND|24 GPIO26|25 GPIO21|26 GPIO19|27 GPIO20|28 GPIO13|29 GPIO16|30 GPIO6|31 GPIO12|32 GND|33 GND|
34 GPIO5|35 ID_SC|36 ID_SD|37 GPIO7|38 GPIO11|39 GPIO8|40 GPIO9|41 GPIO25|42 GND|43 GND|44 GPIO10|45 GPIO24|
46 GPIO22|47 GPIO23|48 GPIO27|49 GPIO18|50 GPIO17|51 GPIO15|52 GND|53 GND|54 GPIO4|55 GPIO14|56 GPIO3|57 SD_CLK|
58 GPIO2|59 GND|60 GND|61 SD_DAT3|62 SD_CMD|63 SD_DAT0|64 SD_DAT5|65 GND|66 GND|67 SD_DAT1|68 SD_DAT4|
69 SD_DAT2|70 SD_DAT7|71 GND|72 SD_DAT6|73 SD_VDD_OVERRIDE|74 GND|75 SD_PWR_ON|76 Reserved|77 +5V|78 GPIO_VREF|
79 +5V|80 SCL0|81 +5V|82 SDA0|83 +5V|84 CM4_3.3V|85 +5V|86 CM4_3.3V|87 +5V|88 CM4_1.8V|89 WL_nDisable|
90 CM4_1.8V|91 BT_nDisable|92 RUN_PG|93 nRPIBOOT|94 AnalogIP1|95 PI_LED_nPWR|96 AnalogIP0|97 Camera_GPIO|
98 GND|99 GLOBAL_EN|100 nEXTRST|101 USB_OTG_ID|102 PCIe_CLK_nREQ|103 USB_N|104 Reserved|105 USB_P|
106 Reserved|107 GND|108 GND|109 PCIe_nRST|110 PCIe_CLK_P|111 VDAC_COMP|112 PCIe_CLK_N|113 GND|114 GND|
115 CAM1_D0_N|116 PCIe_RX_P|117 CAM1_D0_P|118 PCIe_RX_N|119 GND|120 GND|121 CAM1_D1_N|122 PCIe_TX_P|
123 CAM1_D1_P|124 PCIe_TX_N|125 GND|126 GND|127 CAM1_C_N|128 CAM0_D0_N|129 CAM1_C_P|130 CAM0_D0_P|131 GND|
132 GND|133 CAM1_D2_N|134 CAM0_D1_N|135 CAM1_D2_P|136 CAM0_D1_P|137 GND|138 GND|139 CAM1_D3_N|140 CAM0_C_N|
141 CAM1_D3_P|142 CAM0_C_P|143 HDMI1_HOTPLUG|144 GND|145 HDMI1_SDA|146 HDMI1_TX2_P|147 HDMI1_SCL|148 HDMI1_TX2_N|
149 HDMI1_CEC|150 GND|151 HDMI0_CEC|152 HDMI1_TX1_P|153 HDMI0_HOTPLUG|154 HDMI1_TX1_N|155 GND|156 GND|
157 DSI0_D0_N|158 HDMI1_TX0_P|159 DSI0_D0_P|160 HDMI1_TX0_N|161 GND|162 GND|163 DSI0_D1_N|164 HDMI1_CLK_P|
165 DSI0_D1_P|166 HDMI1_CLK_N|167 GND|168 GND|169 DSI0_C_N|170 HDMI0_TX2_P|171 DSI0_C_P|172 HDMI0_TX2_N|
173 GND|174 GND|175 DSI1_D0_N|176 HDMI0_TX1_P|177 DSI1_D0_P|178 HDMI0_TX1_N|179 GND|180 GND|181 DSI1_D1_N|
182 HDMI0_TX0_P|183 DSI1_D1_P|184 HDMI0_TX0_N|185 GND|186 GND|187 DSI1_C_N|188 HDMI0_CLK_P|189 DSI1_C_P|
190 HDMI0_CLK_N|191 GND|192 GND|193 DSI1_D2_N|194 DSI1_D3_N|195 DSI1_D2_P|196 DSI1_D3_P|197 GND|198 GND|
199 HDMI0_SDA|200 HDMI0_SCL
"""
PIN = {int(e.split()[0]): e.split()[1] for e in CM4_PINS.replace("\n", "").split("|") if e.strip()}
NR = {}
for n, nm in PIN.items():
    NR.setdefault(nm, []).append(n)
assert sorted(PIN) == list(range(1, 201))


def _e(name: str, typ: str = "bidirectional") -> tuple:
    return (str(NR[name][0]), name, typ)


GPIO_RECHTS = [_e(f"GPIO{i}") for i in range(2, 28)]
J1_LINKS = [_e("GPIO_VREF", "power_in"), None, _e("nRPIBOOT", "input"), None, _e("Pi_nLED_Activity", "open_collector"),
            None, _e("PI_LED_nPWR", "output"), _e("RUN_PG"), _e("GLOBAL_EN", "input"), _e("nEXTRST", "output"),
            _e("WL_nDisable", "input"), _e("BT_nDisable", "input"), _e("EEPROM_nWP", "input"), None,
            _e("SD_PWR_ON", "output"), _e("SD_CLK", "output"), _e("SD_CMD"), _e("SD_DAT0"), _e("SD_DAT1"),
            _e("SD_DAT2"), _e("SD_DAT3"), _e("SD_DAT4"), _e("SD_DAT5"), _e("SD_DAT6"), _e("SD_DAT7"),
            _e("SD_VDD_OVERRIDE", "input"), None,
            _e("Ethernet_Pair0_P"), _e("Ethernet_Pair0_N"), _e("Ethernet_Pair1_P"), _e("Ethernet_Pair1_N"),
            _e("Ethernet_Pair2_P"), _e("Ethernet_Pair2_N"), _e("Ethernet_Pair3_P"), _e("Ethernet_Pair3_N"),
            _e("Ethernet_nLED1", "open_collector"), _e("Ethernet_nLED2", "open_collector"),
            _e("Ethernet_nLED3", "open_collector"), _e("Ethernet_SYNC_IN", "input"), _e("Ethernet_SYNC_OUT", "output"),
            None, _e("AnalogIP0", "input"), _e("AnalogIP1", "input"), _e("Camera_GPIO"), (str(76), "Reserved", "passive"),
            _e("SCL0"), _e("SDA0"), _e("ID_SD"), _e("ID_SC")]


def _gruppe(name, typ, bereich):
    return [(str(n), name, typ) for n in NR[name] if n in bereich]


J1_OBEN = [_gruppe("+5V", "power_in", range(1, 101)), _gruppe("CM4_3.3V", "power_out", range(1, 101)),
           _gruppe("CM4_1.8V", "power_out", range(1, 101))]
J1_UNTEN = [_gruppe("GND", "power_in", range(1, 101))]
_j2_signale = [(str(n), PIN[n], "bidirectional") for n in range(101, 201) if PIN[n] != "GND"]
_usb = [e for e in _j2_signale if e[1] in ("USB_OTG_ID", "USB_N", "USB_P")]
_rest = [e for e in _j2_signale if e not in _usb]
_rest.sort(key=lambda e: (e[1].split("_")[0], e[1]))
J2_LINKS = _usb + [None] + _rest[:len(_rest) // 2 - 2]
J2_RECHTS = _rest[len(_rest) // 2 - 2:]
J2_UNTEN = [_gruppe("GND", "power_in", range(101, 201))]
for teil in (J1_LINKS + GPIO_RECHTS, ):
    pass
_j1 = {e[0] for e in J1_LINKS + GPIO_RECHTS if e} | {e[0] for g in J1_OBEN + J1_UNTEN for e in g}
_j2 = {e[0] for e in J2_LINKS + J2_RECHTS if e} | {e[0] for g in J2_UNTEN for e in g}
assert _j1 == {str(n) for n in range(1, 101)}, set(map(str, range(1, 101))) ^ _j1
assert _j2 == {str(n) for n in range(101, 201)}, set(map(str, range(101, 201))) ^ _j2

DATENBLATT = "https://datasheets.raspberrypi.com/cm4/cm4-datasheet.pdf"
FP_DF40 = "Connector_Hirose_DF40:Hirose_DF40C-100DS-0.4V_2x50_P0.4mm"
kg.EIGENE_SYMBOLE["Sopho2SIP:CM4_Stecker1"] = kg.stecker_symbol(
    "Sopho2SIP:CM4_Stecker1", J1_LINKS, GPIO_RECHTS, J1_UNTEN, J1_OBEN, 45.72, FP_DF40,
    "Raspberry Pi Compute Module 4, Stecker 1 (Pins 1–100)", DATENBLATT)
kg.EIGENE_SYMBOLE["Sopho2SIP:CM4_Stecker2"] = kg.stecker_symbol(
    "Sopho2SIP:CM4_Stecker2", J2_LINKS, J2_RECHTS, J2_UNTEN, [], 45.72, FP_DF40,
    "Raspberry Pi Compute Module 4, Stecker 2 (Pins 101–200)", DATENBLATT)

# Netze der CM4-Pins
GENUTZT = {"Ethernet_Pair0_P": "ETH_P0_P", "Ethernet_Pair0_N": "ETH_P0_N", "Ethernet_Pair1_P": "ETH_P1_P",
           "Ethernet_Pair1_N": "ETH_P1_N", "Ethernet_nLED2": "ETH_nLED2", "Ethernet_nLED3": "ETH_nLED3",
           "SD_CLK": "SD_CLK", "SD_CMD": "SD_CMD", "SD_DAT0": "SD_DAT0", "SD_DAT1": "SD_DAT1", "SD_DAT2": "SD_DAT2",
           "SD_DAT3": "SD_DAT3", "SD_PWR_ON": "SD_PWR_ON",
           "GPIO4": "UART3_TXD", "GPIO5": "UART3_RXD", "GPIO2": "I2C_SDA", "GPIO3": "I2C_SCL",
           "GPIO18": "I2S_BCLK", "GPIO19": "I2S_LRCLK", "GPIO20": "I2S_DIN", "GPIO21": "I2S_DOUT",
           "GPIO23": "LED_TELEFON", "GPIO24": "LED_GESPRAECH", "GPIO25": "TASTE",
           "USB_P": "USB_P", "USB_N": "USB_N",
           "+5V": "+5V", "CM4_3.3V": "+3V3", "GPIO_VREF": "+3V3", "GND": "GND",
           "nRPIBOOT": "nRPIBOOT", "Pi_nLED_Activity": "LED_ACT_K", "PI_LED_nPWR": "LED_PWR_G"}
CM4_SIGNALE = {v for k, v in GENUTZT.items() if v not in kg.POWER and not v.startswith(("nRPI", "LED_ACT", "LED_PWR"))}


def cm4_belegung(bereich) -> dict:
    return {str(n): GENUTZT.get(PIN[n], "NC") for n in bereich}


# ------------------------------------------------------------------------------------------------------------------
# SOLL der neuen Blätter
# ------------------------------------------------------------------------------------------------------------------
SOLL_CM4 = {
    "J11": ("Sopho2SIP:CM4_Stecker1", "CM4 Stecker 1", FP_DF40, cm4_belegung(range(1, 101))),
    "J12": ("Sopho2SIP:CM4_Stecker2", "CM4 Stecker 2", FP_DF40, cm4_belegung(range(101, 201))),
    "C40": ("Device:C", "47u", FP_C47, {"1": "+5V", "2": "GND"}),
    "C41": ("Device:C", "100n", FP_C, {"1": "+5V", "2": "GND"}),
    "JP10": ("Jumper:Jumper_2_Open", "nRPIBOOT", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
             {"1": "nRPIBOOT", "2": "GND"}),
    "R12": ("Device:R", "330", FP_R, {"1": "+3V3", "2": "LED_ACT_A"}),
    "D10": ("Device:LED", "grün ACT", FP_LED, {"2": "LED_ACT_A", "1": "LED_ACT_K"}),
    "Q10": ("Transistor_FET:BSS84", "BSS84", "Package_TO_SOT_SMD:SOT-23", {"1": "LED_PWR_G", "2": "+3V3", "3": "LED_PWR_D"}),
    "R13": ("Device:R", "330", FP_R, {"1": "LED_PWR_D", "2": "LED_PWR_A"}),
    "D11": ("Device:LED", "rot PWR", FP_LED, {"2": "LED_PWR_A", "1": "GND"}),
}
SOLL_VERSORGUNG = {
    "J10": ("Connector:USB_C_Receptacle_USB2.0_16P", "USB-C 5V/USB",
            "Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal",
            {"A4": "VBUS", "A9": "VBUS", "B4": "VBUS", "B9": "VBUS", "A1": "GND", "A12": "GND", "B1": "GND",
             "B12": "GND", "SH": "GND", "A5": "CC1", "B5": "CC2", "A6": "USB_P", "B6": "USB_P", "A7": "USB_N",
             "B7": "USB_N", "A8": "NC", "B8": "NC"}),
    "F1": ("Device:Polyfuse", "2A", "Fuse:Fuse_1812_4532Metric", {"1": "VBUS", "2": "+5V"}),
    "D12": ("Device:D_TVS", "SMAJ5.0CA", "Diode_SMD:D_SMA", {"1": "+5V", "2": "GND"}),
    "R10": ("Device:R", "5k1", FP_R, {"1": "CC1", "2": "GND"}),
    "R11": ("Device:R", "5k1", FP_R, {"1": "CC2", "2": "GND"}),
    "U10": ("Power_Protection:USBLC6-2SC6", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6",
            {"1": "USB_P", "6": "USB_P", "3": "USB_N", "4": "USB_N", "5": "+5V", "2": "GND"}),
    "C42": ("Device:C", "47u", FP_C47, {"1": "+5V", "2": "GND"}),
}
SOLL_SD = {
    "J13": ("Connector:Micro_SD_Card_Det1", "microSD", "Connector_Card:microSD_HC_Hirose_DM3AT-SF-PEJM5",
            {"1": "SD_DAT2", "2": "SD_DAT3", "3": "SD_CMD", "4": "SD_VDD", "5": "SD_CLK", "6": "GND", "7": "SD_DAT0",
             "8": "SD_DAT1", "9": "NC", "SH": "GND"}),
    "U11": ("Power_Management:AP22804AW5", "AP22804AW5", "Package_TO_SOT_SMD:SOT-23-5",
            {"5": "+3V3", "2": "GND", "4": "SD_PWR_ON", "1": "SD_VDD", "3": "NC"}),
    "R14": ("Device:R", "12k", FP_R, {"1": "+3V3", "2": "SD_PWR_ON"}),
    "C43": ("Device:C", "10u", FP_C10, {"1": "SD_VDD", "2": "GND"}),
    "C44": ("Device:C", "100n", FP_C, {"1": "+3V3", "2": "GND"}),
}
SOLL_ETH = {
    "J14": ("Connector:RJ45_Hanrun_HR911105A_Horizontal", "HR911105A", "Connector_RJ:RJ45_Hanrun_HR911105A_Horizontal",
            {"1": "ETH_P0_P", "2": "ETH_P0_N", "3": "ETH_P1_P", "6": "ETH_P1_N", "4": "ETH_CT", "5": "ETH_CT",
             "7": "NC", "8": "GND", "9": "+3V3", "10": "LED_Y_K", "12": "+3V3", "11": "LED_G_K", "SH": "GND"}),
    "U12": ("Power_Protection:TPD4EUSB30", "TPD4EUSB30", "Package_SON:USON-10_2.5x1.0mm_P0.5mm",
            {"1": "ETH_P0_P", "2": "ETH_P0_N", "4": "ETH_P1_P", "5": "ETH_P1_N", "3": "GND", "8": "GND",
             "6": "NC", "7": "NC", "9": "NC", "10": "NC"}),
    "C45": ("Device:C", "100n", FP_C, {"1": "ETH_CT", "2": "GND"}),
    "R15": ("Device:R", "470", FP_R, {"1": "LED_Y_K", "2": "ETH_nLED2"}),
    "R16": ("Device:R", "470", FP_R, {"1": "LED_G_K", "2": "ETH_nLED3"}),
}


# ------------------------------------------------------------------------------------------------------------------
# Zeichnungen der neuen Blätter
# ------------------------------------------------------------------------------------------------------------------
def blatt_cm4(p: Blatt) -> None:
    P, w = p.P, p.w
    p.rahmen_(15, 15, 405, 282, "Compute Module 4")
    X, Y = 160.02, 148.59
    p.setze("J11", X, Y, ref_at=(22.86, -69.85, "right"), wert_at=(22.86, -66.04, "right"))
    p.setze("J12", 330.2, 130.81, ref_at=(-22.86, -52.0, "left"), wert_at=(22.86, -52.0, "right"))
    belegung = p.soll["J11"][3]
    # Signale mit hierarchischen Labels
    for nr, netz in belegung.items():
        if netz in CM4_SIGNALE:
            x, y = P("J11", nr)
            xl = x - 7.62 if x < X else x + 7.62
            w((x, y), (xl, y)); p.lbl(netz, (xl, y), "l" if x < X else "r")
    for nr, netz in p.soll["J12"][3].items():
        if netz in CM4_SIGNALE:
            x, y = P("J12", nr); w((x, y), (x - 7.62, y)); p.lbl(netz, (x - 7.62, y), "l")
    # Versorgung oben: +5V mit Abblockung, CM4_3.3V als +3V3, 1.8 V ungenutzt
    x5, y5 = P("J11", "77")
    w((x5, y5), (x5, y5 - 17.78), (x5 - 38.1, y5 - 17.78))
    p.pw("+5V", (x5 - 38.1, y5 - 17.78))
    for ref, dx in (("C40", 12.7), ("C41", 22.86)):
        p.setze(ref, x5 - dx, y5 - 13.97)
        w(P(ref, "1"), (x5 - dx, y5 - 17.78))
        p.ab(ref, "2", "GND")
    p.auf("J11", "84", "+3V3", 5.08)
    p.offen(("J11", "88"))
    p.ab("J11", NR["GND"][0].__str__(), "GND", 5.08)
    p.ab("J12", "107", "GND", 5.08)
    # GPIO_VREF an +3V3; Boot- und Statuspins über Labels zum Block unten links
    x, y = P("J11", "78"); w((x, y), (x - 7.62, y)); p.pw("+3V3", (x - 7.62, y))
    for nr in ("93", "21", "95"):
        x, y = P("J11", nr); w((x, y), (x - 7.62, y)); p.lbl(belegung[nr], (x - 7.62, y), "l")
    x0, y0 = 50.8, 182.88
    p.text(x0 - 15.24, y0 - 12.7, "Boot und Status", 1.524)
    # nRPIBOOT-Jumper: gesteckt = USB-Boot zum Flashen des eMMC
    p.setze("JP10", x0 + 20.32, y0, rot=180, ref_at=(0, -3.0), wert_at=(0, 3.3))
    xj, yj = P("JP10", "1"); w((xj, yj), (x0 + 38.1, yj)); p.lbl("nRPIBOOT", (x0 + 38.1, yj), "r")
    xj, yj = P("JP10", "2"); w((xj, yj), (xj - 2.54, yj), (xj - 2.54, yj + 2.54)); p.pw("GND", (xj - 2.54, yj + 2.54))
    # Aktivitäts-LED (Pin senkt bis 20 mA): +3V3 → R12 → D10 → Pi_nLED_Activity
    ya = y0 + 15.24
    p.setze("R12", x0 + 7.62, ya, rot=90)
    p.setze("D10", x0 + 20.32, ya, rot=180, ref_at=(0, -3.0), wert_at=(0, 3.3))
    xr, yr = P("R12", "1"); w((xr, yr), (x0, yr)); p.pw("+3V3", (x0, yr))
    w(P("R12", "2"), P("D10", "2"))
    xk, yk = P("D10", "1"); w((xk, yk), (x0 + 38.1, yk)); p.lbl("LED_ACT_K", (x0 + 38.1, yk), "r")
    # Power-LED, gepuffert (Datenblatt): PI_LED_nPWR → Gate BSS84, Source +3V3, Drain → R13 → D11 → GND
    yc = y0 + 35.56
    p.setze("Q10", x0 + 12.7, yc, rot=180, ref_at=(-7.62, -1.27, "right"), wert_at=(-7.62, 1.27, "right"))
    xg, yg = P("Q10", "1"); w((xg, yg), (x0 + 38.1, yg)); p.lbl("LED_PWR_G", (x0 + 38.1, yg), "r")
    xs, ys = P("Q10", "2"); w((xs, ys), (xs, ys - 2.54)); p.pw("+3V3", (xs, ys - 2.54))
    xd, yd = P("Q10", "3")
    p.setze("R13", xd, yd + 5.08)
    p.setze("D11", xd, yd + 16.51, rot=90, ref_at=(3.0, -1.27, "left"), wert_at=(3.0, 1.27, "left"))
    w((xd, yd), P("R13", "1")); w(P("R13", "2"), P("D11", "2"))
    p.ab("D11", "1", "GND")
    p.text(x0 - 15.24, yd + 33.02, "D10 = Aktivität (grün), D11 = Spannung (rot, über Q10 gepuffert)")
    # Unbenutztes
    p.nc_alle("J11"); p.nc_alle("J12")
    p.text(20, 27, "Pinbelegung nach CM4-Datenblatt (Pins 1–200) · GPIO_VREF = 3,3 V · Ethernet 10/100 über Paar 0/1")
    p.text(20, 31, "WLAN/Bluetooth auf dem Modul (CM4 mit Funk): WL_nDisable/BT_nDisable offen = an; "
           "Antenne intern oder U.FL am Modul (dtparam=ant2)")
    p.text(20, 35, "eMMC: CM4 mit eMMC bootet davon; Flashen mit JP10 gesteckt über USB-C (rpiboot). "
           "CM4 Lite: Start von der µSD-Karte (Blatt µSD)")


def blatt_versorgung(p: Blatt) -> None:
    P, w = p.P, p.w
    p.rahmen_(15, 15, 230, 150, "Versorgung und USB")
    p.setze("J10", 60.96, 101.6)
    # VBUS → F1 → +5V mit TVS und Puffer
    xv, yv = P("J10", "A4")
    p.setze("F1", 106.68, yv, rot=90)
    w((xv, yv), P("F1", "1"))
    xf, yf = P("F1", "2"); w((xf, yf), (195.58, yf)); p.pw("+5V", (195.58, yf))
    w((185.42, yf), (185.42, yf - 2.54)); p.flag((185.42, yf - 2.54))
    p.setze("D12", 165.1, yf + 6.35, rot=270, ref_at=(-3.0, -1.27, "right"), wert_at=(-3.0, 1.27, "right"))
    w(P("D12", "1"), (165.1, yf)); p.ab("D12", "2", "GND")
    p.setze("C42", 175.26, yf + 3.81)
    w(P("C42", "1"), (175.26, yf)); p.ab("C42", "2", "GND")
    # CC-Widerstände (Senke, 5,1 kΩ) waagerecht am Pin
    for pin, ref, texte in (("A5", "R10", ((-2.2, -2.54), (2.6, -2.54))), ("B5", "R11", ((-2.2, 2.8), (2.6, 2.8)))):
        xc, yc = P("J10", pin)
        p.setze(ref, xc + 7.62, yc, rot=90, ref_at=texte[0], wert_at=texte[1])
        w((xc, yc), P(ref, "1"))
    # beide an eine gemeinsame Masse
    xr, yr = P("R10", "2"); w((xr, yr), (xr + 5.08, yr)); p.pw("GND", (xr + 5.08, yr), rot=90)
    x2, y2 = P("R11", "2"); w((x2, y2), (x2 + 2.54, y2), (x2 + 2.54, yr))
    # USB 2.0: beide Kontaktreihen zusammenführen, Leitungen zum Blattpin, ESD-Schutz U10 als Abzweig
    for a, b, xs in (("A7", "B7", 78.74), ("A6", "B6", 81.28)):
        xa, ya = P("J10", a); xb, yb = P("J10", b)
        w((xa, ya), (xs, ya), (xs, yb), (xb, yb))
    y_n, y_p = P("J10", "A7")[1], P("J10", "A6")[1]
    w((78.74, y_n), (147.32, y_n)); p.lbl("USB_N", (147.32, y_n), "r")
    w((81.28, y_p), (147.32, y_p)); p.lbl("USB_P", (147.32, y_p), "r")
    p.setze("U10", 127.0, 119.38, ref_at=(-2.54, 5.08, "right"), wert_at=(-2.54, 7.62, "right"))
    for pin, x_ab, y_bus in (("1", 116.84, y_p), ("6", 137.16, y_p), ("3", 114.3, y_n), ("4", 139.7, y_n)):
        xu, yu = P("U10", pin)
        w((x_ab, y_bus), (x_ab, yu), (xu, yu))
    p.auf("U10", "5", "+5V"); p.ab("U10", "2", "GND")
    xg, yg = P("J10", "A1"); w((xg, yg), (xg, yg + 2.54)); p.pw("GND", (xg, yg + 2.54))
    w((xg, yg + 1.27), (xg + 5.08, yg + 1.27)); p.flag((xg + 5.08, yg + 1.27))
    p.ab("J10", "SH", "GND")
    p.offen(("J10", "A8"), ("J10", "B8"))
    p.text(20, 27, "5 V über USB-C (Rd 5,1 kΩ: Senke); dieselbe Buchse dient mit gestecktem nRPIBOOT zum Flashen des eMMC")
    p.text(20, 31, "Strombedarf CM4 bis ~1,4 A + Peripherie: Netzteil mit 5 V/3 A verwenden")


def blatt_sd(p: Blatt) -> None:
    P, w = p.P, p.w
    p.rahmen_(15, 15, 230, 150, "µSD-Karte (nur CM4 Lite)")
    p.setze("J13", 152.4, 81.28)
    for nr in ("1", "2", "3", "4", "5", "7", "8"):
        x, y = P("J13", nr); netz = p.soll["J13"][3][nr]
        if netz == "SD_VDD":
            continue
        w((x, y), (101.6, y)); p.lbl(netz, (101.6, y), "l")
    x, y = P("J13", "6"); w((x, y), (x - 2.54, y)); p.pw("GND", (x - 2.54, y), rot=270)
    p.ab("J13", "SH", "GND")
    p.offen(("J13", "9"))
    # Lastschalter (Datenblatt Figure 3: RT9742; hier AP22804A, gleiche Funktion, EN aktiv hoch)
    p.setze("U11", 71.12, 116.84)
    xo, yo = P("U11", "1"); x4, y4 = P("J13", "4"); w((xo, yo), (109.22, yo), (109.22, y4), (x4, y4))
    p.setze("C43", 91.44, yo + 3.81)
    w(P("C43", "1"), (91.44, yo)); p.ab("C43", "2", "GND")
    xi, yi = P("U11", "5"); yr = yi - 12.7
    w((xi, yi), (60.96, yi), (60.96, yr), (35.56, yr)); p.pw("+3V3", (35.56, yr))
    p.setze("C44", 43.18, yr + 3.81, links=True)
    p.ab("C44", "2", "GND")
    p.setze("R14", 50.8, yr + 3.81)
    xe, ye = P("U11", "4"); w((xe, ye), (33.02, ye)); p.lbl("SD_PWR_ON", (33.02, ye), "l")
    w(P("R14", "2"), (50.8, ye))
    p.ab("U11", "2", "GND")
    p.offen(("U11", "3"))
    p.text(20, 27, "Nur beim CM4 Lite belegt; beim CM4 mit eMMC sind die SD-Pins offen, der Sockel stört nicht")
    p.text(20, 31, "R14 hält den Lastschalter ohne Ansteuerung an (Start von der Karte möglich), wie im CM4-Datenblatt")


def blatt_ethernet(p: Blatt) -> None:
    P, w = p.P, p.w
    p.rahmen_(15, 15, 250, 150, "Ethernet 10/100")
    p.setze("J14", 160.02, 76.2)
    for nr in ("1", "2", "3", "6"):
        x, y = P("J14", nr)
        w((x, y), (55.88, y)); p.lbl(p.soll["J14"][3][nr], (55.88, y), "l")
    # Mittelanzapfungen zusammen über C45 an GND
    x4, y4 = P("J14", "4"); x5, y5 = P("J14", "5")
    w((x4, y4), (x4 - 2.54, y4), (x4 - 2.54, y5)); w((x5, y5), (x5 - 2.54, y5))
    p.setze("C45", x4 - 2.54, y5 + 7.62)
    w((x4 - 2.54, y5), P("C45", "1")); p.ab("C45", "2", "GND")
    # ESD-Schutz U12 als Abzweige der Paare
    p.setze("U12", 93.98, 109.22)
    for nr_j, pin_u, x_ab in (("1", "1", 71.12), ("2", "2", 73.66), ("3", "4", 111.76), ("6", "5", 114.3)):
        y_netz = P("J14", nr_j)[1]
        xu, yu = P("U12", pin_u)
        w((x_ab, y_netz), (x_ab, yu), (xu, yu))
    p.ab("U12", "3", "GND")
    p.offen(("U12", "6"), ("U12", "7"), ("U12", "9"), ("U12", "10"))
    p.ab("J14", "8", "GND"); p.ab("J14", "SH", "GND")
    p.offen(("J14", "7"))
    # LEDs: Anode an +3V3, Kathode über 470 Ω an den Low-aktiven LED-Pin des CM4
    for a, k, r, netz in (("12", "11", "R16", "ETH_nLED3"), ("9", "10", "R15", "ETH_nLED2")):
        xa, ya = P("J14", a); w((xa, ya), (xa + 5.08, ya)); p.pw("+3V3", (xa + 5.08, ya))
        xk, yk = P("J14", k)
        p.setze(r, xk + 15.24, yk, rot=90)
        w((xk, yk), P(r, "1"))
        xr, yr = P(r, "2"); w((xr, yr), (xr + 7.62, yr)); p.lbl(netz, (xr + 7.62, yr), "r")
    p.text(20, 27, "MagJack 1:1 wie CM4-Datenblatt (Figure 2): Mittelanzapfungen über C45 an GND, ESD-Schutz U12, LED 470 Ω")
    p.text(20, 31, "10/100 genügt für VoIP; für Gigabit 4-Paar-MagJack verwenden und Paare 2/3 des CM4 anschließen")
    p.text(190, 92, "LED 12/11: Aktivität (nLED3)")
    p.text(190, 96, "LED 9/10: Link (nLED2)")


# ------------------------------------------------------------------------------------------------------------------
# Wurzelblatt
# ------------------------------------------------------------------------------------------------------------------
def main() -> int:
    alle_hat = hat.SOLL
    blaetter = {
        "cm4": Blatt("CM4", SOLL_CM4, "cm4.kicad_sch", export=CM4_SIGNALE, papier="A3"),
        "versorgung": Blatt("Versorgung", SOLL_VERSORGUNG, "versorgung.kicad_sch", export={"USB_P", "USB_N"}, papier="A3"),
        "sd": Blatt("µSD", SOLL_SD, "sd.kicad_sch", papier="A3",
                    export={"SD_CLK", "SD_CMD", "SD_DAT0", "SD_DAT1", "SD_DAT2", "SD_DAT3", "SD_PWR_ON"}),
        "eth": Blatt("Ethernet", SOLL_ETH, "ethernet.kicad_sch", papier="A3",
                     export={"ETH_P0_P", "ETH_P0_N", "ETH_P1_P", "ETH_P1_N", "ETH_nLED2", "ETH_nLED3"}),
        "codec": Blatt("Audio-Codec", hat.teil_soll("codec"), "codec.kicad_sch", papier="A3", versatz=(-121.92, 0),
                       export={"I2S_BCLK", "I2S_LRCLK", "I2S_DIN", "I2S_DOUT", "I2C_SDA", "I2C_SCL", "HP_L", "LINE_IN"}),
        "sprechweg": Blatt("Sprechweg", hat.teil_soll("sprechweg"), "sprechweg.kicad_sch", papier="A3",
                           versatz=(-257.81, 0), export={"HP_L", "LINE_IN"}),
        "rs232": Blatt("RS-232", hat.teil_soll("rs232"), "rs232.kicad_sch", papier="A3", versatz=(-121.92, -142.24),
                       export={"UART3_TXD", "UART3_RXD"}),
        "bedienung": Blatt("Bedienung", hat.teil_soll("bedienung"), "bedienung.kicad_sch", papier="A3",
                           versatz=(0, -187.96), export={"LED_TELEFON", "LED_GESPRAECH", "TASTE"}),
    }
    blatt_cm4(blaetter["cm4"]); blatt_versorgung(blaetter["versorgung"]); blatt_sd(blaetter["sd"])
    blatt_ethernet(blaetter["eth"]); hat.codec(blaetter["codec"]); hat.sprechweg(blaetter["sprechweg"])
    hat.rs232(blaetter["rs232"]); hat.bedienung(blaetter["bedienung"])
    # Bohrungen: das Raster des HAT gilt hier nicht
    bed = blaetter["bedienung"]
    bed.texte = [(x, y, "H1–H4: Gehäusebefestigung M2,5 (Lage nach Gehäuse); CM4 auf 4 Abstandsbolzen M2,5"
                  if s.startswith("M2,5, Raster") else s, g) for x, y, s, g in bed.texte]
    for b in blaetter.values():
        fehlt = set(b.soll) - {t[0] for t in b.teile}
        if fehlt:
            raise SystemExit(f"{b.name}: nicht platziert: {sorted(fehlt)}")

    root = Blatt("Wurzel", {}, f"{NAME}.kicad_sch", titel="Sopho2SIP-Träger für Compute Module 4",
                 kommentare=("CM4 (eMMC oder Lite mit µSD), WLAN am Modul oder Ethernet, D340-Anbindung wie HAT",
                             "Entwurf – Datenblätter vor Fertigung prüfen"))
    root.rahmen_(15, 15, 405, 250, "Sopho2SIP-Träger für Compute Module 4 – Übersicht")
    # CM4 in der Mitte; Pins rechts zu Ethernet, µSD, Codec, RS-232; links zu Versorgung und Bedienung
    y0 = 45.72
    rechts = ([("ETH_P0_P", 0), ("ETH_P0_N", 1), ("ETH_P1_P", 2), ("ETH_P1_N", 3), ("ETH_nLED2", 4), ("ETH_nLED3", 5)],
              [("SD_CLK", 15), ("SD_CMD", 16), ("SD_DAT0", 17), ("SD_DAT1", 18), ("SD_DAT2", 19), ("SD_DAT3", 20),
               ("SD_PWR_ON", 21)],
              [("I2S_BCLK", 31), ("I2S_LRCLK", 32), ("I2S_DIN", 33), ("I2S_DOUT", 34), ("I2C_SDA", 35), ("I2C_SCL", 36)],
              [("UART3_TXD", 46), ("UART3_RXD", 47)])
    links = ([("USB_P", 0), ("USB_N", 1)], [("LED_TELEFON", 31), ("LED_GESPRAECH", 32), ("TASTE", 33)])
    x_cm4, b_cm4 = 157.48, 50.8
    pins_cm4 = [(n, "r", 7.62 + 2.54 * i) for gruppe in rechts for n, i in gruppe] + \
               [(n, "l", 7.62 + 2.54 * i) for gruppe in links for n, i in gruppe]
    pos_cm4 = root.blatt(blaetter["cm4"], x_cm4, y0, b_cm4, pins_cm4, hoehe=7.62 + 2.54 * 47 + 7.62)
    x_rechts, b_rechts = 248.92, 45.72
    abstand = {}
    for kind, gruppe in (("eth", rechts[0]), ("sd", rechts[1]), ("codec", rechts[2]), ("rs232", rechts[3])):
        top = pos_cm4[gruppe[0][0]][1] - 7.62
        pins = [(n, "l", pos_cm4[n][1] - top) for n, _ in gruppe]
        if kind == "codec":
            pins += [("HP_L", "r", 7.62), ("LINE_IN", "r", 10.16)]
        pos = root.blatt(blaetter[kind], x_rechts, top, b_rechts, pins,
                         hoehe=max(dy for _, _, dy in pins) + 7.62)
        abstand[kind] = pos
        for n, _ in gruppe:
            root.w(pos_cm4[n], pos[n])
    top_s = abstand["codec"]["HP_L"][1] - 7.62
    pos_s = root.blatt(blaetter["sprechweg"], 332.74, top_s, 45.72, [("HP_L", "l", 7.62), ("LINE_IN", "l", 10.16)],
                       hoehe=22.86)
    for n in ("HP_L", "LINE_IN"):
        root.w(abstand["codec"][n], pos_s[n])
    x_links, b_links = 63.5, 45.72
    for kind, gruppe in (("versorgung", links[0]), ("bedienung", links[1])):
        top = pos_cm4[gruppe[0][0]][1] - 7.62
        pins = [(n, "r", pos_cm4[n][1] - top) for n, _ in gruppe]
        pos = root.blatt(blaetter[kind], x_links, top, b_links, pins, hoehe=max(dy for _, _, dy in pins) + 7.62)
        for n, _ in gruppe:
            root.w(pos[n], pos_cm4[n])
    root.text(20, 225, "Speicher: CM4 mit eMMC (Flashen per USB-C, nRPIBOOT-Jumper im Blatt CM4) oder CM4 Lite mit µSD-Karte")
    root.text(20, 230, "Netz: WLAN/Bluetooth des CM4 (Antenne am Modul) oder Ethernet 10/100 (MagJack); beides gleichzeitig möglich")
    root.text(20, 235, "D340: Audio-Codec + Sprechweg (Übertrager, RJ12) und RS-232 (isoliert, UART3) wie beim HAT; "
              "Versorgungsnetze +5V/+3V3/GND global")
    root.text(20, 240, "Erzeugt von hardware/cm4/erzeuge_schaltplan.py; Prüfung --pruefen (ERC + Netzliste gegen SOLL)")

    rootpfad = kg.schreibe_projekt(HIER, NAME, root)
    alle = list(blaetter.values())
    netze = kg.soll_netze(alle)
    (HIER / "netzliste.txt").write_text("# Netz: Pins (SOLL aus erzeuge_schaltplan.py; Blatt/Netz = lokal)\n"
                                        + "".join(f"{n}: {' '.join(v)}\n" for n, v in sorted(netze.items())),
                                        encoding="utf-8")
    teile = sum(len(b.soll) for b in alle)
    print(f"{len(alle)} Blätter, {teile} Bauteile, {len(netze)} Netze → {rootpfad.name}")
    return kg.pruefe_projekt(rootpfad, alle) if "--pruefen" in sys.argv else 0


if __name__ == "__main__":
    raise SystemExit(main())

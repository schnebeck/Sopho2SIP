#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Erzeugt die eigenen Footprints (sopho2sip.pretty) aus den Herstellerzeichnungen.

  hardware/bibliothek/erzeuge_footprints.py

Quellen (Maße aus den Zeichnungen, Abruf 2026-10-03):
  Bourns SM-LP-5001 (https://www.bourns.com/docs/Product-Datasheets/SMLP5001.pdf),
  Würth WR-MJ 615006138421 (https://www.we-online.com/components/products/datasheet/615006138421.pdf).
"""
from __future__ import annotations

import pathlib

HIER = pathlib.Path(__file__).resolve().parent / "sopho2sip.pretty"


def _f(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".")


def linie(x1, y1, x2, y2, lage, breite=0.12) -> str:
    return (f'\t(fp_line (start {_f(x1)} {_f(y1)}) (end {_f(x2)} {_f(y2)}) '
            f'(stroke (width {breite}) (type solid)) (layer "{lage}"))\n')


def rechteck(x1, y1, x2, y2, lage, breite=0.12) -> str:
    return (f'\t(fp_rect (start {_f(x1)} {_f(y1)}) (end {_f(x2)} {_f(y2)}) '
            f'(stroke (width {breite}) (type solid)) (fill no) (layer "{lage}"))\n')


def text(art, wert, x, y, lage, versteckt=False) -> str:
    h = " (hide yes)" if versteckt else ""
    return (f'\t(property "{art}" "{wert}" (at {_f(x)} {_f(y)} 0) (layer "{lage}"){h} '
            f'(effects (font (size 1 1) (thickness 0.15))))\n')


def kopf(name, beschreibung, attr) -> str:
    return (f'(footprint "{name}" (version 20241229) (generator "sopho2sip") (generator_version "1.0") '
            f'(layer "F.Cu")\n\t(descr "{beschreibung}")\n\t(attr {attr})\n')


def smd(nr, x, y, b, h) -> str:
    return (f'\t(pad "{nr}" smd roundrect (at {_f(x)} {_f(y)}) (size {_f(b)} {_f(h)}) '
            f'(layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.15))\n')


def tht(nr, x, y, d, bohrung, form="circle") -> str:
    return (f'\t(pad "{nr}" thru_hole {form} (at {_f(x)} {_f(y)}) (size {_f(d)} {_f(d)}) (drill {_f(bohrung)}) '
            f'(layers "*.Cu" "*.Mask"))\n')


def npth(x, y, d) -> str:
    return (f'\t(pad "" np_thru_hole circle (at {_f(x)} {_f(y)}) (size {_f(d)} {_f(d)}) (drill {_f(d)}) '
            f'(layers "*.Cu" "*.Mask"))\n')


def sm_lp_5001() -> str:
    """Übertrager 600:600. Pads wie Symbol Device:Transformer_1P_1S: 1/2 = Wicklung A (Herstellerpins 1/3),
    4/3 = Wicklung B (Herstellerpins 6/4); Herstellerpins 2 und 5 sind innen nicht beschaltet (Pads ohne Nummer)."""
    name = "Bourns_SM-LP-5001"
    s = kopf(name, "Bourns SM-LP-5001 Übertrager 600:600 SMD, Pads 3,0 × 1,5 mm, Raster 2,54 mm, Reihen 12 mm "
             "(Mitte); Pad 1/2 = Pin 1/3, Pad 4/3 = Pin 6/4", "smd")
    s += text("Reference", "REF**", 0, -6.0, "F.SilkS") + text("Value", name, 0, 6.0, "F.Fab")
    s += text("Footprint", "", 0, 0, "F.Fab", True) + text("Datasheet", "", 0, 0, "F.Fab", True)
    for nr, x, y in (("1", -6.0, -2.54), ("", -6.0, 0.0), ("2", -6.0, 2.54),
                     ("4", 6.0, -2.54), ("", 6.0, 0.0), ("3", 6.0, 2.54)):
        s += smd(nr, x, y, 3.0, 1.5)
    s += rechteck(-6.4, -4.5, 6.4, 4.5, "F.Fab", 0.1)
    s += linie(-4.3, -4.6, 4.3, -4.6, "F.SilkS") + linie(-4.3, 4.6, 4.3, 4.6, "F.SilkS")
    s += linie(-7.8, -3.6, -4.6, -3.6, "F.SilkS")                 # Markierung Pin 1
    s += rechteck(-7.75, -4.75, 7.75, 4.75, "F.CrtYd", 0.05)
    return s + ")\n"


def rj12_wuerth_615006138421() -> str:
    """6P6C liegend, Lasche oben. Ursprung = Pin 1; Steckseite bei y = +10,8 (Platinenkante)."""
    name = "RJ12_Wuerth_615006138421_Horizontal"
    s = kopf(name, "Würth WR-MJ 615006138421, 6P6C liegend, THT, Steckseite zur Platinenkante (y = +10,8 mm)",
             "through_hole")
    s += text("Reference", "REF**", -2.55, -3.4, "F.SilkS") + text("Value", name, -2.55, 12.2, "F.Fab")
    s += text("Footprint", "", 0, 0, "F.Fab", True) + text("Datasheet", "", 0, 0, "F.Fab", True)
    for i in range(6):
        x = -1.02 * i
        y = 0.0 if i % 2 == 0 else 2.54
        s += tht(str(i + 1), x, y, 1.5, 0.9, "rect" if i == 0 else "circle")
    s += npth(-8.55, 4.84, 2.36) + npth(3.45, 4.84, 2.36)
    s += rechteck(-8.55, -2.2, 3.45, 10.8, "F.Fab", 0.1)
    s += linie(-8.67, -2.32, 3.57, -2.32, "F.SilkS") + linie(-8.67, -2.32, -8.67, 3.2, "F.SilkS")
    s += linie(3.57, -2.32, 3.57, 3.2, "F.SilkS")
    s += rechteck(-9.95, -2.7, 4.85, 11.3, "F.CrtYd", 0.05)
    s += linie(-8.55, 10.8, 3.45, 10.8, "Dwgs.User", 0.1)        # Steckseite / Platinenkante
    return s + ")\n"


def df40_stecker2() -> None:
    """KiCad-Footprint Hirose DF40C-100DS mit Padnummern 101–200 (zweiter CM4-Stecker, Symbol CM4_Stecker2)."""
    import pcbnew
    fp = pcbnew.FootprintLoad("/usr/share/kicad/footprints/Connector_Hirose_DF40.pretty",
                              "Hirose_DF40C-100DS-0.4V_2x50_P0.4mm")
    for pad in fp.Pads():
        if pad.GetNumber().isdigit():
            pad.SetNumber(str(int(pad.GetNumber()) + 100))
    name = "Hirose_DF40C-100DS-0.4V_2x50_P0.4mm_Pins101-200"
    fp.SetFPID(pcbnew.LIB_ID("Sopho2SIP", name))
    fp.SetLibDescription("Hirose DF40C-100DS-0.4V(51), Padnummern 101–200 für den zweiten CM4-Stecker "
                         "(sonst wie Connector_Hirose_DF40:Hirose_DF40C-100DS-0.4V_2x50_P0.4mm)")
    pcbnew.FootprintSave(str(HIER), fp)
    print(f"{name}.kicad_mod")


def main() -> int:
    HIER.mkdir(parents=True, exist_ok=True)
    df40_stecker2()
    for f in (sm_lp_5001, rj12_wuerth_615006138421):
        s = f()
        name = s.split('"')[1]
        (HIER / f"{name}.kicad_mod").write_text(s, encoding="utf-8")
        print(f"{name}.kicad_mod")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

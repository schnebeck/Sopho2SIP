#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Querschnitte durch Taster, LED und Schraubsäule (schnitte.json aus freecad_gehaeuse.py) → vorschau_schnitte.png.
Braucht matplotlib."""
from __future__ import annotations

import json
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HIER = pathlib.Path(__file__).resolve().parent


def schnittbild():
    """Querschnitte (aus freecad_gehaeuse.py): Taster mit Stößel, LED mit Lichtleiter, Schraubsäule."""
    daten = json.loads((HIER / "schnitte.json").read_text())
    farben = {"unterschale": "#7a8088", "deckel": "#3d434c", "lichtleiter": "#4aa3df", "platine": "#2e8b57"}
    titel = {"SW1": "Schnitt durch Taster SW1", "D1": "Schnitt durch LED D1", "H3": "Schnitt durch Schraubsäule H3"}
    fig, achsen = plt.subplots(3, 1, figsize=(12, 11), dpi=110)
    for ax, (ref, s) in zip(achsen, daten.items()):
        for art, pkt in s["linien"]:
            p = np.array(pkt)
            ax.fill(p[:, 0], p[:, 1], color=farben[art], alpha=0.85 if art != "platine" else 0.6, lw=0)
        ax.set_aspect("equal")
        ax.set_xlim(50, 92)
        ax.set_ylim(-7, 21)
        ax.set_title(f"{titel[ref]} (x = {s['x']:.1f} mm, Blick von links; y nach vorn)", fontsize=10)
        ax.grid(alpha=0.3)
    handles = [plt.Rectangle((0, 0), 1, 1, color=f) for f in farben.values()]
    fig.legend(handles, ["Unterschale", "Deckel", "Lichtleiter", "Platine/Bauteile"], loc="lower center", ncol=4)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(HIER / "vorschau_schnitte.png")


def main() -> int:
    schnittbild()
    print("vorschau_schnitte.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

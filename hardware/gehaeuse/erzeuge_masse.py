#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Maße für das Gehäuse aus der Platine: Bauteillagen relativ zur linken hinteren Platinenecke → masse.json,
dazu die bestückte Platine als STEP (für die Kollisionsprüfung im Gehäuse-Skript).

  hardware/gehaeuse/erzeuge_masse.py        (danach: freecad_gehaeuse.py, siehe README)
"""
from __future__ import annotations

import json
import pathlib
import subprocess

import pcbnew

HIER = pathlib.Path(__file__).resolve().parent
PLATINE = HIER.parent / "cm4" / "sopho2sip-cm4.kicad_pcb"
REFS = ("J2", "J3", "J10", "J13", "J14", "J15", "JP10", "M1", "SW1", "SW2", "SW3", "D1", "D2", "D3", "D10", "D11",
        "H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8")


def main() -> int:
    board = pcbnew.LoadBoard(str(PLATINE))
    bb = board.GetBoardEdgesBoundingBox()
    x0, y0 = round(pcbnew.ToMM(bb.GetLeft()) + 0.05, 2), round(pcbnew.ToMM(bb.GetTop()) + 0.05, 2)
    masse = {"platine": {"breite": round(pcbnew.ToMM(bb.GetWidth()) - 0.1, 2),
                         "tiefe": round(pcbnew.ToMM(bb.GetHeight()) - 0.1, 2),
                         "dicke": round(pcbnew.ToMM(board.GetDesignSettings().GetBoardThickness()), 2)},
             "bauteile": {}}
    for fp in board.GetFootprints():
        if fp.GetReference() in REFS:
            p = fp.GetPosition()
            masse["bauteile"][fp.GetReference()] = {"x": round(pcbnew.ToMM(p.x) - x0, 3),
                                                    "y": round(pcbnew.ToMM(p.y) - y0, 3),
                                                    "drehung": round(fp.GetOrientationDegrees())}
    (HIER / "masse.json").write_text(json.dumps(masse, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    step = HIER / "platine_bestueckt.step"
    if not step.exists() or step.stat().st_mtime < PLATINE.stat().st_mtime:   # Export dauert ~5 min
        subprocess.run(["kicad-cli", "pcb", "export", "step", "--subst-models", "--force", "--user-origin",
                        f"{x0}x{y0}mm", "-o", str(step), str(PLATINE)], check=True, capture_output=True)
    print(f"masse.json ({len(masse['bauteile'])} Bauteile), {step.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

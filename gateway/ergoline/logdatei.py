# SPDX-License-Identifier: GPL-3.0-or-later
"""Rohdaten mit Zeitstempel aus Mitschnitten lesen (serial_probe-, ergo- und test-Logs)."""
from __future__ import annotations

import ast
import datetime as dt
import pathlib
import re

ZEILE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) (<<|>>) raw (b'.*'|b\".*\")$")


def rohdaten(pfad: str | pathlib.Path) -> list[tuple[float, str, bytes]]:
    """Liste (Unix-Zeit, Richtung '<<' oder '>>', Bytes) in Dateireihenfolge."""
    out = []
    for zeile in pathlib.Path(pfad).read_text(encoding="utf-8", errors="replace").splitlines():
        m = ZEILE.match(zeile)
        if m:
            t = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f").timestamp()
            out.append((t, m.group(2), ast.literal_eval(m.group(3))))
    return out

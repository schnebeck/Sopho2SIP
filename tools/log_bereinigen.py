#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mitschnitt für das öffentliche Repo bereinigen: echte Rufnummer durch den Platzhalter ersetzen.

  tools/log_bereinigen.py QUELLE ZIEL NUMMER [--von HH:MM:SS] [--bis HH:MM:SS] [--titel TEXT]

NUMMER ohne Amtsholung (z. B. 0171…); ersetzt wird durch 0170… gleicher Länge (Platzhalter 01700000000).
Die Nummer kann über mehrere Rohzeilen (<< raw) verteilt sein: Rohbytes werden je Richtung als Strom bereinigt
und wieder auf die Originalzeilen verteilt. Ersetzt werden ASCII, Hex-Darstellung (\"30 31 …\") und Rohbytes.
Bricht ab, wenn danach noch ein Teil der Nummer (letzte 6 Ziffern) im Ergebnis steht.
"""
import argparse
import ast
import pathlib
import re
import sys

RAW = re.compile(r"^(.{23} (<<|>>) raw )(b'.*'|b\".*\")$")


def platzhalter(nummer: str) -> str:
    return ("01700000000" + "0" * len(nummer))[:len(nummer)]


def bereinige(zeilen: list[str], echt: bytes, ersatz: bytes) -> list[str]:
    zeilen = list(zeilen)
    for richtung in ("<<", ">>"):
        idx = [i for i, z in enumerate(zeilen) if (m := RAW.match(z)) and m.group(2) == richtung]
        stuecke = [ast.literal_eval(RAW.match(zeilen[i]).group(3)) for i in idx]
        strom = b"".join(stuecke).replace(echt, ersatz)
        pos = 0
        for i, s in zip(idx, stuecke):
            zeilen[i] = RAW.match(zeilen[i]).group(1) + repr(strom[pos:pos + len(s)])
            pos += len(s)
    hx_echt, hx_ersatz = echt.hex(" "), ersatz.hex(" ")
    return [z if RAW.match(z) else z.replace(hx_echt, hx_ersatz).replace(echt.decode(), ersatz.decode())
            for z in zeilen]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("quelle")
    ap.add_argument("ziel")
    ap.add_argument("nummer")
    ap.add_argument("--von", default="00:00:00")
    ap.add_argument("--bis", default="99:99:99")
    ap.add_argument("--titel", default="")
    a = ap.parse_args()
    if not a.nummer.isdigit():
        sys.exit("NUMMER nur aus Ziffern")
    alle = pathlib.Path(a.quelle).read_text(encoding="utf-8").splitlines()
    kopf = [z for z in alle if z.startswith("# ") and " Port " in z][:1]
    teil = [z for z in alle if not z.startswith("# ") and a.von <= z[11:19] <= a.bis
            or z.startswith("# ") and a.von <= z[13:21] <= a.bis]
    echt = a.nummer.encode()
    teil = bereinige(teil, echt, platzhalter(a.nummer).encode())
    titel = f"# Auszug aus {pathlib.Path(a.quelle).name}, Rufnummer ersetzt" + (f": {a.titel}" if a.titel else "")
    text = "\n".join([titel] + kopf + teil) + "\n"
    rest = echt[-6:]
    if rest.decode() in text or rest.hex(" ") in text or rest.decode() in repr(text):
        sys.exit("!! Nummer noch enthalten, nichts geschrieben")
    pathlib.Path(a.ziel).write_text(text, encoding="utf-8")
    print(f"{len(teil)} Zeilen → {a.ziel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

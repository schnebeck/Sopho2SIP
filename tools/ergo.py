#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Testwerkzeug für das Rahmenprotokoll der ErgoLine D340 (siehe docs/protocol.md, docs/testplan.md).

Frei (ändern keinen Gesprächszustand):
  ergo.py decode LOG...                 alte Mitschnitte offline dekodieren
  ergo.py listen   [--dauer S]          nur mitlesen
  ergo.py anmelden [--dauer S]          01 02 01 00 senden, Quittung abwarten, dann mitlesen
  ergo.py keepalive                     01 02 00 00 senden, Quittung abwarten

Nur mit --freigabe (Anruf wird ausgelöst/beeinflusst; CLAUDE.md: vorher Nutzer fragen):
  ergo.py belegen | annehmen | auflegen --freigabe
  ergo.py waehlen NUMMER --freigabe     Nummer inkl. Amtsholung (extern: 01…)
  ergo.py roh "01 02 00 00" --freigabe  beliebiger Rahmen

Optionen: --port, --paritaet O|N (Standard O = 8O1 wie im Treiber), --xonxoff, --dauer
"""
import argparse
import ast
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "gateway"))
from ergoline import protocol as p  # noqa: E402

FREI = {"decode", "listen", "anmelden", "keepalive"}


def lese_log(pfad: pathlib.Path) -> dict[str, bytes]:
    """Bytes je Richtung aus serial_probe-, ergo- und bitbang-Logs."""
    rx, tx = bytearray(), bytearray()
    for zeile in pfad.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.search(r"(<<|>>) raw (b'.*'|b\".*\")$", zeile)
        if m:
            (rx if m.group(1) == "<<" else tx).extend(ast.literal_eval(m.group(2)))
            continue
        m = re.match(r"RX @\s*\d+ \(\+\s*[\d.]+ s\)\s+0x([0-9a-f]{2})", zeile)
        if m:
            rx.append(int(m.group(1), 16))
    return {"<<": bytes(rx), ">>": bytes(tx)}


def decode(pfade: list[str]) -> int:
    for pfad in map(pathlib.Path, pfade):
        print(f"== {pfad}")
        for richtung, daten in lese_log(pfad).items():
            if not daten:
                continue
            asm = p.Assembler()
            try:
                for r in asm.feed(daten):
                    print(f"  {richtung} {r.hex():40} {r.beschreibung()}")
            except ValueError as e:
                print(f"  {richtung} kein Rahmenstrom: {e}")
                continue
            if asm.rest:
                print(f"  {richtung} unvollständiger Rest: {asm.rest.hex(' ')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("befehl", choices=sorted(FREI | {"belegen", "annehmen", "auflegen", "waehlen", "roh"}))
    ap.add_argument("argumente", nargs="*")
    ap.add_argument("--port", default=None)
    ap.add_argument("--paritaet", choices=["O", "N", "E"], default="O")
    ap.add_argument("--xonxoff", action="store_true")
    ap.add_argument("--dauer", type=float, default=10.0, help="Mitlesen danach (s)")
    ap.add_argument("--freigabe", action="store_true", help="Nutzerfreigabe für gesprächsrelevante Rahmen")
    a = ap.parse_args()

    if a.befehl == "decode":
        return decode(a.argumente)
    if a.befehl not in FREI and not a.freigabe:
        sys.exit(f"'{a.befehl}' beeinflusst Gespräche: nur mit --freigabe (vorher Nutzer fragen)")

    rahmen = None
    if a.befehl == "anmelden":
        rahmen = p.anmelden()
    elif a.befehl == "keepalive":
        rahmen = p.keepalive()
    elif a.befehl in ("belegen", "annehmen", "auflegen"):
        rahmen = getattr(p, a.befehl)()
    elif a.befehl == "waehlen":
        if len(a.argumente) != 1:
            sys.exit("waehlen braucht genau eine Nummer")
        rahmen = p.waehlen(a.argumente[0])
    elif a.befehl == "roh":
        roh = bytes.fromhex(" ".join(a.argumente))
        teile = p.Assembler().feed(roh)
        if len(teile) != 1 or teile[0].to_bytes() != roh:
            sys.exit(f"kein einzelner gültiger Rahmen: {roh.hex(' ')}")
        rahmen = teile[0]

    from ergoline.link import PORT_STANDARD, ErgoLink
    with ErgoLink(a.port or PORT_STANDARD, paritaet=a.paritaet, xonxoff=a.xonxoff) as link:
        if rahmen is not None:
            q = link.sende(rahmen)
            if q is None:
                print("!! keine Quittung")
            elif q.klasse != p.ACK:
                print(f"!! Antwort ist keine Bestätigung: {q.beschreibung()}")
        link.lausche(a.dauer if a.befehl != "keepalive" else 2.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

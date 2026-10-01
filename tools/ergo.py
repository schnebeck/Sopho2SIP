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
  ergo.py waehltest NUMMER --freigabe [--warte S] [--gespraech S]
                                        anmelden, belegen, wählen, auf Verbindung warten, S s halten, auflegen
  ergo.py annahmetest --freigabe [--gespraech S]
                                        anmelden, auf Anruf warten, annehmen, S s halten, auflegen

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


def warte_auf(link, typ: str, sekunden: float):
    """Wartet auf eine Meldung des Typs (Name aus MELDUNGSTYP); liefert den Rahmen oder None."""
    import queue, time
    ende = time.time() + sekunden
    while time.time() < ende:
        try:
            _, r = link.rahmen.get(timeout=max(0.05, ende - time.time()))
        except queue.Empty:
            break
        if r.klasse == p.MELDUNG and p.MELDUNGSTYP.get(r.typ) == typ:
            return r
    return None


def warte_auf_eins(link, typen: set[str], sekunden: float) -> str | None:
    """Wartet auf die erste Meldung aus typen; liefert deren Namen oder None."""
    import queue, time
    ende = time.time() + sekunden
    while time.time() < ende:
        try:
            _, r = link.rahmen.get(timeout=max(0.05, ende - time.time()))
        except queue.Empty:
            break
        if r.klasse == p.MELDUNG and p.MELDUNGSTYP.get(r.typ) in typen:
            return p.MELDUNGSTYP[r.typ]
    return None


def waehltest(a, link, nummer: str) -> int:
    """Wie der Treiber bei lineMakeCall: anmelden, belegen (11), auf ACK warten, wählen (19). Danach auf Verbindung
    warten, a.gespraech s halten, auflegen. Bei fehlender Quittung Abbruch; aufgelegt wird in jedem Fall."""
    wahl = p.waehlen(nummer)                       # prüft die Nummer vor jedem Senden
    with link:
        if (q := link.sende(p.anmelden())) is None or q.klasse != p.ACK:
            link.notiz("Anmelden fehlgeschlagen, Abbruch")
            return 1
        link.lausche(1)
        q = link.sende(p.belegen())
        if q is None or q.klasse != p.ACK:
            link.notiz(f"Belegen nicht quittiert ({q.beschreibung() if q else 'nichts'}), Abbruch")
            return 1
        ende = None
        try:
            link.notiz(f"Wählton: {warte_auf_eins(link, {'DIALTONE'}, 3) or 'keine Meldung binnen 3 s'}")
            q = link.sende(wahl)
            if q is None or q.klasse != p.ACK:
                link.notiz(f"Wählen nicht quittiert ({q.beschreibung() if q else 'nichts'})")
                return 1
            ende = warte_auf_eins(link, {"CONNECTED", "BUSY", "DISCONNECTED", "RELEASED"}, a.warte)
            if ende == "CONNECTED":
                link.notiz(f"verbunden, Gespräch {a.gespraech:.0f} s")
                if a.nach_verbindung:
                    link.lausche(1)
                    q = link.sende(a.nach_verbindung)
                    link.notiz(f"Zusatzrahmen: {q.beschreibung() if q else 'keine Quittung'}")
                ende = warte_auf_eins(link, {"DISCONNECTED", "RELEASED"}, a.gespraech)
            link.notiz(f"Zustand vor dem Auflegen: {ende or 'Zeit abgelaufen'}")
        finally:
            if ende != "RELEASED":
                q = link.sende(p.auflegen())
                if q is None or q.klasse != p.ACK:
                    link.notiz("Auflegen nicht quittiert")
                if warte_auf_eins(link, {"RELEASED"}, 5) is None:
                    link.notiz("keine RELEASED-Meldung nach Auflegen")
            link.lausche(3)
    return 0


def annahmetest(a, link) -> int:
    with link:
        if (q := link.sende(p.anmelden())) is None or q.klasse != p.ACK:
            link.notiz("Anmelden fehlgeschlagen, Abbruch")
            return 1
        link.notiz(f"Warte bis {a.warte:.0f} s auf einen Anruf …")
        if warte_auf(link, "RINGING", a.warte) is None:
            link.notiz("kein Anruf, Abbruch")
            return 1
        q = link.sende(p.annehmen())
        if q is None or q.klasse != p.ACK:
            link.notiz("Annehmen nicht quittiert, Abbruch")
            return 1
        if warte_auf(link, "CONNECTED", 5) is None:
            link.notiz("keine CONNECTED-Meldung nach Annehmen")
        link.notiz(f"Gespräch {a.gespraech:.0f} s")
        link.lausche(a.gespraech)
        q = link.sende(p.auflegen())
        if q is None or q.klasse != p.ACK:
            link.notiz("Auflegen nicht quittiert")
        if warte_auf(link, "RELEASED", 5) is None:
            link.notiz("keine RELEASED-Meldung nach Auflegen")
        link.lausche(3)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("befehl", choices=sorted(FREI | {"belegen", "annehmen", "auflegen", "waehlen", "roh", "annahmetest", "waehltest"}))
    ap.add_argument("argumente", nargs="*")
    ap.add_argument("--port", default=None)
    ap.add_argument("--paritaet", choices=["O", "N", "E"], default="O")
    ap.add_argument("--xonxoff", action="store_true")
    ap.add_argument("--dauer", type=float, default=10.0, help="Mitlesen danach (s)")
    ap.add_argument("--freigabe", action="store_true", help="Nutzerfreigabe für gesprächsrelevante Rahmen")
    ap.add_argument("--gespraech", type=float, default=10.0, help="annahmetest: Gesprächsdauer (s)")
    ap.add_argument("--warte", type=float, default=120.0, help="annahmetest: max. Wartezeit auf Anruf (s)")
    ap.add_argument("--nach-verbindung", metavar="HEX",
                    help="waehltest: diesen Rahmen 1 s nach CONNECTED senden (z. B. '01 03 26 00 4f'; Freigabe!)")
    a = ap.parse_args()

    if a.befehl == "decode":
        return decode(a.argumente)
    if a.nach_verbindung:
        roh = bytes.fromhex(a.nach_verbindung)
        teile = p.Assembler().feed(roh)
        if len(teile) != 1 or teile[0].to_bytes() != roh:
            sys.exit(f"--nach-verbindung: kein einzelner gültiger Rahmen: {roh.hex(' ')}")
        a.nach_verbindung = teile[0]
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
    if a.befehl == "waehltest":
        if len(a.argumente) != 1:
            sys.exit("waehltest braucht genau eine Nummer")
        return waehltest(a, ErgoLink(a.port or PORT_STANDARD, paritaet=a.paritaet, xonxoff=a.xonxoff), a.argumente[0])
    if a.befehl == "annahmetest":
        return annahmetest(a, ErgoLink(a.port or PORT_STANDARD, paritaet=a.paritaet, xonxoff=a.xonxoff))
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

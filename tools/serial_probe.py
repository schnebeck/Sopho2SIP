#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Serielle Testsonde für die PC-Schnittstelle der ErgoLine D340 / Octophon 340i.

Sendet optional freigegebene Befehle und protokolliert danach alle Meldungen
mit Zeitstempel nach logs/. Riskante Befehle (Anruf, Annehmen, Auslösen ...)
werden nur mit --allow-call-control gesendet.

Beispiele:
  ./serial_probe.py --port /dev/serial/by-id/usb-FTDI_... ATI0
  ./serial_probe.py --port ... ATI0 'AT$STA1'          # danach Anruf auslösen und beobachten
  ./serial_probe.py --port ... --listen-only
"""
import argparse
import datetime as dt
import pathlib
import sys
import time

import serial

SAFE = {"ATI0", "AT$STA0", "AT$STA1",
        "AT", "ATI", "ATI1"}  # reine Abfragen, vom Nutzer am 2026-09-29 freigegeben
# Anrufsteuerung: nur mit --allow-call-control und nach Freigabe durch den Nutzer.
# Alles, was weder SAFE ist noch mit einem dieser Präfixe beginnt, wird immer abgelehnt.
CALL_CONTROL = ("AT$CAL", "AT$ANS", "AT$REL", "AT$RED", "AT$TRA", "AT$CON", "AT$ALT", "AT$RET")
LOGDIR = pathlib.Path(__file__).resolve().parent.parent / "logs"


def ts() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--eol", choices=["cr", "crlf"], default="cr")
    ap.add_argument("--listen-only", action="store_true")
    ap.add_argument("--duration", type=float, default=0,
                    help="nach N Sekunden Lauschen beenden (0 = bis Strg+C)")
    ap.add_argument("--allow-call-control", action="store_true",
                    help="erlaubt Befehle außer ATI0/AT$STA0/AT$STA1")
    ap.add_argument("commands", nargs="*")
    a = ap.parse_args()

    for c in a.commands:
        u = c.upper()
        if u in SAFE:
            continue
        if not u.startswith(CALL_CONTROL):
            sys.exit(f"Befehl {c!r} ist unbekannt und wird nie gesendet")
        if not a.allow_call_control:
            sys.exit(f"Befehl {c!r} ist nicht freigegeben (--allow-call-control)")

    eol = b"\r" if a.eol == "cr" else b"\r\n"
    LOGDIR.mkdir(exist_ok=True)
    logfile = LOGDIR / f"serial_{dt.datetime.now():%Y%m%d_%H%M%S}.log"

    with serial.Serial(a.port, a.baud, bytesize=8, parity="N", stopbits=1,
                       timeout=0.1, xonxoff=False, rtscts=False, dsrdtr=False) as s, \
            open(logfile, "x", encoding="utf-8") as log:

        def out(line: str) -> None:
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()

        out(f"# {ts()} Port {a.port} {a.baud} 8N1 eol={a.eol}")
        buf = b""

        def pump(duration: float) -> None:
            nonlocal buf
            end = time.time() + duration
            while time.time() < end:
                data = s.read(256)
                if not data:
                    continue
                log.write(f"{ts()} << raw {data!r}\n")
                log.flush()
                buf += data
                while True:
                    idx = min((i for i in (buf.find(b"\r"), buf.find(b"\n")) if i >= 0), default=-1)
                    if idx < 0:
                        break
                    line, buf = buf[:idx], buf[idx + 1:]
                    if line:
                        out(f"{ts()} << {line!r}")

        if not a.listen_only:
            for c in a.commands:
                raw = c.encode("ascii") + eol
                out(f"{ts()} >> {raw!r}")
                s.write(raw)
                pump(1.5)

        out(f"# {ts()} Lausche ... (Strg+C beendet), Log: {logfile}")
        stop = time.time() + a.duration if a.duration else float("inf")
        try:
            while time.time() < stop:
                pump(1.0)
                if buf and s.in_waiting == 0:
                    out(f"{ts()} << (unvollständig) {buf!r}")
                    buf = b""
        except KeyboardInterrupt:
            pass
        out(f"# {ts()} Ende")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

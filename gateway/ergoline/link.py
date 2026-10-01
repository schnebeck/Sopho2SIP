# SPDX-License-Identifier: GPL-3.0-or-later
"""Serielle Verbindung zur ErgoLine D340: Lesethread, Senden mit Quittung, Sitzungslog.

Jede Sitzung schreibt nach logs/ergo_<zeit>.log: Rohbytes (<< raw / >> raw) und dekodierte Rahmen.
"""
from __future__ import annotations

import datetime as dt
import os
import pathlib
import queue
import threading
import time

import serial

from .protocol import QUITTUNGEN, Assembler, Rahmen

PORT_STANDARD = "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A97WEQGD-if00-port0"
LOGDIR = pathlib.Path(__file__).resolve().parents[2] / "logs"


def ts() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


class ErgoLink:
    """Verbindung mit 1200 Baud 8O1 (Treiber-Einstellung). Xon/Xoff standardmäßig aus, damit
    Bytes 0x11/0x13 in Rahmen nicht als Flusssteuerung verschluckt werden."""

    def __init__(self, port: str = PORT_STANDARD, baud: int = 1200, paritaet: str = "O",
                 xonxoff: bool = False, echo=print) -> None:
        self.port, self.baud, self.paritaet, self.xonxoff = port, baud, paritaet, xonxoff
        self.echo = echo
        self.rahmen: queue.Queue[tuple[float, Rahmen]] = queue.Queue()
        self._quittung: queue.Queue[Rahmen] = queue.Queue()
        self._stop = threading.Event()
        self._asm = Assembler()
        self._ser = None
        self._log = None
        self._thread = None

    # --- Lebenszyklus ---------------------------------------------------------------------------
    def __enter__(self) -> "ErgoLink":
        LOGDIR.mkdir(exist_ok=True)
        self.logfile = LOGDIR / f"ergo_{dt.datetime.now():%Y%m%d_%H%M%S}.log"
        # O_APPEND, damit logrotate (copytruncate) die Datei kürzen kann, ohne dass Nullbytes entstehen
        fd = os.open(self.logfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND, 0o644)
        self._log = os.fdopen(fd, "w", encoding="utf-8")
        self._ser = serial.Serial(self.port, self.baud, bytesize=8, parity=self.paritaet, stopbits=1,
                                  timeout=0.05, xonxoff=self.xonxoff, rtscts=False, dsrdtr=False)
        self.notiz(f"Port {self.port} {self.baud} 8{self.paritaet}1 xonxoff={self.xonxoff}")
        self._thread = threading.Thread(target=self._leser, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        if self._ser:
            self._ser.close()
        self.notiz(f"Ende, Log: {self.logfile}")
        self._log.close()

    # --- Protokollierung ------------------------------------------------------------------------
    def _schreibe(self, zeile: str, anzeigen: bool = True) -> None:
        self._log.write(zeile + "\n")
        self._log.flush()
        if anzeigen and self.echo:
            if self.echo is print:
                print(zeile, flush=True)
            else:
                self.echo(zeile)

    def notiz(self, text: str) -> None:
        self._schreibe(f"# {ts()} {text}")

    # --- Empfang --------------------------------------------------------------------------------
    def _leser(self) -> None:
        while not self._stop.is_set():
            try:
                daten = self._ser.read(256)
            except serial.SerialException as e:
                self.notiz(f"Lesefehler: {e}")
                return
            if not daten:
                continue
            jetzt = time.time()
            self._schreibe(f"{ts()} << raw {daten!r}", anzeigen=False)
            try:
                fertig = self._asm.feed(daten)
            except ValueError as e:
                self.notiz(f"Rahmenfehler: {e}")
                self._asm = Assembler()
                continue
            for r in fertig:
                self._schreibe(f"{ts()} << {r.hex():30} {r.beschreibung()}")
                self.rahmen.put((jetzt, r))
                if r.klasse in QUITTUNGEN:
                    self._quittung.put(r)

    # --- Senden ---------------------------------------------------------------------------------
    def sende(self, r: Rahmen, warte_quittung: float = 5.0) -> Rahmen | None:
        """Sendet einen Rahmen; wartet bis zu warte_quittung s auf ACK/REJ/ERR (0 = nicht warten)."""
        while not self._quittung.empty():
            self._quittung.get_nowait()
        roh = r.to_bytes()
        self._schreibe(f"{ts()} >> {r.hex():30} {r.beschreibung()}")
        self._schreibe(f"{ts()} >> raw {roh!r}", anzeigen=False)
        self._ser.write(roh)
        self._ser.flush()
        if not warte_quittung:
            return None
        try:
            q = self._quittung.get(timeout=warte_quittung)
        except queue.Empty:
            self.notiz(f"keine Quittung binnen {warte_quittung:.1f} s")
            return None
        self.notiz(f"Quittung: {q.beschreibung()}")
        return q

    def lausche(self, dauer: float) -> None:
        """Blockiert dauer Sekunden (Empfang läuft im Thread weiter). Strg+C bricht ab."""
        ende = time.time() + dauer
        try:
            while time.time() < ende:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.notiz("abgebrochen")

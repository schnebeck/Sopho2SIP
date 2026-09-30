# SPDX-License-Identifier: GPL-3.0-or-later
"""Test von gateway/ergoline/link.py gegen ein simuliertes Telefon am Pseudo-Terminal (ohne Hardware).

Die Simulation quittiert jeden Auftrag mit 04 00 (echtes ACK-Format noch unbekannt) und meldet danach
einen Anruf. Logs landen in einem temporären Verzeichnis.
"""
import os
import pathlib
import pty
import sys
import tempfile
import threading
import time
import tty
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gateway"))

from ergoline import link, protocol as p  # noqa: E402

KLINGELN = bytes.fromhex("02 12 30 01 98 6c 0d") + b"0101700000000"


class Telefon(threading.Thread):
    def __init__(self, master: int, quittung: bytes = b"\x04\x00"):
        super().__init__(daemon=True)
        self.master, self.quittung, self.empfangen = master, quittung, bytearray()
        self.stop = threading.Event()

    def run(self):
        asm = p.Assembler()
        while not self.stop.is_set():
            try:
                daten = os.read(self.master, 64)
            except OSError:
                return
            self.empfangen += daten
            for r in asm.feed(daten):
                if r.klasse == p.AUFTRAG:
                    time.sleep(0.05)
                    os.write(self.master, self.quittung)
                    time.sleep(0.05)
                    os.write(self.master, KLINGELN)


class LinkTest(unittest.TestCase):
    def setUp(self):
        self.master, slave = pty.openpty()
        tty.setraw(slave)
        self.port = os.ttyname(slave)
        self.tmp = tempfile.TemporaryDirectory()
        self._logdir, link.LOGDIR = link.LOGDIR, pathlib.Path(self.tmp.name)

    def tearDown(self):
        link.LOGDIR = self._logdir
        self.tmp.cleanup()

    def test_anmelden_quittung_und_meldung(self):
        tel = Telefon(self.master)
        tel.start()
        with link.ErgoLink(self.port, echo=None) as l:
            q = l.sende(p.anmelden(), warte_quittung=2)
            self.assertIsNotNone(q)
            self.assertEqual(q.klasse, p.ACK)
            t, r = l.rahmen.get(timeout=2)          # zuerst die Quittung
            t, r = l.rahmen.get(timeout=2)          # dann die Anrufmeldung
            self.assertEqual(p.MELDUNGSTYP[r.typ], "RINGING")
            logtext = l.logfile.read_text(encoding="utf-8") if l.logfile.exists() else ""
        tel.stop.set()
        self.assertEqual(bytes(tel.empfangen), bytes.fromhex("01 02 01 00"))
        self.assertIn(">> 01 02 01 00", logtext)
        self.assertIn("RINGING", logtext)

    def test_keine_quittung(self):
        with link.ErgoLink(self.port, echo=None) as l:
            self.assertIsNone(l.sende(p.keepalive(), warte_quittung=0.3))


if __name__ == "__main__":
    unittest.main()

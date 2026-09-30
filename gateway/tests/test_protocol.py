# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests für gateway/ergoline/protocol.py gegen den echten Mitschnitt vom 2026-09-30.

Aufruf: python3 -m unittest discover -s gateway/tests -v
"""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gateway"))
sys.path.insert(0, str(ROOT / "tools"))

from ergoline import protocol as p  # noqa: E402
from ergo import lese_log  # noqa: E402

MITSCHNITT = ROOT / "logs" / "serial_20260930_163534.log"


class Mitschnitt(unittest.TestCase):
    def setUp(self):
        self.rahmen = p.Assembler().feed(lese_log(MITSCHNITT)["<<"])

    def test_strom_zerfaellt_restlos_in_rahmen(self):
        asm = p.Assembler()
        asm.feed(lese_log(MITSCHNITT)["<<"])
        self.assertEqual(asm.rest, b"")
        self.assertTrue(all(r.klasse == p.MELDUNG for r in self.rahmen))

    def test_ablauf(self):
        typen = [p.MELDUNGSTYP[r.typ] for r in self.rahmen]
        self.assertEqual(typen[:4], ["RINGING", "FACILITY_EIN", "CONNECTED", "FACILITY_EIN"])
        self.assertIn("MORE_INFO", typen)
        self.assertEqual(typen[-2:], ["RELEASED", "FACILITY_AUS"])

    def test_anrufernummer(self):
        klingeln = self.rahmen[0]
        ie = dict(p.ies(klingeln.daten[2:]))
        nr = p.rufnummer(ie[0x6C])
        self.assertEqual(nr, "0101700000000")
        self.assertEqual(p.extern(nr), (True, "01700000000"))

    def test_hoerer_und_dtmf(self):
        self.assertIn("HOERER", self.rahmen[1].beschreibung())
        self.assertIn("DTMF", self.rahmen[3].beschreibung())

    def test_ursache_gegenseite(self):
        texte = [r.beschreibung() for r in self.rahmen]
        self.assertTrue(any("DISCONNECTED" in t and "URSACHE=8f" in t for t in texte))


class Stueckweise(unittest.TestCase):
    def test_byteweise_gleich_blockweise(self):
        strom = lese_log(MITSCHNITT)["<<"]
        asm, einzeln = p.Assembler(), []
        for b in strom:
            einzeln += asm.feed(bytes([b]))
        self.assertEqual(einzeln, p.Assembler().feed(strom))

    def test_fehlerantwort(self):
        (r,) = p.Assembler().feed(bytes.fromhex("05 00"))
        self.assertEqual((r.klasse, r.daten), (p.ERR, b""))
        self.assertEqual(r.beschreibung(), "ERR")


class Auftraege(unittest.TestCase):
    def test_bytes(self):
        self.assertEqual(p.anmelden().hex(), "01 02 01 00")
        self.assertEqual(p.keepalive().hex(), "01 02 00 00")
        self.assertEqual(p.belegen().hex(), "01 02 11 00")
        self.assertEqual(p.annehmen().hex(), "01 02 14 00")
        self.assertEqual(p.auflegen().hex(), "01 02 13 00")

    def test_waehlen(self):
        self.assertEqual(p.waehlen("123").hex(), "01 09 19 00 98 70 04 81 31 32 33")
        self.assertIn("ZIEL='123'", p.waehlen("123").beschreibung())
        with self.assertRaises(ValueError):
            p.waehlen("12a")

    def test_freie_auftraege(self):
        self.assertEqual(p.FREIE_AUFTRAEGE, {bytes.fromhex("01 02 01 00"), bytes.fromhex("01 02 00 00")})


if __name__ == "__main__":
    unittest.main()

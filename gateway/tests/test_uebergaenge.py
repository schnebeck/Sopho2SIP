# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of the transition table: completeness, assignment order, invariants."""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gateway"))

from ergoline import anruf as an, protocol as p, uebergaenge as u, zustand as z  # noqa: E402

RUF = "02 12 30 01 98 6c 0d" + b"0101700000000".hex()
RUF_2 = "02 12 30 01 98 6c 0d" + b"0101700000001".hex()
OHNE_ANRUF = ("READY", "FACILITY_EIN", "FACILITY_AUS", "FACILITY_ABGELEHNT")


class Tabelle(unittest.TestCase):
    def test_jede_meldung_ist_zugeordnet(self):
        for name in p.MELDUNGSTYP.values():
            self.assertEqual(sum(name in g for g in (u.REGELN, u.OHNE_REGEL, OHNE_ANRUF)), 1, name)

    def test_jeder_laufende_zustand_kann_enden(self):
        for typ, quellen in (("DISCONNECTED", an.AKTIV), ("RELEASED", an.AKTIV + (an.DISCONNECTED,))):
            self.assertEqual({von for von, _ in u.REGELN[typ].uebergaenge}, set(quellen), typ)

    def test_ziele_sind_zustaende(self):
        for typ, regel in u.REGELN.items():
            for von, nach in regel.uebergaenge:
                self.assertTrue({von, *nach} <= set(an.ZUSTANDSNAME), typ)


class Zuordnung(unittest.TestCase):
    def setUp(self):
        self.tel = z.Telefon()

    def melde(self, hexstr):
        (r,) = p.Assembler().feed(bytes.fromhex(hexstr))
        return self.tel.verarbeite(r, 0.0)

    def test_meldung_ohne_passenden_anruf(self):
        (ev,) = self.melde("02 02 31 01")
        self.assertEqual(ev[0], "UNERWARTET")
        self.assertIn("CONNECTED ohne passenden Anruf (keine Anrufe)", ev[2])

    def test_aufgebender_anklopfer_beendet_nicht_das_gespraech(self):   # vermutet, kein Mitschnitt
        self.melde(RUF)
        self.melde("02 02 31 01")
        self.melde(RUF_2)
        (ende,) = self.melde("02 06 39 01 98 08 01 8f")
        self.assertEqual((ende[0], ende[1].kennung), ("ANRUF_ENDE", 2))
        self.assertEqual({k: a.zustand for k, a in self.tel.anrufe.items()}, {1: an.CONNECTED})

    def test_zwei_gespraeche_verletzen_die_invariante_einmal(self):
        self.melde(RUF)
        self.melde("02 02 31 01")
        self.melde(RUF_2)
        ev = self.melde("02 02 31 01")                                      # ohne HOLD für den ersten
        self.assertEqual([e[0] for e in ev], ["VERBUNDEN", "INVARIANTE"])
        self.assertEqual([e[0] for e in self.melde("02 03 19 01 aa")], ["UNERWARTET"])   # nicht erneut gemeldet


if __name__ == "__main__":
    unittest.main()

# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests des Zustandsautomaten gegen echte Mitschnitte (Rufnummern bereinigt)."""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gateway"))

from ergoline import protocol as p, zustand as z  # noqa: E402
from ergoline.logdatei import rohdaten  # noqa: E402


def abspielen(log: str):
    tel, asm, ereignisse = z.Telefon(), p.Assembler(), []
    for zeit, richtung, daten in rohdaten(ROOT / "logs" / log):
        if richtung == "<<":
            for r in asm.feed(daten):
                ereignisse += tel.verarbeite(r, zeit)
    return tel, ereignisse, [e[2] for e in ereignisse if e[0] == "ANRUF_ENDE"]


class Mitschnitte(unittest.TestCase):
    def test_drei_vorgaenge_30_09(self):
        tel, _, ds = abspielen("serial_20260930_163534.log")
        self.assertEqual([d["ergebnis"] for d in ds], ["angenommen", "ohne_wahl", "verbunden"])
        ein, _, aus = ds
        self.assertEqual((ein["richtung"], ein["nummer"], ein["extern"]), ("ein", "01700000000", True))
        self.assertEqual(ein["verlauf"], ["OFFERING", "ACCEPTED", "CONNECTED", "DISCONNECTED", "IDLE"])
        self.assertAlmostEqual(ein["dauer_s"], 22.2, delta=0.3)
        self.assertEqual(ein["ausloeser"], "eigene_seite")
        self.assertEqual((aus["richtung"], aus["nummer"], aus["ursache"], aus["ausloeser"]),
                         ("aus", "01700000000", "8f", "gegenseite"))
        self.assertIn("RINGBACK", aus["verlauf"])
        self.assertEqual(tel.anrufe, {})                       # nichts bleibt hängen

    def test_annahme_und_auflegen_durch_pc(self):
        tel, ev, ds = abspielen("test_20261001_085744_annehmen_auflegen.log")
        self.assertTrue(tel.bereit)                             # READY nach Anmelden
        (d,) = ds
        self.assertEqual((d["ergebnis"], d["ausloeser"]), ("angenommen", "eigene_seite"))
        self.assertAlmostEqual(d["dauer_s"], 4.5, delta=0.5)

    def test_lautsprechertaste(self):
        _, _, (d,) = abspielen("test_20261001_085405_annehmen.log")
        self.assertEqual(d["ergebnis"], "angenommen")

    def test_pc_waehlt_extern(self):
        tel, ev, (d,) = abspielen("test_20261001_150042_waehlen_extern.log")   # belegen ohne DIALTONE
        self.assertEqual((d["ergebnis"], d["richtung"], d["nummer"], d["ausloeser"]),
                         ("verbunden", "aus", "01700000000", "eigene_seite"))
        self.assertEqual(d["verlauf"], ["DIALING", "PROCEEDING", "RINGBACK", "CONNECTED", "DISCONNECTED", "IDLE"])
        self.assertAlmostEqual(d["dauer_s"], 15.4, delta=0.3)
        self.assertEqual(tel.anrufe, {})

    def test_pi_angenommen_und_verpasst(self):
        tel, _, ds = abspielen("test_20261001_130201_pi_angenommen_verpasst.log")
        self.assertEqual([d["ergebnis"] for d in ds], ["angenommen", "verpasst"])
        verpasst = ds[1]                                        # RINGING → RELEASED 08 01 8f, ohne DISCONNECTED
        self.assertEqual(verpasst["verlauf"], ["OFFERING", "IDLE"])
        self.assertEqual((verpasst["ursache"], verpasst["ausloeser"]), ("8f", "gegenseite"))
        self.assertEqual(tel.anrufe, {})


class Vorbedingungen(unittest.TestCase):
    def setUp(self):
        self.tel = z.Telefon()

    def melde(self, hexstr, t=0.0):
        (r,) = p.Assembler().feed(bytes.fromhex(hexstr))
        return self.tel.verarbeite(r, t)

    def test_waehlen_in_ruhe(self):
        self.assertEqual([r.hex() for r in self.tel.auftraege_waehlen("123")],
                         ["01 02 11 00", "01 09 19 00 98 70 04 81 31 32 33"])

    def test_annehmen_nur_bei_klingeln(self):
        with self.assertRaises(z.AuftragNichtMoeglich):
            self.tel.auftraege_annehmen()
        self.melde("02 12 30 01 98 6c 0d" + b"0101700000000".hex())
        self.assertEqual([r.hex() for r in self.tel.auftraege_annehmen()], ["01 02 14 00"])
        with self.assertRaises(z.AuftragNichtMoeglich):
            self.tel.auftraege_waehlen("123")                  # Leitung belegt

    def test_auflegen_und_sperre_bis_freigabe(self):
        self.melde("02 12 30 01 98 6c 0d" + b"0101700000000".hex())
        self.melde("02 02 31 01")
        self.assertEqual([r.hex() for r in self.tel.auftraege_auflegen()], ["01 02 13 00"])
        self.melde("02 05 32 01 98 08 00")
        with self.assertRaises(z.AuftragNichtMoeglich):
            self.tel.auftraege_waehlen("123")                  # DISCONNECTED noch nicht frei
        self.melde("02 05 39 01 98 08 00")
        self.assertEqual(len(self.tel.auftraege_waehlen("123")), 2)

    def test_ziffern_nur_mit_anruf(self):
        with self.assertRaises(z.AuftragNichtMoeglich):
            self.tel.auftraege_ziffern("1")
        self.assertEqual([r.hex() for r in self.tel.auftraege_wahl_oder_ziffern("12")],
                         ["01 02 11 00", "01 08 19 00 98 70 03 81 31 32"])   # Ruhe → belegen + wählen
        self.melde("02 12 30 01 98 6c 0d" + b"0101700000000".hex())
        self.melde("02 02 31 01")
        self.assertEqual(self.tel.zustand_kurz()["zustand"], "verbunden")
        self.assertEqual(self.tel.zustand_kurz()["nummer"], "01700000000")
        self.assertEqual([r.hex() for r in self.tel.auftraege_wahl_oder_ziffern("#")],
                         ["01 07 19 00 98 70 02 81 23"])                    # Gespräch → nur 19 (Tonwahl)
        self.melde("02 05 32 01 98 08 00")
        with self.assertRaises(z.AuftragNichtMoeglich):
            self.tel.auftraege_ziffern("1")                                 # DISCONNECTED sperrt
        self.melde("02 05 39 01 98 08 00")
        self.assertEqual(self.tel.zustand_kurz(), {"zustand": "ruhe"})


if __name__ == "__main__":
    unittest.main()

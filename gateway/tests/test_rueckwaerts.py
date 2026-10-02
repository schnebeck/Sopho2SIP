# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests der Rückwärtssuche ohne Netz (Seitenausschnitte nachgebildet nach den am Pi geprüften Seiten)."""
import pathlib
import sys
import tempfile
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gateway"))

import rueckwaerts as r  # noqa: E402
import sopho2sipd as d  # noqa: E402
from ergoline import protocol as p  # noqa: E402

SEITE_11880 = ('<script type="application/ld+json">{"@type":"GovernmentOffice","name":"Stadtverwaltung Hannover",'
               '"address":{"@type":"PostalAddress","addressLocality":"Hannover"},"telephone":["(0511) 168-0"]}'
               '</script><script type="application/ld+json">{"@type":"FAQPage"}</script>')
SEITE_DOE = "<title>Stadtverwaltung Hannover in Hannover &rArr; in Das Örtliche</title>"
SEITE_DOE_LEER = "<title>01700000000 in Münster &rArr; in Das Örtliche</title>"


class Auswertung(unittest.TestCase):
    def test_11880(self):
        self.assertEqual(r.aus_11880(SEITE_11880, "05111680"),
                         {"name": "Stadtverwaltung Hannover", "ort": "Hannover", "quelle": "11880"})
        self.assertIsNone(r.aus_11880(SEITE_11880, "05111681"))          # Nummer passt nicht → kein Treffer

    def test_dasoertliche_nur_mit_detailseite(self):
        self.assertEqual(r.aus_dasoertliche("https://www.dasoertliche.de/?form_name=detail&id=1", SEITE_DOE)["name"],
                         "Stadtverwaltung Hannover")
        self.assertIsNone(r.aus_dasoertliche("https://www.dasoertliche.de/?form_name=search_inv&ph=0170",
                                             SEITE_DOE_LEER))            # Geo-IP-Ort, kein Eintrag

    def test_suchbar(self):
        self.assertTrue(r.Rueckwaertssuche.suchbar("05111680"))
        for n in ("123", "anonymous", "", "0511"):
            self.assertFalse(r.Rueckwaertssuche.suchbar(n))


class Http404(unittest.TestCase):
    def test_404_ist_kein_eintrag(self):
        import io
        import urllib.error
        from unittest import mock
        fehler = urllib.error.HTTPError("https://x/", 404, "Not Found", {}, io.BytesIO(b""))
        with mock.patch("urllib.request.urlopen", side_effect=fehler):
            self.assertEqual(r._hole("https://x/", 1), ("https://x/", ""))
            self.assertIsNone(r.suche_online("01700000000"))              # beide Quellen „leer“ → kein Treffer


class Zwischenspeicher(unittest.TestCase):
    def test_einmal_online_dann_gespeichert(self):
        aufrufe = []
        with tempfile.TemporaryDirectory() as tmp:
            pfad = pathlib.Path(tmp) / "r.json"
            s = r.Rueckwaertssuche(pfad, suche=lambda n: aufrufe.append(n) or {"name": "X", "ort": "Y", "quelle": "t"})
            self.assertEqual(s.frage("05111680")["name"], "X")
            self.assertEqual(r.Rueckwaertssuche(pfad, suche=None).frage("05111680")["name"], "X")   # aus Datei
            self.assertEqual(aufrufe, ["05111680"])
            self.assertIsNone(s.frage("123"))                              # Nebenstelle: nie online
            self.assertEqual(aufrufe, ["05111680"])


class Gateway(unittest.TestCase):
    def test_name_im_zustand_und_datensatz(self):
        gw = d.Gateway(d.Ausgabe("-", None, echo=lambda s: None))
        gefunden = threading.Event()
        with tempfile.TemporaryDirectory() as tmp:
            def suche(n):
                self.assertEqual(n, "01700000000")                         # ohne Amtsholung
                return {"name": "Testfirma", "ort": "Hannover", "quelle": "t"}
            gw.rueckwaerts = r.Rueckwaertssuche(pathlib.Path(tmp) / "r.json", suche=suche)
            abo = gw.abonniere()
            for rahmen in p.Assembler().feed(bytes.fromhex("02 12 30 01 98 6c 0d" + b"0101700000000".hex())):
                gw.verarbeite(rahmen, time.time())
            ende = time.time() + 2
            while time.time() < ende and not gefunden.is_set():
                if abo.get(timeout=1)["typ"] == "NAME":
                    gefunden.set()
            self.assertTrue(gefunden.is_set())
            self.assertEqual(gw.status()["anruf"]["name"], "Testfirma")
            ende = []
            gw.zuhoerer.append(lambda name, anruf, zusatz: name == "ANRUF_ENDE" and ende.append(zusatz))
            for rahmen in p.Assembler().feed(bytes.fromhex("02 06 39 01 98 08 01 8f")):
                gw.verarbeite(rahmen, time.time())
            self.assertEqual((ende[0]["name"], ende[0]["ort"]), ("Testfirma", "Hannover"))


if __name__ == "__main__":
    unittest.main()

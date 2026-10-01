# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests des Webportals: Zugang, Schutz der POST-Aufträge, Sperre ohne --steuerung (ohne Telefon)."""
import base64
import json
import pathlib
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gateway"))

import portal  # noqa: E402
import sopho2sipd as d  # noqa: E402


class Portal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        pw = pathlib.Path(cls.tmp.name) / "portal.json"
        portal.passwort_setzen("sopho", "geheim-geheim", pw)
        anrufe = pathlib.Path(cls.tmp.name) / "anrufe.jsonl"
        d.wiedergabe(str(ROOT / "logs" / "test_20261001_130201_pi_angenommen_verpasst.log"),
                     d.Ausgabe(str(anrufe), None, echo=lambda s: None), "01")
        cls.gw = d.Gateway(d.Ausgabe(str(anrufe), None, echo=lambda s: None))
        cls.srv = portal.Portal(("127.0.0.1", 0), cls.gw, portal.lade_zugang(pw))
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.basis = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def anfrage(self, pfad, daten=None, auth=("sopho", "geheim-geheim"), kopf=True):
        req = urllib.request.Request(self.basis + pfad, data=None if daten is None else json.dumps(daten).encode())
        if auth:
            req.add_header("Authorization", "Basic " + base64.b64encode(":".join(auth).encode()).decode())
        if kopf and daten is not None:
            req.add_header("X-Sopho2SIP", "1")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, None

    def test_ohne_oder_falsches_passwort(self):
        self.assertEqual(self.anfrage("/api/status", auth=None)[0], 401)
        self.assertEqual(self.anfrage("/api/status", auth=("sopho", "falsch"))[0], 401)

    def test_status_und_liste(self):
        code, st = self.anfrage("/api/status")
        self.assertEqual((code, st["steuerung"], st["anruf"]), (200, False, {"zustand": "ruhe"}))
        code, liste = self.anfrage("/api/anrufe")
        self.assertEqual([a["ergebnis"] for a in liste], ["verpasst", "angenommen"])   # neueste zuerst

    def test_post_braucht_kopf_und_steuerung(self):
        self.assertEqual(self.anfrage("/api/waehlen", {"nummer": "123"}, kopf=False)[0], 403)
        self.assertEqual(self.anfrage("/api/waehlen", {"nummer": "123"})[0], 409)       # gesperrt

    def test_ohne_passwort_nur_lokal(self):
        with self.assertRaises(SystemExit):
            portal.Portal(("0.0.0.0", 0), self.gw, None)


if __name__ == "__main__":
    unittest.main()

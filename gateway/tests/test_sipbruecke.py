# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests der SIP-Brücke ohne Telefon und ohne baresip (beide nachgebildet)."""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gateway"))

import sopho2sipd as d  # noqa: E402
from ergoline import protocol as p  # noqa: E402
from sipbruecke import NetstringLeser, SipBruecke, netstring, nummer_aus_uri  # noqa: E402

NUMMER = b"0101700000000".hex(" ")


class Link:
    def __init__(self):
        self.gesendet = []

    def sende(self, r, warte_quittung=5.0):
        self.gesendet.append(r.hex())
        return p.Rahmen(p.ACK, b"\x00")


class Ctrl:
    verbunden = True

    def __init__(self):
        self.befehle = []

    def befehl(self, cmd, params=""):
        self.befehle.append(f"{cmd} {params}".strip())
        return True


class Bruecke(unittest.TestCase):
    def aufbau(self, steuerung=True):
        self.gw = d.Gateway(d.Ausgabe("-", None, echo=lambda s: None), steuerung=steuerung)
        self.link, self.ctrl = Link(), Ctrl()
        self.gw.link = self.link
        self.br = SipBruecke(self.gw, self.ctrl)
        self.gw.zuhoerer.append(self.br.bei_telefon)

    def melde(self, hexstr):
        for r in p.Assembler().feed(bytes.fromhex(hexstr)):
            self.gw.verarbeite(r, 0.0)

    def sip(self, typ, **kw):
        self.br.bei_sip({"event": True, "type": typ, **kw})

    def test_sopho_nach_sip(self):
        self.aufbau()
        self.melde("02 12 30 01 98 6c 0d " + NUMMER)                      # RINGING
        self.assertEqual(self.ctrl.befehle, ["dial sip:01700000000@127.0.0.1"])
        self.sip("CALL_ESTABLISHED", direction="outgoing")                  # Softphone nimmt ab
        self.assertEqual(self.link.gesendet, ["01 02 14 00"])               # → Annehmen an der D340
        self.melde("02 03 3b 01 0a 02 02 31 01")                             # Hörer ab, CONNECTED
        self.sip("CALL_DTMF_START", param="5")
        self.assertEqual(self.link.gesendet[-1], "01 07 19 00 98 70 02 81 35")
        self.sip("CALL_CLOSED")                                             # Softphone legt auf
        self.assertEqual(self.link.gesendet[-1], "01 02 13 00")             # → Auflegen
        self.melde("02 05 32 01 98 08 00 02 05 39 01 98 08 00")
        self.assertEqual(self.ctrl.befehle, ["dial sip:01700000000@127.0.0.1"])   # kein zweites hangup
        self.assertIsNone(self.br.modus)

    def test_anrufer_legt_auf_bevor_sip_annimmt(self):
        self.aufbau()
        self.melde("02 12 30 01 98 6c 0d " + NUMMER)
        self.melde("02 06 39 01 98 08 01 8f")                               # RELEASED (verpasst)
        self.assertEqual(self.ctrl.befehle[-1], "hangup")
        self.assertEqual(self.link.gesendet, [])
        self.assertIsNone(self.br.modus)

    def test_ohne_steuerung_nur_anzeige(self):
        self.aufbau(steuerung=False)
        self.melde("02 12 30 01 98 6c 0d " + NUMMER)
        self.sip("CALL_ESTABLISHED")
        self.assertEqual(self.link.gesendet, [])                            # nichts an die D340
        self.assertEqual(self.ctrl.befehle[-1], "hangup")
        self.sip("CALL_INCOMING", peeruri="sip:123@127.0.0.1")              # SIP-Wahl gesperrt
        self.assertEqual(self.link.gesendet, [])

    def test_sip_nach_sopho(self):
        self.aufbau()
        self.sip("CALL_INCOMING", peeruri="sip:01700000000@127.0.0.1", direction="incoming")
        self.assertEqual(self.link.gesendet, ["01 02 11 00", "01 13 19 00 98 70 0e 81 " + NUMMER])
        self.melde("02 02 36 01 02 12 19 01 98 70 0d " + NUMMER + " 02 02 3e 01")   # Wählton, Wahl, Proceeding
        self.assertEqual(self.ctrl.befehle, [])
        self.melde("02 02 31 01")                                           # Gegenseite meldet sich
        self.assertEqual(self.ctrl.befehle, ["accept"])
        self.sip("CALL_ESTABLISHED")
        self.melde("02 06 32 01 98 08 01 8f")                               # Gegenseite legt auf
        self.assertEqual(self.ctrl.befehle[-1], "hangup")
        self.melde("02 05 39 01 98 08 00")
        self.assertIsNone(self.br.modus)

    def test_sip_anrufer_legt_vor_meldung_auf(self):
        self.aufbau()
        self.sip("CALL_INCOMING", peeruri="sip:123@127.0.0.1")
        self.melde("02 02 36 01")
        self.sip("CALL_CLOSED")
        self.assertEqual(self.link.gesendet[-1], "01 02 13 00")


class Hilfen(unittest.TestCase):
    def test_netstring(self):
        leser = NetstringLeser()
        roh = netstring({"a": 1}) + netstring({"b": "ü"})
        self.assertEqual(leser.feed(roh[:5]), [])
        self.assertEqual(leser.feed(roh[5:]), [{"a": 1}, {"b": "ü"}])

    def test_nummer_aus_uri(self):
        self.assertEqual(nummer_aus_uri("sip:0171@127.0.0.1"), "0171")
        self.assertEqual(nummer_aus_uri("sip:123;user=phone@host"), "123")


if __name__ == "__main__":
    unittest.main()

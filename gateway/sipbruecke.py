# SPDX-License-Identifier: GPL-3.0-or-later
"""Brücke Telefon (D340) ⇄ SIP (baresip über ctrl_tcp, Netstring-JSON).

Rufweg (Asterisk-Wählplan gateway/asterisk/extensions.conf):
  Sopho → SIP: Anruf an der D340 → baresip ruft sip:<Anrufernummer>@127.0.0.1 (Asterisk setzt daraus die
               Caller-ID und lässt die Softphones klingeln) → Softphone nimmt ab (CALL_ESTABLISHED) → Annehmen.
  SIP → Sopho: Softphone wählt → Asterisk ruft baresip mit der gewählten Nummer als Absender (CALL_INCOMING)
               → Wahl an der D340 → Gegenseite meldet sich (VERBUNDEN) → baresip nimmt an.
  Auflegen auf einer Seite löst die andere aus; DTMF vom Softphone (CALL_DTMF_START) wird als Ziffer nachgewählt.
Ohne --steuerung klingeln die Softphones nur (Anrufanzeige); Annehmen dort beendet den SIP-Anruf wieder.
Ereignisformat am Gerät mitgeschnitten (baresip 1.1.0, 2026-10-01): type, id, direction, peeruri, param.
"""
from __future__ import annotations

import json
import socket
import threading
import time

from ergoline import protocol as p


def netstring(daten: dict) -> bytes:
    j = json.dumps(daten).encode()
    return str(len(j)).encode() + b":" + j + b","


class NetstringLeser:
    def __init__(self) -> None:
        self.puffer = b""

    def feed(self, daten: bytes) -> list[dict]:
        self.puffer += daten
        out = []
        while b":" in self.puffer:
            laenge, _, rest = self.puffer.partition(b":")
            if not laenge.isdigit():
                raise ValueError(f"kein Netstring: {self.puffer[:20]!r}")
            n = int(laenge)
            if len(rest) < n + 1:
                break
            out.append(json.loads(rest[:n]))
            self.puffer = rest[n + 1:]
        return out


class BaresipCtrl:
    """TCP-Verbindung zu ctrl_tcp mit Wiederanlauf; Ereignisse gehen an bei_ereignis(dict)."""

    def __init__(self, adresse: tuple[str, int], bei_ereignis, echo=print) -> None:
        self.adresse, self.bei_ereignis, self.echo = adresse, bei_ereignis, echo
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._token = 0

    def start(self) -> None:
        threading.Thread(target=self._schleife, daemon=True, name="baresip").start()

    @property
    def verbunden(self) -> bool:
        return self._sock is not None

    def befehl(self, cmd: str, params: str = "") -> bool:
        with self._lock:
            if self._sock is None:
                self.echo(f"  SIP          baresip nicht verbunden, '{cmd}' entfällt")
                return False
            self._token += 1
            try:
                self._sock.sendall(netstring({"command": cmd, "params": params, "token": str(self._token)}))
            except OSError as e:
                self.echo(f"  SIP          Senden an baresip fehlgeschlagen: {e}")
                return False
        self.echo(f"  SIP >>       {cmd} {params}")
        return True

    def _schleife(self) -> None:
        while True:
            try:
                s = socket.create_connection(self.adresse, timeout=5)
                s.settimeout(None)
                with self._lock:
                    self._sock = s
                self.echo(f"  SIP          baresip verbunden ({self.adresse[0]}:{self.adresse[1]})")
                leser = NetstringLeser()
                while daten := s.recv(65536):
                    for nachricht in leser.feed(daten):
                        if nachricht.get("event"):
                            self.bei_ereignis(nachricht)
                        elif nachricht.get("response") and not nachricht.get("ok"):
                            self.echo(f"  SIP <<       Fehler: {nachricht.get('data', '').strip()}")
            except (OSError, ValueError) as e:
                if self._sock is not None:
                    self.echo(f"  SIP          baresip getrennt ({e})")
            with self._lock:
                if self._sock:
                    self._sock.close()
                self._sock = None
            time.sleep(5)


def nummer_aus_uri(uri: str) -> str:
    """'sip:0171…@127.0.0.1' → '0171…' (Benutzerteil)."""
    benutzer = uri.split(":", 1)[-1].split("@", 1)[0]
    return benutzer.split(";", 1)[0]


class SipBruecke:
    """Verknüpft die Ereignisse des Gateways (Telefon) mit baresip. Höchstens ein Anruf gleichzeitig."""

    SIP_ZIEL = "127.0.0.1"          # Asterisk

    def __init__(self, gateway, ctrl) -> None:
        self.gw, self.ctrl = gateway, ctrl
        self.modus: str | None = None      # "ein" = Sopho → SIP, "aus" = SIP → Sopho
        self.sip_aktiv = False             # SIP-Anruf besteht (klingelt oder verbunden)
        self.sip_verbunden = False
        self.sopho_verbunden = False
        self._lock = threading.RLock()

    def _log(self, text: str) -> None:
        self.gw.ausgabe.echo(f"  BRÜCKE       {text}")

    def _sip_auflegen(self) -> None:
        if self.sip_aktiv:
            self.ctrl.befehl("hangup")
        self.sip_aktiv = self.sip_verbunden = False

    def _ende(self) -> None:
        self.modus, self.sopho_verbunden = None, False

    # --- Telefon → SIP ------------------------------------------------------------------------------
    def bei_telefon(self, name: str, anruf, zusatz) -> None:
        with self._lock:
            if name == "ANRUF_EIN" and self.modus is None:
                self.modus = "ein"
                ziel = p.sip_nummer(anruf.nummer_roh, self.gw.amtsholung)
                if self.ctrl.befehl("dial", f"sip:{ziel}@{self.SIP_ZIEL}"):
                    self.sip_aktiv = True
            elif name == "VERBUNDEN":
                self.sopho_verbunden = True
                if self.modus == "aus" and self.sip_aktiv and not self.sip_verbunden:
                    self.ctrl.befehl("accept")
            elif name == "BESETZT" and self.modus == "aus":
                self._log("Ziel besetzt")
                self._sip_auflegen()
            elif name == "VERBINDUNG" and not zusatz and self.modus is not None:
                self._log("Verbindung zum Telefon verloren")
                self._sip_auflegen()
                self._ende()
            elif name in ("GETRENNT", "ANRUF_ENDE") and self.modus is not None:
                self._sip_auflegen()
                if name == "ANRUF_ENDE":
                    self._ende()

    # --- SIP → Telefon ------------------------------------------------------------------------------
    def bei_sip(self, ev: dict) -> None:
        typ = ev.get("type")
        with self._lock:
            if typ == "CALL_INCOMING":
                self._eingehend_sip(nummer_aus_uri(ev.get("peeruri", "")))
            elif typ == "CALL_ESTABLISHED":
                self.sip_verbunden = True
                if self.modus == "ein":
                    erg = self.gw.auftrag("annehmen")
                    if not erg["ok"]:
                        self._log(f"Annehmen an der D340 nicht möglich: {erg['fehler']}")
                        self._sip_auflegen()
            elif typ == "CALL_CLOSED":
                war_aktiv = self.sip_aktiv
                self.sip_aktiv = self.sip_verbunden = False
                if war_aktiv and (self.modus == "aus" or (self.modus == "ein" and self.sopho_verbunden)):
                    erg = self.gw.auftrag("auflegen")
                    if not erg["ok"]:
                        self._log(f"Auflegen an der D340: {erg['fehler']}")
                if self.modus == "aus" and self.gw.status()["anruf"]["zustand"] == "ruhe":
                    self._ende()                 # an der D340 kam kein Anruf zustande
            elif typ == "CALL_DTMF_START" and self.sopho_verbunden:
                ziffer = (ev.get("param") or "").strip()[:1]
                if ziffer and ziffer in "0123456789*#":
                    self.gw.auftrag("waehlen", ziffer)

    def _eingehend_sip(self, nummer: str) -> None:
        self.sip_aktiv = True
        if self.modus is not None:
            self._log("Leitung belegt, SIP-Anruf abgewiesen")
            self._sip_auflegen()
            return
        wahl = p.sopho_nummer(nummer, self.gw.amtsholung)
        if not wahl:
            self._log(f"keine wählbare Nummer in {nummer!r}")
            self._sip_auflegen()
            return
        self.modus = "aus"
        erg = self.gw.auftrag("waehlen", wahl)
        if not erg["ok"]:
            self._log(f"Wahl {wahl} nicht möglich: {erg['fehler']}")
            self._sip_auflegen()
            self._ende()

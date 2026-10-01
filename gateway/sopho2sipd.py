#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sopho2SIP-Daemon: hält die Verbindung zur ErgoLine D340, führt den Zustandsautomaten, gibt für jeden beendeten
Anruf einen Anrufdatensatz aus (JSON-Zeile in eine Datei, optional HTTP-POST) und bedient das Webportal.

Betrieb:     gateway/sopho2sipd.py [--port …] [--anrufe DATEI] [--webhook URL] [--portal HOST:PORT]
                                   [--baresip HOST:PORT] [--steuerung]
Wiedergabe:  gateway/sopho2sipd.py --wiedergabe logs/serial_20260930_163534.log [--anrufe -]

Ohne --steuerung sendet der Daemon nur Anmelden und Keepalive; Wählen/Annehmen/Auflegen aus dem Portal sind
dann gesperrt. Die Datensätze enthalten echte Rufnummern: Standardziel ~/.local/share/sopho2sip/anrufe.jsonl.
"""
import argparse
import json
import pathlib
import queue
import sys
import threading
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ergoline import protocol as p  # noqa: E402
from ergoline.logdatei import rohdaten  # noqa: E402
from ergoline.zustand import AuftragNichtMoeglich, Telefon  # noqa: E402

STANDARD_ANRUFE = pathlib.Path.home() / ".local" / "share" / "sopho2sip" / "anrufe.jsonl"
KEEPALIVE_S = 15.0


class Ausgabe:
    def __init__(self, datei: str, webhook: str | None, echo=print):
        self.datei, self.webhook, self.echo = datei, webhook, echo
        if datei != "-":
            pathlib.Path(datei).parent.mkdir(parents=True, exist_ok=True)

    def ereignis(self, name: str, anruf, zusatz) -> None:
        kennung = f"#{anruf.kennung}" if anruf else ""
        self.echo(f"  {name:12} {kennung:4} {zusatz if zusatz not in (None, '') else ''}")

    def datensatz(self, ds: dict) -> None:
        zeile = json.dumps(ds, ensure_ascii=False)
        if self.datei == "-":
            print(zeile, flush=True)
        else:
            with open(self.datei, "a", encoding="utf-8") as f:
                f.write(zeile + "\n")
        if self.webhook:
            try:
                req = urllib.request.Request(self.webhook, data=zeile.encode(), method="POST",
                                             headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=5).close()
            except OSError as e:
                self.echo(f"  Webhook fehlgeschlagen: {e}")


class Gateway:
    """Gemeinsamer Zustand von Empfangsschleife und Portal. Alle Zugriffe auf Telefon und Link unter self.lock."""

    def __init__(self, ausgabe: Ausgabe, amtsholung: str = p.AMTSHOLUNG, steuerung: bool = False):
        self.ausgabe, self.amtsholung, self.steuerung = ausgabe, amtsholung, steuerung
        self.lock = threading.RLock()
        self.telefon = Telefon(amtsholung)
        self.link = None
        self.zuhoerer: list = []            # f(name, anruf, zusatz), z. B. SipBruecke.bei_telefon
        self.sip = None                     # BaresipCtrl, falls --baresip
        self.rueckwaerts = None             # Rueckwaertssuche, falls --rueckwaertssuche
        self._pc_anruf = False              # Gespräch vom PC angenommen/gewählt → X-Eingang einschalten
        self._abos: list[queue.Queue] = []
        self._abo_lock = threading.Lock()

    # --- Ereignisse an Portal-Abonnenten -----------------------------------------------------------
    def abonniere(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=100)
        with self._abo_lock:
            self._abos.append(q)
        return q

    def abbestelle(self, q: queue.Queue) -> None:
        with self._abo_lock:
            if q in self._abos:
                self._abos.remove(q)

    def _sende_an_abos(self, typ: str, **daten) -> None:
        ev = {"typ": typ, "status": self.status(), **daten}
        with self._abo_lock:
            for q in self._abos:
                try:
                    q.put_nowait(ev)
                except queue.Full:
                    pass

    # --- Empfang ------------------------------------------------------------------------------------
    def verbindung(self, link) -> None:
        with self.lock:
            self.link = link
            self.telefon = Telefon(self.amtsholung)
        self._melde_zuhoerern("VERBINDUNG", None, link is not None)
        self._sende_an_abos("VERBINDUNG")

    def _melde_zuhoerern(self, name, anruf, zusatz) -> None:
        for f in self.zuhoerer:
            try:
                f(name, anruf, zusatz)
            except Exception as e:          # ein Fehler in der Brücke darf den Empfang nicht stoppen
                self.ausgabe.echo(f"  FEHLER       {f.__qualname__}: {e!r}")

    def verarbeite(self, r: p.Rahmen, zeit: float) -> None:
        with self.lock:
            ereignisse = self.telefon.verarbeite(r, zeit)
        for name, anruf, zusatz in ereignisse:
            if name == "ANRUF_ENDE":
                self.ausgabe.ereignis(name, anruf, f"{zusatz['richtung']} {zusatz['nummer'] or '–'} "
                                      f"{'angenommen ' + str(zusatz['dauer_s']) + ' s' if zusatz['angenommen'] else 'nicht angenommen'}")
                self.ausgabe.datensatz(zusatz)
            else:
                self.ausgabe.ereignis(name, anruf, zusatz)
            if name == "VERBUNDEN":
                self._x_eingang_einschalten()
            elif name == "ANRUF_ENDE":
                self._pc_anruf = False
            self._melde_zuhoerern(name, anruf, zusatz)
            self._sende_an_abos(name)
            if name in ("ANRUF_EIN", "WAHL") and self.rueckwaerts and anruf.nummer_roh and anruf.name is None:
                threading.Thread(target=self._rueckwaerts, args=(anruf,), daemon=True).start()

    def _x_eingang_einschalten(self) -> None:
        """Bei PC-geführten Gesprächen Sprache von X_IN statt der Mikrofone der D340 (Merkmal 4f).
        Gespräche am Hörer der D340 bleiben unberührt, sonst wäre dort das Mikrofon stumm."""
        with self.lock:
            if not (self._pc_anruf and self.steuerung and self.link) or self.telefon.x_eingang:
                return
            q = self.link.sende(p.x_eingang())
        self.ausgabe.echo(f"  AUFTRAG      X-Eingang statt Mikrofon: {q.beschreibung() if q else 'keine Quittung'}")

    def _rueckwaerts(self, anruf) -> None:
        ext, nummer = p.extern(anruf.nummer_roh, self.amtsholung)
        treffer = self.rueckwaerts.frage(nummer) if ext else None
        if not treffer:
            return
        with self.lock:
            anruf.name, anruf.ort = treffer["name"], treffer.get("ort")
        self.ausgabe.echo(f"  NAME         #{anruf.kennung} {treffer['name']} ({treffer.get('ort') or '–'}, {treffer['quelle']})")
        self._sende_an_abos("NAME")

    # --- Abfragen -----------------------------------------------------------------------------------
    def status(self) -> dict:
        with self.lock:
            return {"verbunden": self.link is not None, "bereit": self.telefon.bereit,
                    "hoerer_ab": self.telefon.hoerer_ab, "steuerung": self.steuerung,
                    "sip": None if self.sip is None else self.sip.verbunden,
                    "anruf": self.telefon.zustand_kurz(), "zeit": time.time()}

    def anrufliste(self, n: int = 200) -> list[dict]:
        if self.ausgabe.datei == "-":
            return []
        try:
            zeilen = pathlib.Path(self.ausgabe.datei).read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        out = []
        for z in reversed(zeilen[-n:]):
            try:
                ds = json.loads(z)
            except json.JSONDecodeError:
                continue
            if not ds.get("name") and self.rueckwaerts and ds.get("extern"):
                treffer = self.rueckwaerts.bekannt(ds.get("nummer", ""))    # nur Zwischenspeicher, kein Netz
                if treffer:
                    ds["name"], ds["ort"] = treffer["name"], treffer.get("ort")
            out.append(ds)
        return out

    # --- Aufträge (Portal) --------------------------------------------------------------------------
    def auftrag(self, art: str, nummer: str = "") -> dict:
        if not self.steuerung:
            return {"ok": False, "fehler": "Steuerung gesperrt (Daemon ohne --steuerung gestartet)"}
        with self.lock:
            if self.link is None:
                return {"ok": False, "fehler": "keine Verbindung zum Telefon"}
            try:
                if art == "waehlen":
                    rahmen = self.telefon.auftraege_wahl_oder_ziffern(nummer)
                elif art == "annehmen":
                    rahmen = self.telefon.auftraege_annehmen()
                elif art == "auflegen":
                    rahmen = self.telefon.auftraege_auflegen()
                else:
                    return {"ok": False, "fehler": f"unbekannter Auftrag {art}"}
            except (AuftragNichtMoeglich, ValueError) as e:
                return {"ok": False, "fehler": str(e)}
            gesendet = []
            for r in rahmen:
                q = self.link.sende(r)
                gesendet.append(r.hex())
                if q is None or q.klasse != p.ACK:
                    return {"ok": False, "gesendet": gesendet,
                            "fehler": f"keine Quittung für {r.hex()}" if q is None else q.beschreibung()}
            # noch unter der Sperre: CONNECTED wird erst danach verarbeitet und findet die Markierung sicher vor
            if art == "annehmen" or (art == "waehlen" and gesendet[0] == p.belegen().hex()):
                self._pc_anruf = True
        self.ausgabe.echo(f"  AUFTRAG     {art} {' | '.join(gesendet)}")
        return {"ok": True, "gesendet": gesendet}


def wiedergabe(pfad: str, ausgabe: Ausgabe, amtsholung: str) -> int:
    gw, asm = Gateway(ausgabe, amtsholung), p.Assembler()
    for zeit, richtung, daten in rohdaten(pfad):
        if richtung != "<<":
            continue
        for r in asm.feed(daten):
            gw.verarbeite(r, zeit)
    return 0


def betrieb(a, gw: Gateway) -> int:
    from ergoline.link import PORT_STANDARD, ErgoLink
    import serial
    while True:
        try:
            with ErgoLink(a.port or PORT_STANDARD, echo=None) as link:
                gw.verbindung(link)
                with gw.lock:
                    q = link.sende(p.anmelden())
                print(f"Anmeldung: {q.beschreibung() if q else 'keine Quittung'}", flush=True)
                letzte = time.time()
                while True:
                    try:
                        zeit, r = link.rahmen.get(timeout=1.0)
                    except queue.Empty:
                        if time.time() - letzte > KEEPALIVE_S:
                            with gw.lock:
                                q = link.sende(p.keepalive())
                            if q is None:
                                raise serial.SerialException("Keepalive ohne Quittung")
                            letzte = time.time()
                        continue
                    letzte = zeit
                    gw.verarbeite(r, zeit)
        except (serial.SerialException, OSError) as e:
            gw.verbindung(None)
            print(f"Verbindung verloren ({e}); neuer Versuch in 5 s", flush=True)
            time.sleep(5)
        except KeyboardInterrupt:
            return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port")
    ap.add_argument("--anrufe", default=str(STANDARD_ANRUFE), help="JSON-Zeilen-Datei für Anrufdatensätze, '-' = stdout")
    ap.add_argument("--webhook", help="URL, an die jeder Anrufdatensatz per HTTP-POST (JSON) geht")
    ap.add_argument("--amtsholung", default=p.AMTSHOLUNG)
    ap.add_argument("--portal", metavar="HOST:PORT", help="Webportal starten, z. B. 127.0.0.1:8080")
    ap.add_argument("--steuerung", action="store_true", help="Wählen/Annehmen/Auflegen (Portal, SIP) erlauben")
    ap.add_argument("--baresip", metavar="HOST:PORT", help="SIP-Brücke über baresip ctrl_tcp, z. B. 127.0.0.1:4444")
    ap.add_argument("--rueckwaertssuche", action="store_true",
                    help="Namen externer Anrufer online nachschlagen (11880, Das Örtliche; Nummern gehen an diese Dienste)")
    ap.add_argument("--wiedergabe", metavar="LOG", help="Mitschnitt statt Telefon verarbeiten")
    a = ap.parse_args()
    ausgabe = Ausgabe(a.anrufe, a.webhook, echo=lambda s: print(s, file=sys.stderr, flush=True))
    if a.wiedergabe:
        return wiedergabe(a.wiedergabe, ausgabe, a.amtsholung)
    gw = Gateway(ausgabe, a.amtsholung, a.steuerung)
    if a.rueckwaertssuche:
        from rueckwaerts import Rueckwaertssuche
        gw.rueckwaerts = Rueckwaertssuche(echo=ausgabe.echo)
    if a.baresip:
        from sipbruecke import BaresipCtrl, SipBruecke
        host, _, port = a.baresip.rpartition(":")
        bruecke = SipBruecke(gw, None)
        bruecke.ctrl = gw.sip = BaresipCtrl((host or "127.0.0.1", int(port)), bruecke.bei_sip, echo=ausgabe.echo)
        gw.zuhoerer.append(bruecke.bei_telefon)
        gw.sip.start()
    if a.portal:
        import portal
        srv = portal.starte(a.portal, gw)
        host, port = srv.server_address[:2]
        print(f"Portal: {'https' if srv.tls else 'http'}://{host}:{port}/ "
              f"(Steuerung {'frei' if a.steuerung else 'gesperrt'})", flush=True)
    return betrieb(a, gw)


if __name__ == "__main__":
    raise SystemExit(main())

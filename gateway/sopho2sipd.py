#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sopho2SIP-Daemon (Kern): hält die Verbindung zur ErgoLine D340, führt den Zustandsautomaten und gibt
für jeden beendeten Anruf einen Anrufdatensatz aus – als JSON-Zeile in eine Datei und optional per HTTP-POST.

Betrieb:     gateway/sopho2sipd.py [--port …] [--anrufe DATEI] [--webhook URL]
Wiedergabe:  gateway/sopho2sipd.py --wiedergabe logs/serial_20260930_163534.log [--anrufe -]

Die Datensätze enthalten echte Rufnummern: Standardziel ist ~/.local/share/sopho2sip/anrufe.jsonl, nie das Repo.
SIP, Audio und Steuerbefehle folgen in späteren Ausbaustufen.
"""
import argparse
import json
import pathlib
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ergoline import protocol as p  # noqa: E402
from ergoline.logdatei import rohdaten  # noqa: E402
from ergoline.zustand import Telefon  # noqa: E402

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


def verarbeite(telefon: Telefon, ausgabe: Ausgabe, r: p.Rahmen, zeit: float) -> None:
    for name, anruf, zusatz in telefon.verarbeite(r, zeit):
        if name == "ANRUF_ENDE":
            ausgabe.ereignis(name, anruf, f"{zusatz['richtung']} {zusatz['nummer'] or '–'} "
                                          f"{'angenommen ' + str(zusatz['dauer_s']) + ' s' if zusatz['angenommen'] else 'nicht angenommen'}")
            ausgabe.datensatz(zusatz)
        else:
            ausgabe.ereignis(name, anruf, zusatz)


def wiedergabe(pfad: str, ausgabe: Ausgabe, amtsholung: str) -> int:
    telefon, asm = Telefon(amtsholung), p.Assembler()
    for zeit, richtung, daten in rohdaten(pfad):
        if richtung != "<<":
            continue
        for r in asm.feed(daten):
            verarbeite(telefon, ausgabe, r, zeit)
    return 0


def betrieb(a, ausgabe: Ausgabe) -> int:
    from ergoline.link import PORT_STANDARD, ErgoLink
    import serial
    while True:
        try:
            with ErgoLink(a.port or PORT_STANDARD, echo=None) as link:
                telefon = Telefon(a.amtsholung)
                q = link.sende(p.anmelden())
                print(f"Anmeldung: {q.beschreibung() if q else 'keine Quittung'}", flush=True)
                letzte = time.time()
                while True:
                    try:
                        zeit, r = link.rahmen.get(timeout=1.0)
                    except Exception:
                        if time.time() - letzte > KEEPALIVE_S:
                            if link.sende(p.keepalive()) is None:
                                raise serial.SerialException("Keepalive ohne Quittung")
                            letzte = time.time()
                        continue
                    letzte = zeit
                    verarbeite(telefon, ausgabe, r, zeit)
        except (serial.SerialException, OSError) as e:
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
    ap.add_argument("--wiedergabe", metavar="LOG", help="Mitschnitt statt Telefon verarbeiten")
    a = ap.parse_args()
    ausgabe = Ausgabe(a.anrufe, a.webhook, echo=lambda s: print(s, file=sys.stderr, flush=True))
    if a.wiedergabe:
        return wiedergabe(a.wiedergabe, ausgabe, a.amtsholung)
    return betrieb(a, ausgabe)


if __name__ == "__main__":
    raise SystemExit(main())

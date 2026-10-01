# ErgoLine D340 – Protokoll der PC-Schnittstelle

Offene Dokumentation des seriellen Protokolls, mit dem ein PC ein Philips-Systemtelefon **ErgoLine D340**
(Anlage **Sopho iS3000**, Telekom-Variante Octophon 340) steuert: Anrufe erkennen – mit Anrufernummer –,
annehmen, wählen und auslösen. Ziel: Jede und jeder soll damit einen eigenen TAPI- oder SIP-Daemon bauen können.

**➜ Spezifikation lesen: [schnebeck.github.io/Sopho2SIP/protokoll.html](https://schnebeck.github.io/Sopho2SIP/protokoll.html)**
(im Repository: [`docs/protokoll.html`](docs/protokoll.html))

Die Spezifikation enthält Rahmenformat, alle Meldungen und Aufträge, Zeitverhalten, Ablauf- und Zustandsdiagramme,
die Zuordnung zu SIP und einen Leitfaden für den Daemon. Jede Angabe ist gekennzeichnet als
**bestätigt** (am Gerät gemessen), **Treiber** (aus dem Philips-Treiber abgeleitet) oder **vermutet**.

## Kurzfassung

| | |
|---|---|
| Anschluss | 9-polige Buchse hinten am Telefon, 1:1-Kabel, Pin 2/3/5 |
| Freischaltung | am Telefon: Merkmale → Optionen → „TAPI: Sprache über Telefon“ = Ein |
| Leitung | 1200 Baud, 8O1 |
| Rahmen | `Klasse · Länge · Nutzdaten` – ohne Prüfsumme, ohne Start-/Endzeichen |
| Klassen | `01` Auftrag PC · `02` Meldung Telefon · `03` REJ · `04` ACK · `05` ERR |
| Meldungen | `30` RINGING (mit Anrufernummer) · `31` CONNECTED · `32` DISCONNECTED · `36` DIALTONE · `39` RELEASED · `3e` PROCEEDING · … |
| Aufträge | Anmelden `01 02 01 00` · Wählen `01 L 19 00 98 70 …` · Annehmen `01 02 14 00` · Auflegen `01 02 13 00` |

## Stand

- Empfangsrichtung vollständig mitgeschnitten und entschlüsselt (Anruf mit Nummer, Wahl, Verbindung, Auslösung).
- Senderichtung aus dem originalen Philips-Treiber abgeleitet; der erste Test am Gerät steht aus
  ([`docs/testplan.md`](docs/testplan.md)).
- Offene Fragen stehen am Ende der Spezifikation.

## Weitere Dokumente

| Datei | Inhalt |
|---|---|
| [`docs/protocol.md`](docs/protocol.md) | Arbeitsnotizen zum Protokoll mit Log-Verweisen |
| [`docs/audio_verkabelung.html`](https://schnebeck.github.io/Sopho2SIP/audio_verkabelung.html) | Schaltplan: Audio-Buchse über 600-Ω-Übertrager an die USB-Soundkarte (vorläufig) |
| [`docs/hardware.md`](docs/hardware.md) | Pinbelegung, Messwerte, Menüpunkte, Wartungsmodus des Telefons |
| [`docs/sackgassen.md`](docs/sackgassen.md) | Irrwege, z. B. der inkompatible Octophon-Treiber mit AT-Befehlen |
| [`docs/testplan.md`](docs/testplan.md) | nächste Tests am Gerät |
| [`logs/INDEX.md`](logs/INDEX.md) | Mitschnitte, die die Angaben belegen (Rufnummern durch Platzhalter ersetzt) |
| [`ref/ergoline_tsp/QUELLE.md`](ref/ergoline_tsp/QUELLE.md) | Herkunft des Philips-Treibers (Wayback Machine) mit Prüfsummen |

## Referenzimplementierung (experimentell)

Python 3 mit `pyserial`, keine weiteren Abhängigkeiten:

- `gateway/ergoline/protocol.py` – Rahmen, Meldungen, Aufträge (ohne Ein-/Ausgabe)
- `gateway/ergoline/link.py` – serielle Verbindung mit Quittung und Sitzungslog
- `gateway/ergoline/zustand.py` – Zustandsautomat nach dem Vorbild des Philips-Treibers
- `gateway/sopho2sipd.py` – Daemon: Verbindung, Anmeldung, Keepalive, Anrufdatensätze als JSON-Datei/Webhook ([`docs/anrufdaten.md`](docs/anrufdaten.md))
- `tools/ergo.py` – Mitschnitte dekodieren, mitlesen, Aufträge senden
- Tests: `python3 -m unittest discover -s gateway/tests -v`

```
tools/ergo.py decode logs/serial_20260930_163534.log
gateway/sopho2sipd.py --wiedergabe logs/serial_20260930_163534.log --anrufe -
```

Die Spezifikation wird mit `tools/build_protokoll_doc.py` aus `docs/protokoll.tpl.html` erzeugt.

## Nicht enthalten: der Philips-Treiber

Der Philips-Treiber (`Ergoline.tsp`), Handbuch-Auszüge und das Benutzerhandbuch sind urheberrechtlich geschützt
und liegen nicht im Repository. Der Treiber ist in der Wayback Machine archiviert:

- Direkt-Download: [ergoline.zip (Wayback Machine, 2010-12-01)](https://web.archive.org/web/20101201193039id_/http://tapicall.de/tapi-treiber/nec_philips/telefone/ergoline-serie/ergoline_d330/ergoline.zip)
- SHA-256 `ergoline.zip`: `d278ae82b84d656354e80f650fbd9ae9816d62526e92ea5dcb5483e05b374daf`
- SHA-256 `Ergoline.tsp` (im ZIP): `2b5b2b3e2e3ff51a2ca666b7bc874e9e9d81551a3f67c5357ea8ea297f50b282`

Weitere Fundstellen: [`ref/ergoline_tsp/QUELLE.md`](ref/ergoline_tsp/QUELLE.md) und Abschnitt Quellen der Spezifikation.

## Lizenz

Der Code (`gateway/`, `tools/`) steht unter der **GNU General Public License v3.0 oder später**
(`GPL-3.0-or-later`, siehe [`LICENSE`](LICENSE)). Für die Dokumentation gilt keine gesonderte Lizenz.

## Vorsicht

Eine Telefonanlage lässt sich nicht beliebig zurücksetzen. Nur dokumentierte Aufträge senden, nichts raten, und am
Telefon weder das Service-Menü noch die Wartungscodes 31–34 benutzen.

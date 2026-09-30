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
| [`docs/hardware.md`](docs/hardware.md) | Pinbelegung, Messwerte, Menüpunkte, Wartungsmodus des Telefons |
| [`docs/sackgassen.md`](docs/sackgassen.md) | Irrwege, z. B. der inkompatible Octophon-Treiber mit AT-Befehlen |
| [`docs/testplan.md`](docs/testplan.md) | nächste Tests am Gerät |
| [`logs/INDEX.md`](logs/INDEX.md) | Mitschnitte, die die Angaben belegen (Rufnummern durch Platzhalter ersetzt) |
| [`ref/ergoline_tsp/QUELLE.md`](ref/ergoline_tsp/QUELLE.md) | Herkunft des Philips-Treibers (Wayback Machine) mit Prüfsummen |

## Referenzimplementierung (experimentell)

Python 3 mit `pyserial`, keine weiteren Abhängigkeiten:

- `gateway/ergoline/protocol.py` – Rahmen, Meldungen, Aufträge (ohne Ein-/Ausgabe)
- `gateway/ergoline/link.py` – serielle Verbindung mit Quittung und Sitzungslog
- `tools/ergo.py` – Mitschnitte dekodieren, mitlesen, Aufträge senden
- Tests: `python3 -m unittest discover -s gateway/tests -v`

```
tools/ergo.py decode logs/serial_20260930_163534.log
```

Die Spezifikation wird mit `tools/build_protokoll_doc.py` aus `docs/protokoll.tpl.html` erzeugt.

## Nicht enthalten

Der Philips-Treiber (`Ergoline.tsp`), Handbuch-Auszüge und das Benutzerhandbuch sind urheberrechtlich geschützt
und liegen nicht im Repository. Fundstellen stehen in [`ref/ergoline_tsp/QUELLE.md`](ref/ergoline_tsp/QUELLE.md)
und in der Spezifikation (Abschnitt Quellen).

## Vorsicht

Eine Telefonanlage lässt sich nicht beliebig zurücksetzen. Nur dokumentierte Aufträge senden, nichts raten, und am
Telefon weder das Service-Menü noch die Wartungscodes 31–34 benutzen.

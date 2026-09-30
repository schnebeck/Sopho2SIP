# Sackgassen

Kurzvermerke, damit nichts doppelt versucht wird. Belege wurden gelöscht, soweit sie nichts mehr beitragen.

## Falscher Treiber
- **`Octophon340.tsp` (+ `OctophonGer.hlp`/`OctophonEng.hlp`)**, TAPICall-Download „Octopus 180i/M/M26“:
  **falscher Treiber, inkompatibel** mit unserer D340. Er spricht ASCII/AT (`AT$CAL`, `CAL`, `CPN` …) mit 9600 Baud,
  Zeilenende CRLF, bricht an Nullbytes ab, keine Rahmen, kein ACK. Unsere D340 spricht binär mit 1200 Baud.
  Statisch analysiert und am 2026-09-30 aus `ref/` gelöscht. Vermutlich für Telekom-Firmware der Octophon 340i
  oder den V.24-Terminal-Adapter geschrieben.
- Richtiger Treiber: `ref/ergoline_tsp/Ergoline.tsp`.

## Widerlegte Annahmen
| Annahme | Stand |
|---|---|
| 9600 Baud 8N1 (aus dem falschen Treiber) | falsch: **1200** (Wartungscode 63, Messung), laut `Ergoline.tsp` **8O1** + Xon/Xoff |
| AT-Befehle (`ATI0`, `AT`, `ATI`, `ATI1`, `AT$STA1`), CR/CRLF, alle Raten 1200–38400 | nie verstanden; Antwort bestenfalls `05 00` |
| Stille bei allen Raten ⇒ Telefon sendet nicht | Fehlschluss: Schnittstelle war aus (TAPI-Schalter) |
| Adapter, Kabel, Pinbelegung, Stecker defekt | alles in Ordnung (Loopback, Pegelmessung) |
| DB9 dient der ASCII-Tastatur | nein, die ist Infrarot |
| PC-Schnittstelle braucht Netzteil | nein, nur V.24/DSS |
| Baudrate im Telefon einstellbar | nur für V.24-Option, nicht für die DB9 |
| `05 00` ist ein Herzschlag | nein, Antwort ~1,5 s nach jeder Eingabe |
| Hex-Strings `3B`/`0A`/`3E`/`0F` im falschen Treiber = Meldungstypen | nein, ASCII-Ursachencodes |
| `98` = Anrufkennung | nein, fester Wert |
| `36 01` = abgehoben | `L3_STATUSDIALTONE` (Treiber) |
| `3b`/`3a` = unbekanntes Ein/Aus-Paar | FACILITY ACTIVATED/DEACTIVATED, `0a` = Hörer, `30` = DTMF (Treiber) |
| Telefon erwartet Quittung für seine Meldungen | nein, nur PC-Aufträge (`01`) werden mit `04` quittiert (Treiber) |

**Eigentliche Ursache der Stille bis 2026-09-30 16:28:** Merkmale → Optionen, beide TAPI-Schalter aus.

## Werkzeug
- Umschalt-Abtaster (mit 9600 senden, dann auf hohe Rate umschalten) zu langsam → gelöscht; Ersatz `tools/bitbang_scope.py`.
- Bitbang braucht Vorausschreiben (2 Blöcke à 64), sonst Lücken; pyftdi-Parameter heißt `baudrate`, nicht `frequency`.
- `pkill -f <muster>` trifft auch die eigene Shell → PID gezielt per `pgrep` bestimmen.

## Quellen
- Scribd blockiert automatischen Abruf → Handbücher über ManualsLib.
- Aktuelle TAPICall-Seiten für ErgoLine D330/Octophon 340i ohne Download; archivierter Download `…/download/treiber/481100869/`
  war ein falsches (FRITZ!Box-)Paket. Gefunden hat es erst der Wayback-Index (`ergoline.zip`, 2010).

## Infrastruktur
- rpi-imager 1.8.5 kann kein cloud-init → Image per `dd`, cloud-init-Dateien selbst auf bootfs.

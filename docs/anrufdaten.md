# Anrufdatensätze (Schnittstelle zur Nextcloud-App)

Der Daemon `gateway/sopho2sipd.py` erzeugt für jeden beendeten Vorgang an der D340 einen Datensatz – als JSON-Zeile
in eine Datei (Standard `~/.local/share/sopho2sip/anrufe.jsonl`) und optional per **HTTP-POST** an `--webhook URL`
(`Content-Type: application/json`, ein Datensatz je Anfrage, Antwort wird nicht ausgewertet).

Stand: Ausbaustufe 1 (nur Telefonseite, noch ohne SIP). Felder können ergänzt, aber nicht umbenannt werden.

## Felder

| Feld | Typ | Bedeutung |
|---|---|---|
| `kennung` | int | laufende Nummer seit Start des Daemons |
| `ergebnis` | str | `angenommen`, `verpasst` (eingehend) · `verbunden`, `nicht_erreicht`, `ohne_wahl` (abgehend) |
| `richtung` | str | `ein` oder `aus` |
| `nummer` | str | Rufnummer ohne Amtsholung (`""` wenn keine) |
| `extern` | bool | `true`, wenn die Nummer mit der Amtsholung (`01`) kam/gewählt wurde |
| `nummer_roh` | str | Ziffern wie vom Telefon gemeldet, inkl. Amtsholung |
| `name` | str/null | Name aus der Rückwärtssuche (nur externe Nummern, nur mit `--rueckwaertssuche`) |
| `ort` | str/null | Ort aus der Rückwärtssuche |
| `beginn` | str | ISO 8601 mit Zeitzone: Klingelbeginn bzw. Wählton |
| `verbunden` | str/null | Zeitpunkt der Verbindung |
| `ende` | str | Zeitpunkt der Freigabe (RELEASED) |
| `angenommen` | bool | ob eine Verbindung zustande kam |
| `dauer_s` | float | Gesprächsdauer von Verbindung bis Trennung |
| `ursache` | str/null | Auslöseursache hex (`""` = keine, z. B. `"8f"`) |
| `ausloeser` | str/null | `eigene_seite` (Ursache leer) oder `gegenseite` (vermutet aus Beobachtung) |
| `verlauf` | list | Zustände nach TAPI (`OFFERING`, `CONNECTED`, …) |

## Beispiel (aus einem Mitschnitt, Nummer ersetzt)

```json
{"kennung": 3, "ergebnis": "verbunden", "richtung": "aus", "nummer": "01700000000", "extern": true,
 "nummer_roh": "0101700000000", "name": null, "ort": null, "beginn": "2026-09-30T16:38:37.791+02:00", "verbunden": "2026-09-30T16:38:49.832+02:00",
 "ende": "2026-09-30T16:39:20.128+02:00", "angenommen": true, "dauer_s": 21.9, "ursache": "8f",
 "ausloeser": "gegenseite", "verlauf": ["DIALTONE", "DIALING", "PROCEEDING", "RINGBACK", "CONNECTED", "DISCONNECTED", "IDLE"]}
```

## Ohne Telefon ausprobieren

```
gateway/sopho2sipd.py --wiedergabe logs/serial_20260930_163534.log --anrufe - --webhook http://localhost:8080/…
```

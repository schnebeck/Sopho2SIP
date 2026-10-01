# Verzeichnis der Mitschnitte

Nur Mitschnitte, die etwas belegen, das wir weiter brauchen. Alles andere wurde gelöscht (Ergebnisse stehen in
`docs/sackgassen.md`). Rufnummern sind durch `0101700000000` ersetzt; Originale liegen nur lokal in `privat/`.
Neue Sitzungslogs `logs/ergo_*.log` sind per `.gitignore` ausgeschlossen; veröffentlicht werden bereinigte Kopien `test_*.log`. Alle Mitschnitte bei eingeschaltetem „TAPI: Sprache über Telefon“.
Werkzeuge: `serial` = `tools/serial_probe.py`, `bitbang` = `tools/bitbang_scope.py` (`.bin` = Rohabtastwerte, Bit 1 = RXD).

| Datei | Werkzeug | gesendet | Nutzeraktion | Beleg für |
|---|---|---|---|---|
| `serial_20260930_163534.log` | serial 1200 passiv, 10 min | – | Anruf ein/Annahme/Auflegen, Abheben ohne Wahl, externe Wahl, Auflegen beider Seiten | alle Ereignisrahmen (`protocol.md` Abschn. 4) |
| `bitbang_20260930_163321.*` | bitbang 19,2 kHz | `ATI0` @9600 | – | 1200 Baud 8N1; Antwort `05 00` 1,52 s später |
| `bitbang_20260930_163416.*` | bitbang | `ATI0` @1200 | – | gleiche Antwort `05 00` auch bei 1200 |
| `bitbang_20260930_163457.*` | bitbang, 10 s ohne Befehl | – | – | kein periodischer Takt (nur Reaktion auf Schaltimpuls) |
| `bitbang_20260930_163507.*` | bitbang, 3 s Ruhe + Befehl | `ATI0` @9600 | – | `05 00` genau 1,51 s nach der Eingabe |
| `test_20261001_084855_anmelden.log` | ergo 1200 8O1 | `01 02 01 00` | – | ACK `04 00`, danach Meldung Typ `01` |
| `test_20261001_084917_keepalive.log` | ergo 1200 8O1 | `01 02 00 00` | – | ACK `04 00` |
| `test_20261001_084929_empfang_8O1.log` | ergo 1200 8O1 | Anmelden | Anruf, am Telefon angenommen und aufgelegt | Empfang mit 8O1 fehlerfrei |
| `test_20261001_085405_annehmen.log` | ergo annahmetest | Anmelden, Annehmen, Auflegen | Lautsprecher-Taste nach 8 s | Annehmen bestätigt; Gespräch durch Taste beendet |
| `test_20261001_085744_annehmen_auflegen.log` | ergo annahmetest | Anmelden, Annehmen, Auflegen (4 s) | keine | **Annehmen und Auflegen bestätigt** |
| `test_20261001_130201_pi_angenommen_verpasst.log` | Daemon `sopho2sipd.py` auf dem Pi | Anmelden, Keepalive | Anruf am Telefon angenommen; zweiter Anruf nicht angenommen | Betrieb am Pi; verpasster Anruf = RINGING → RELEASED `08 01 8f` |
| `test_20261001_150042_waehlen_extern.log` | ergo waehltest am Pi | Anmelden, Belegen, Wählen (extern), Auflegen | Handy angenommen | **Belegen und Wählen bestätigt**; kein DIALTONE nach Belegen |

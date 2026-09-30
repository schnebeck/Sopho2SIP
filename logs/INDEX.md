# Verzeichnis der Mitschnitte

Nur Mitschnitte, die etwas belegen, das wir weiter brauchen. Alles andere wurde gelöscht (Ergebnisse stehen in
`docs/sackgassen.md`). Alle Mitschnitte bei eingeschaltetem „TAPI: Sprache über Telefon“.
Werkzeuge: `serial` = `tools/serial_probe.py`, `bitbang` = `tools/bitbang_scope.py` (`.bin` = Rohabtastwerte, Bit 1 = RXD).

| Datei | Werkzeug | gesendet | Nutzeraktion | Beleg für |
|---|---|---|---|---|
| `serial_20260930_163534.log` | serial 1200 passiv, 10 min | – | Anruf ein/Annahme/Auflegen, Abheben ohne Wahl, externe Wahl, Auflegen beider Seiten | alle Ereignisrahmen (`protocol.md` Abschn. 4) |
| `bitbang_20260930_163321.*` | bitbang 19,2 kHz | `ATI0` @9600 | – | 1200 Baud 8N1; Antwort `05 00` 1,52 s später |
| `bitbang_20260930_163416.*` | bitbang | `ATI0` @1200 | – | gleiche Antwort `05 00` auch bei 1200 |
| `bitbang_20260930_163457.*` | bitbang, 10 s ohne Befehl | – | – | kein periodischer Takt (nur Reaktion auf Schaltimpuls) |
| `bitbang_20260930_163507.*` | bitbang, 3 s Ruhe + Befehl | `ATI0` @9600 | – | `05 00` genau 1,51 s nach der Eingabe |

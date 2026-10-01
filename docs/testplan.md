# Testplan: Aufträge an die D340 (erster Sendetest)

Werkzeug: `tools/ergo.py` (Rahmen, Quittung, Log nach `logs/ergo_*.log`). Offline-Selbsttest vorher:
`python3 -m unittest discover -s gateway/tests -v`.

## Vorbedingungen (Nutzer)
- FTDI-Adapter am Laptop, 1:1-Kabel an der D340; `ls /dev/serial/by-id/` zeigt `usb-FTDI_FT232R_USB_UART_A97WEQGD…`.
- Merkmale → Optionen: „TAPI: Sprache über Telefon“ = Ein. Telefon in Ruhe (Hörer aufgelegt).

## Schritt 1 – Empfang mit 8O1 (frei) — erledigt 2026-10-01, fehlerfrei
`tools/ergo.py listen --dauer 60`, währenddessen anrufen, abheben, auflegen.
Erwartet: dieselben Meldungen wie `serial_20260930_163534.log`, jetzt mit Klartext.
Falls nur Salat: `--paritaet N` gegenprüfen.

## Schritt 2 – Anmelden (frei) — erledigt 2026-10-01: ACK `04 00`
`tools/ergo.py anmelden --dauer 20`
| Ergebnis | Bedeutung | nächster Versuch |
|---|---|---|
| `ACK …` binnen 5 s | Senderichtung bestätigt, ACK-Format notieren | Schritt 3 |
| `REJ …` | Rahmen verstanden, abgelehnt | Inhalt notieren, `keepalive` testen |
| `ERR` (`05 00`) nach ~1,5 s | nicht verstanden | `--paritaet N`, dann `--xonxoff` |
| nichts | – | Pegel/Stecker, `--paritaet N` |

## Schritt 3 – Keepalive (frei) — erledigt 2026-10-01: ACK `04 00`
`tools/ergo.py keepalive` → erwartet `ACK`.

## Schritt 4 – Gesprächsaufträge (nur nach Freigabe durch den Nutzer)
Reihenfolge, je einzeln und mit Rückfrage:
1. **Erledigt 2026-10-01** (`tools/ergo.py annahmetest --freigabe`). Eingehend annehmen: Nutzer ruft an → `tools/ergo.py annehmen --freigabe` während es klingelt.
   Erwartet: `ACK`, dann `CONNECTED`; Sprache über Hörer/Freisprechen (Schalter „über Telefon“).
2. **Erledigt 2026-10-01.** Auflegen: `tools/ergo.py auflegen --freigabe` → `ACK`, `DISCONNECTED`, `RELEASED`.
3. Wählen intern: `tools/ergo.py waehlen <Nebenstelle> --freigabe` (vom Nutzer genannte Testnummer).
   Hinweis: Der Treiber sendet vorher `belegen` (`01 02 11 00`) im Ruhezustand; bei `ERR`/`REJ` erst
   `tools/ergo.py belegen --freigabe`, dann `waehlen`.
4. Wählen extern: Nummer mit Amtsholung `01` (z. B. `01…`), nur mit Freigabe.

## Danach
Ergebnisse in `docs/protocol.md` (Status „bestätigt“ mit Log), nützliche Logs in `logs/INDEX.md`, nutzlose löschen.

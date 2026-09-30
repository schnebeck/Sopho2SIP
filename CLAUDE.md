# Sopho-SIP-Gateway (ErgoLine D340 ↔ SIP)

Dieses Projekt macht einen Nebenstellenanschluss einer alten **Philips Sopho iS3000**-Telefonanlage SIP-fähig.
Ein Raspberry Pi steuert ein vorhandenes Systemtelefon **ErgoLine D340** über dessen serielle PC-Schnittstelle
und greift die Sprache über dessen Audio-Schnittstelle ab. Nach außen spricht der Pi SIP.

## Ziel und Randbedingungen

- Managementsoftware und Softphones sprechen nur SIP. Der einzige Anschluss nach außen ist eine Sopho-Nebenstelle.
- Die Managementsoftware ist eine eigene **Nextcloud-App** des Nutzers (verwaltet SIP-Telefone, verknüpft mit Kontakten).
  Der Pi ist ihre SIP-Hardware-Schnittstelle zur Sopho. Der Pi ersetzt die D340 als Bediengerät (Tasten, Hörer);
  ein **Bluetooth-Headset (HFP) am Pi** ersetzt den Hörer. Die D340 bleibt als Leitungsmodem im Hintergrund.
- **Die Sopho-Anlage wird nicht angefasst.** Kein Zugriff, keine Umkonfiguration, keine Wartungsschnittstelle.
- **Anrufernummern sind Pflicht.** Sie müssen als SIP-Caller-ID (From-Header) ankommen.
- Die D340 wird nicht geöffnet und bleibt unverändert. Sie dient als „Leitungsmodem“ zur Anlage.
- Verworfene Ansätze (nur noch Plan B): passives Mitlauschen auf der UPN-Leitung mit Raspberry Pi Pico/PIO,
  eigenes Endgerät mit eigener Leitungsschnittstelle, EPROM-Analyse der D340-Firmware.

## Hardware-Erkenntnisse (Details: `docs/hardware.md`)

### Telefon
- Typenschild **ERGOLINE 340-2/LG INT**, 12NC 9600 009 630 02 (`ref/foto_typenschild.png`), UPN, leitungsgespeist,
  nur 9-polige PC-Buchse (keine V.24-Option). Terminal-Software **V4.03.40.01**.
- Telekom-Variante: Octophon 340(i); Anlage bei der Telekom: Octopus 180i/M/M26 (Suchbegriffe, aber andere Firmware).
- Handbuch-Auszüge in `ref/` stammen aus dem **„ErgoLine D330/D340 Customer Engineer Manual“** (ManualsLib).
- Blockschaltbild (`ref/blockschaltbild_d340.png`): Der TAPI-Port hängt am Mikroprozessor, nicht am D-Kanal —
  wir sprechen mit der Telefon-Firmware, nicht mit der Anlage.
- **PC-Schnittstelle erst aktiv, wenn Merkmale → Optionen → „TAPI: Sprache über Telefon“ (oder „… über Zusatzgerät“) = Ein.**

### PC-Schnittstelle (Steuerung)
- DB9-**Buchse** hinten, Telefon = DCE, 1:1-Kabel, nur Pin 2 (Telefon sendet), 3 (Telefon empfängt), 5 (GND).
- RS-232-Pegel (±5 V gemessen). **1200 Baud** (gemessen, fest), **8O1 + Xon/Xoff** laut `Ergoline.tsp`.

### Audio-Schnittstelle (Sprache)
- RJ11 an der Unterseite: Pin 1 X_OUT, Pin 2 X_IN, Pin 3 GNDA (`ref/audio_interface_pinout.png`).
- **Achtung:** Die benachbarte RJ11 „Static Interface“ führt auf Pin 1 +5 V. Vor dem Anschließen Pin 1 gegen Pin 3 messen.
- „TAPI: Sprache über Zusatzgerät“ legt den Sprechweg auf diese Buchse. Pegel, Impedanz, Echo: noch zu testen.

### Gateway-Hardware
- Raspberry Pi 4, **Ethernet** (kein WLAN für VoIP). Bluetooth nur für das Headset (HFP).
- Der Arbeits-Laptop ist die Konsole zum Pi: Entwicklung hier im Repo, Ausführung auf dem Pi per `ssh sopho-gw`.
- USB-RS232-Adapter FTDI FT232R, 1:1-Verlängerung. Im Code immer `/dev/serial/by-id/…`, nie `/dev/ttyUSB0`.
  Der FT232R dient auch als Logikanalysator (`tools/bitbang_scope.py`).
- USB-Audio **Behringer UCA222**; 2× NF-Übertrager 600 Ω 1:1, Spannungsteiler vor X_IN.
- Sprache ist Schmalband (G.711 A-law, 8 kHz). SIP-Codec **PCMA**.

## Das serielle Protokoll (Details: `docs/protocol.md`)

- **Binärrahmen** `<Klasse> <Länge> <Nutzdaten>`, 1200 8O1. Klassen: `01` Auftrag PC, `02` Meldung Telefon, `03` REJ, `04` ACK, `05` ERR.
  Nummern und Ursachen als Q.931-artige Elemente (`6c` Anrufer, `70` Ziel, `08` Ursache).
- Empfangsrichtung ist verstanden (Anruf mit Anrufernummer, Wahl, Rufton, verbunden, Auslösung, Ruhe).
- Aufträge (aus `Ergoline.tsp`, am Gerät noch ungetestet): Anmelden `01 02 01 00`, Wählen `01 LL 19 00 98 70 …`,
  Annehmen `01 02 14 00`, Auflegen `01 02 13 00`; das Telefon quittiert mit `04`. Unverstandene Eingaben beantwortet das Telefon
  nach ~1,5 s mit `05 00`.
- **Maßgebliche Quelle:** `ref/ergoline_tsp/Ergoline.tsp` („Philips ErgoLine D330/D340 TSP for TAPI 2.x“, V2.1.2,
  2002; Herkunft in `ref/ergoline_tsp/QUELLE.md`). Enthält `SendFrame` mit ACK, `L2_ACK_PHONE`, Versionsabfrage.
- Der früher benutzte `Octophon340.tsp` (ASCII/AT, 9600) ist **inkompatibel** und wurde gelöscht (`docs/sackgassen.md`).

## Zielarchitektur

```
Sopho ─UPN─ D340 ─PC-Schnittstelle (Binärrahmen, 1200 8N1)─ USB-RS232 ─┐
                 └─Audio-I/O (X_OUT/X_IN)─ Übertrager ─ UCA222 ─────────┤ Pi: Python-Daemon ⇄ baresip (ctrl_tcp) ─SIP─ Asterisk/SIP-Server ─ Nextcloud-App / Softphones
                                                  BT-Headset (HFP) ─────┘
```

- **SIP nicht selbst implementieren.** baresip mit `ctrl_tcp` übernimmt SIP, RTP, Audio, AEC.
- **Asterisk** (PJSIP) als Registrar, falls kein SIP-Server existiert (offene Frage).
- Abläufe: Eingehend: Rahmen `30` mit Anrufernummer → SIP-INVITE mit From = normalisierte Nummer (Amtsziffer
  entfernen) → bei Annahme Annahme-Rahmen (noch unbekannt). Abgehend: INVITE → Wahl-Rahmen (unbekannt).
  Auflegen: BYE ↔ Auslöse-Rahmen bzw. Meldung `32`/`39`.
- Eine D340 = ein Gespräch gleichzeitig.

## Vorgehen (Phasen)

1. **Pi in Betrieb nehmen:** SD-Karte ist vorbereitet (Trixie Lite, cloud-init), danach `tools/pi_bootstrap.sh`. — offen
2. **Seriell verifizieren:** erledigt (1200 8N1, Freischaltung per TAPI-Schalter, Empfangsrahmen mitgeschnitten).
3. **Protokoll klären:** `Ergoline.tsp` analysieren (Rahmen, ACK, Befehle), dann mit Freigabe Senden testen. — laufend
4. **Audio verifizieren:** UCA222, X_OUT/X_IN, „Sprache über Zusatzgerät“. Ergebnisse in `docs/hardware.md`.
5. **SIP-Stack:** baresip mit `ctrl_tcp`, Codec PCMA, erst lokal mit Softphone testen.
6. **Gateway-Daemon:** Python 3 (asyncio), Rahmen-Decoder, Zustandsautomat, Übersetzung seriell ↔ baresip.
7. **Betrieb:** systemd-Units, Logging, Wiederanlauf bei Verbindungsverlust zum Telefon.

## Arbeitsregeln für Claude Code

- **Nichts an das Telefon senden, was einen Anruf auslöst oder beeinflusst, ohne ausdrückliche Rückfrage.**
  Frei: reines Mitlesen. Jeder Senderahmen, dessen Wirkung nicht aus `Ergoline.tsp` belegt ist, braucht eine
  Freigabe; Wählen nur mit einer vom Nutzer genannten Testnummer. Nichts raten.
  Die Anlage ist nicht rücksetzbar; eine gesperrte Nebenstelle wäre nicht selbst zu beheben.
- Serielle Sitzungen mit Zeitstempel und Richtung (`>>`/`<<`, Rohbytes) nach `logs/` schreiben.
  **Nur behalten, was etwas Weiterführendes belegt**; nutzlose Mitschnitte löschen. Behaltene Logs in
  `logs/INDEX.md` eintragen. Sackgassen nur knapp in `docs/sackgassen.md` vermerken, ohne Belegsammlung.
- Hypothesen in `docs/protocol.md` als **vermutet** vs. **bestätigt** kennzeichnen, mit Verweis auf das Log.
  Neue gesicherte Erkenntnisse zusätzlich in `docs/protokoll.tpl.html` (Status bestätigt/Treiber/vermutet) übernehmen,
  dann `tools/build_protokoll_doc.py` ausführen. Veröffentlichte Fassung: https://claude.ai/artifact/QbyHyYSk8rnWytsR8QnzJi
- Hardware-Schritte (Messen, Umstecken, Anrufe auslösen, Menü am Telefon) macht der Nutzer. Claude sagt konkret,
  was zu tun ist, und wartet. Am Telefon nie: Service-Menü, Wartungscodes 31–34, `*`+`3`+`5` beim Einstecken.
- `ref/` = Referenzmaterial. Quelldateien darin **nie inhaltlich verändern**. Neue Quellen dürfen ergänzt werden
  (mit Herkunftsnachweis: URL, Datum, SHA-256, z. B. `QUELLE.md`). Nachweislich falsche Quellen dürfen gelöscht und
  durch neu gesammelte ersetzt werden; Vermerk in `docs/sackgassen.md`.
- **Öffentliches Repo (GitHub schnebeck/Sopho2SIP):** Treiber, Handbuch-Auszüge/-PDFs und Menübaum-Bild bleiben lokal
  (`.gitignore`), echte Rufnummern nie committen (Platzhalter `01700000000`). Vor jedem Push `git status` und
  `.gitignore` prüfen. Im Mittelpunkt steht die Dokumentation (`docs/protokoll.html`, README).
- Stil: knapp, präzise, kommandozeilenorientiert. Python 3 mit `pyserial`, keine unnötigen Abhängigkeiten.
- Sprache in Doku und Kommentaren: Deutsch.

## Projektstruktur

```
CLAUDE.md
docs/protokoll.html     # Spezifikation für Daemon-Entwickler (erzeugt, nicht von Hand ändern)
docs/protokoll.tpl.html # Vorlage dazu; Grafiken in tools/build_protokoll_doc.py
docs/protocol.md        # Arbeitsnotizen zum Protokoll, bestätigt/vermutet
docs/sackgassen.md      # Kurzvermerke zu Irrwegen (vor neuen Versuchen lesen)
docs/hardware.md        # Pinbelegungen, Messwerte, Verkabelung, Handbuch-Befunde, Wartungsmodus
docs/img/               # Menübaum der D340
ref/                    # Handbuch-Auszüge, Fotos (Quellen nicht verändern)
README.md               # GitHub-Startseite, stellt die Spezifikation in den Mittelpunkt
privat/                 # lokal, nie veröffentlichen (Original-Log mit echter Rufnummer, Sicherungen)
ref/ergoline_tsp/       # Philips ErgoLine D330/D340 TSP (maßgeblicher Treiber), Herkunft in QUELLE.md
tools/ergo.py           # Hauptwerkzeug: Rahmen dekodieren/mitlesen/Aufträge senden (Sperre ohne --freigabe)
tools/serial_probe.py   # Rohmitschnitt ohne Rahmenlogik (Altwerkzeug)
tools/bitbang_scope.py  # FT232R als Logikanalysator (Bitbang, braucht pyftdi)
tools/pi_bootstrap.sh   # Grundeinrichtung des Pi (Pakete, Gruppen, NTP)
tools/build_protokoll_doc.py  # erzeugt docs/protokoll.html (Standardbibliothek)
gateway/ergoline/       # Protokoll (protocol.py) und serielle Verbindung (link.py), Basis für den Daemon
gateway/tests/          # Tests (python3 -m unittest discover -s gateway/tests)
docs/testplan.md        # nächste Tests am Gerät
logs/                   # Mitschnitte, Übersicht in logs/INDEX.md
```

## Offene Punkte

- Protokoll: Aufträge aus `Ergoline.tsp` am Gerät bestätigen (erst Anmelden `01 02 01 00`, dann mit Freigabe Wählen/Annehmen/Auflegen).
- Kommen Ereignisse auch ohne jede vorherige Eingabe (Neustart-Test)?
- Audio: Pegel, Wirkung von X_IN, Inhalt von X_OUT, „Sprache über Zusatzgerät“.
- Gibt es bereits einen SIP-Server, oder wird Asterisk auf dem Pi benötigt?
- Schnittstelle der Nextcloud-App zu den Telefonen (HTTP-API/Action-URLs, AMI/ARI, SIP)?
- Pi noch nicht in Betrieb.

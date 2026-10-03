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
- „TAPI: Sprache über Zusatzgerät“ legt den Sprechweg auf diese Buchse. Gemessen 2026-10-01: X_OUT gut, kein Echo;
  X_IN nur mit Merkmal `4f` „X-Eingang statt Mikrofon“ (Auftrag `01 03 26 00 4f` im Gespräch). Details `docs/hardware.md`.

### Gateway-Hardware
- Raspberry Pi 4, **Ethernet** (kein WLAN für VoIP). Bluetooth nur für das Headset (HFP).
- Der Arbeits-Laptop ist die Konsole zum Pi: Entwicklung hier im Repo, Ausführung auf dem Pi per `ssh sopho-gw`.
- USB-RS232-Adapter FTDI FT232R, 1:1-Verlängerung. Im Code immer `/dev/serial/by-id/…`, nie `/dev/ttyUSB0`.
  Der FT232R dient auch als Logikanalysator (`tools/bitbang_scope.py`).
- USB-Audio **Behringer UCA222** (ALSA `CODEC`, PCM −6 dB gespeichert); 2× NF-Übertrager 600 Ω 1:1, ohne Teiler.
- Sprache ist Schmalband (G.711 A-law, 8 kHz). SIP-Codec **PCMA**.

## Das serielle Protokoll (Details: `docs/protocol.md`)

- **Binärrahmen** `<Klasse> <Länge> <Nutzdaten>`, 1200 8O1. Klassen: `01` Auftrag PC, `02` Meldung Telefon, `03` REJ, `04` ACK, `05` ERR.
  Nummern und Ursachen als Q.931-artige Elemente (`6c` Anrufer, `70` Ziel, `08` Ursache).
- Empfangsrichtung ist verstanden (Anruf mit Anrufernummer, Wahl, Rufton, verbunden, Auslösung, Ruhe).
- Aufträge (aus `Ergoline.tsp`): Anmelden `01 02 01 00`, Keepalive `01 02 00 00`, Annehmen `01 02 14 00`, Auflegen
  `01 02 13 00`, Belegen `01 02 11 00`, Wählen `01 LL 19 00 98 70 …` **am Gerät bestätigt** (2026-10-01, Quittung `04 00`). Unverstandene Eingaben beantwortet das Telefon
  nach ~1,5 s mit `05 00`. **Watchdog:** 30 s ohne Rahmen vom PC → die D340 legt PC-Gespräche auf; Keepalive nach
  15 s ohne Senden (bestätigt).
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
- **Asterisk** (PJSIP) auf dem Pi als Registrar (Entscheidung Nutzer 2026-10-01), Konten `tel1`/`tel2`.
- Abläufe (`docs/betrieb.md`): Eingehend: Rahmen `30` → baresip ruft `sip:<Anrufernummer ohne 01>@Asterisk`, der
  Wählplan macht daraus die Caller-ID → Softphone nimmt ab → Annehmen `01 02 14 00`. Abgehend: Softphone wählt →
  Asterisk ruft baresip mit der Nummer als Absender → Belegen + Wählen → bei `31` nimmt baresip an.
  Auflegen: BYE ↔ `01 02 13 00` bzw. Meldung `32`/`39`.
- Eine D340 = ein Gespräch gleichzeitig.

## Vorgehen (Phasen)

1. **Pi in Betrieb nehmen:** erledigt 2026-10-01 (Trixie Lite, cloud-init, `tools/pi_bootstrap.sh`, Repo unter `~/Sopho2SIP`).
2. **Seriell verifizieren:** erledigt (1200 8N1, Freischaltung per TAPI-Schalter, Empfangsrahmen mitgeschnitten).
3. **Protokoll klären:** `Ergoline.tsp` analysieren (Rahmen, ACK, Befehle), dann mit Freigabe Senden testen. — laufend
4. **Audio verifizieren:** UCA222, X_OUT/X_IN, „Sprache über Zusatzgerät“. Ergebnisse in `docs/hardware.md`.
5. **SIP-Stack:** Asterisk 22 und baresip 4.12 (beide aus dem Quelltext) laufen auf dem Pi (`docs/betrieb.md`).
   Offen: Test mit echtem Softphone, Sprache über UCA222.
6. **Gateway-Daemon:** Stufe 1 fertig (Zustandsautomat, Anrufdatensätze, Keepalive, Wiederanlauf); Stufe 2:
   Steuerbefehle und Brücke seriell ↔ baresip (`gateway/sipbruecke.py`) gebaut, Steuerung noch gesperrt.
7. **Betrieb:** Dienst `sopho2sipd` läuft auf dem Pi (systemd, startet nach Neustart, Ereignisse im Journal,
   Wiederanlauf bei Verbindungsverlust), Logrotation, Firewall (SIP/RTP/Portal nur aus 130.75.63.128/25 und VPN).
   Webportal auf Port 8080 (Passwort). Gesprächsaufträge aus dem Portal erst mit `--steuerung`.

## Arbeitsregeln für Claude Code

- **Nichts an das Telefon senden, was einen Anruf auslöst oder beeinflusst, ohne ausdrückliche Rückfrage.**
  Frei: reines Mitlesen. Jeder Senderahmen, dessen Wirkung nicht aus `Ergoline.tsp` belegt ist, braucht eine
  Freigabe; Wählen nur mit einer vom Nutzer genannten Testnummer. Nichts raten.
  Die Anlage ist nicht rücksetzbar; eine gesperrte Nebenstelle wäre nicht selbst zu beheben.
  `--steuerung` im Dienst nur nach Freigabe des Nutzers einschalten.
- Der Pi hat eine öffentliche Adresse: Ports nur über `gateway/betrieb/sopho2sip.nft` öffnen (mit `tools/firewall.sh`),
  nie SIP/Portal ohne Netzbeschränkung. Externe Wahl (Amtsholung `01`) ist Gebührenbetrugs-Ziel.
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
- Lizenz: Code in `gateway/` und `tools/` ist GPL-3.0-or-later; neue Code-Dateien bekommen als erste Zeile
  (nach dem Shebang) `# SPDX-License-Identifier: GPL-3.0-or-later`. Die Dokumentation hat keine gesonderte Lizenz.
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
tools/log_bereinigen.py # Mitschnitt für das Repo bereinigen (Rufnummer → Platzhalter)
tools/serial_probe.py   # Rohmitschnitt ohne Rahmenlogik (Altwerkzeug)
tools/bitbang_scope.py  # FT232R als Logikanalysator (Bitbang, braucht pyftdi)
tools/pi_bootstrap.sh   # Grundeinrichtung des Pi (Pakete, Gruppen, NTP)
tools/asterisk_build.sh # Asterisk 22 LTS aus dem Quelltext (Trixie hat kein Paket)
tools/firewall.sh       # Firewall laden, mit automatischer Rücknahme gegen Aussperren
tools/asterisk_config.sh # Asterisk/baresip-Konfiguration einspielen, SIP-Passwörter erzeugen
tools/baresip_build.sh  # baresip 4.x + re aus dem Quelltext (Trixie hat nur 1.1.0)
tools/audio_test.sh     # Audiotest im Gespräch (Aufnahme X_OUT, Töne/Nachricht auf X_IN), braucht Freigabe
tools/build_protokoll_doc.py  # erzeugt docs/protokoll.html (Standardbibliothek)
tools/build_audio_doc.py      # erzeugt docs/audio_verkabelung.html (Schaltplan Audio)
gateway/ergoline/       # protocol.py (Rahmen), link.py (seriell), zustand.py (Zustandsautomat), logdatei.py
gateway/sopho2sipd.py   # Daemon (Stufe 1: Anrufdatensätze als JSON/Webhook, Format in docs/anrufdaten.md)
gateway/betrieb/        # Dienst (sopho2sipd.service), Logrotation, Firewall (nftables) für den Pi
gateway/portal.py       # Webportal (Anrufliste, Rückruf, Wähltastatur), Thread im Daemon
gateway/sipbruecke.py   # Brücke Telefon ⇄ baresip (ctrl_tcp)
gateway/rueckwaerts.py  # Rückwärtssuche (11880, Das Örtliche) mit Zwischenspeicher
gateway/asterisk/       # Asterisk-Konfiguration (PJSIP, Wählplan); Passwörter nur auf dem Pi
gateway/baresip/        # baresip-Konfiguration, eigenes Modul dcsperre/ (DC-Blocker, C)
gateway/web/index.html  # Oberfläche des Portals (ohne externe Abhängigkeiten)
gateway/tests/          # Tests (python3 -m unittest discover -s gateway/tests)
docs/testplan.md        # nächste Tests am Gerät
docs/betrieb.md         # Dienste, Ports, Einrichtung und Sicherheit auf dem Pi
logs/                   # Mitschnitte, Übersicht in logs/INDEX.md
hardware/kicadgen.py    # gemeinsamer KiCad-Generator (Symbole, Leitungen, hierarchische Blätter, ERC/Netzlisten-Prüfung)
hardware/hat/           # HAT-Entwurf (KiCad, aus erzeuge_schaltplan.py), README mit offenen Prüfpunkten
hardware/cm4/           # CM4-Träger (hierarchisch; eMMC/µSD, WLAN/Ethernet), nutzt die HAT-Blöcke
```

## Offene Punkte

- Protokoll: Bedeutung der Meldung Typ `01`; Nachwahl/DTMF im Gespräch.
- Kommen Ereignisse auch ohne jede vorherige Eingabe (Neustart-Test)?
- `--steuerung` im Dienst einschalten (Freigabe Nutzer); DTMF-Nachwahl im Gespräch prüfen.
- Schnittstelle der Nextcloud-App zu den Telefonen (HTTP-API/Action-URLs, AMI/ARI, SIP)?

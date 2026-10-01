# Hardware, Verkabelung, Messwerte

Stand 2026-09-30. Widerlegte Verdachte: siehe [`sackgassen.md`](sackgassen.md).

## Telefon
- ERGOLINE 340-2/LG INT (UPN), leitungsgespeist, kein Netzteil angeschlossen, nur 9-polige PC-Buchse (keine V.24-Option).
- Terminal-Software **V4.03.40.01** (Wartungscode 1, abgelesen 2026-09-30).
- Menüsprache Deutsch. Zuordnung (vermutet): Features = Merkmale, Toggle List = Optionen, Set Phone = Einstellungen.
- Merkmale → Optionen enthält „TAPI: Sprache über Zusatzgerät“ und „TAPI: Sprache über Telefon“.
  Stand: **Sprache über Telefon = Ein** (seit 2026-09-30 16:28, damit ist die PC-Schnittstelle aktiv),
  Sprache über Zusatzgerät = Aus.

## PC-Schnittstelle (DB9-Buchse am Telefon)
| Pin | Funktion | Ruhepegel (gemessen 2026-09-30) |
|---|---|---|
| 2 | TxD Telefon → PC | −5 V (am Telefon, Kabel ab) |
| 3 | RxD Telefon ← PC | 0 V am Telefon ohne Kabel; −5 V vom Adapter am Kabelende |
| 5 | GND | – |

Kabel: FTDI-Adapter (Stecker) → 1:1-Verlängerung → Telefon (Buchse). Loopback am Kabelende und Pegelmessung
bestätigen: Kabel 1:1, nicht gekreuzt. Rate/Format: **1200 Baud**, laut Treiber **8O1 + Xon/Xoff** (siehe `protocol.md`).

## Audio-Schnittstelle (RJ11 Unterseite)
| Pin | Funktion | Messwert |
|---|---|---|
| 1 | X_OUT | Gegenseite: Sprache −31 … −43 dBFS RMS, Spitzen −13 dBFS an der UCA222 (Eingang ohne Verstärkung) |
| 2 | X_IN | braucht „X-Eingang statt Mikrofon“; dann passt UCA222-Wiedergabe mit PCM −6 dB (Sprache bis −1 dBFS war leicht übersteuert) |
| 3 | GNDA | – |
Angeschlossen 2026-10-01 (Nutzer): 2 × Übertrager 600:600, C1/C2 1 µF, **ohne** Teiler R1/R2, Cinch `INPUT L`/`OUTPUT L`.
Pinlage wie in [`audio_verkabelung.html`](audio_verkabelung.html) (Pin 1 links) funktioniert in beiden Richtungen.
Messungen mit `tools/audio_test.sh` (Aufnahmen `logs/audio_*.wav`, nur lokal):
- Ruhe: −80 dBFS, kein Brummen; rechter (unbenutzter) Kanal −87 dBFS.
- **Kein Echo:** Testton auf X_IN erscheint auf X_OUT mit < −91 dBFS (Echodämpfung ≈ 75 dB) → X_OUT führt nur die
  Gegenseite, AEC unnötig.
- **X_IN ohne Merkmal 4f sehr leise** (1 kHz bei −16 dBFS kaum hörbar). Mit „X-Eingang statt Mikrofon“ (Merkmal `4f`,
  per FN-Taste oder Auftrag `01 03 26 00 4f`) passt der Pegel; der Daemon schaltet es bei PC-Gesprächen ein.
- PCM-Regler der UCA222 dauerhaft −6 dB (`alsactl store`). Der Drehregler der UCA222 wirkt nur auf den Kopfhörer.
- Vorzeitige Auslösung vom Pi gewählter Gespräche: kein Audioproblem, sondern der 30-s-Watchdog der D340
  (`docs/protocol.md`, Abschnitt 6).

## Messungen
| Datum | Messpunkt | Wert | Deutung |
|---|---|---|---|
| 2026-09-30 | Kabelende telefonseitig (Telefon ab), Pin 2–5 | 0 V | nur Empfänger des Adapters |
| 2026-09-30 | Kabelende, Pin 3–5 | −5 V | Sender des Adapters in Ruhe → Kabel 1:1 |
| 2026-09-30 | Telefonbuchse (Kabel ab), Pin 2–5 | −5 V | Sender des Telefons aktiv |
| 2026-09-30 | Telefonbuchse (Kabel ab), Pin 3–5 | 0 V | Eingang des Telefons |
| offen | Pin 3–5 bei angestecktem Telefon (Last) | – | nicht mehr nötig (Telefon reagiert) |

## Aus den Handbüchern
Quellen: Customer Engineer Manual https://www.manualslib.com/manual/846588/Philips-Ergoline-D330.html (CEM),
User Manual D340 https://www.manualslib.com/manual/715348/Sopho-Ergoline-D340.html (UM),
User Guide D325/D330 `ref/ergoline_tsp/guide_ergoline_d325_d330_english.pdf`. Seiten = PDF-Seiten.

**PC-Schnittstelle**
- Standard bei D330/D340, 1:1-Kabel, TAPI-Treiber auf Diskette (CEM S. 59). Keine Freischaltung beschrieben.
- Keine Baudrate dokumentiert oder einstellbar. Einzige Angabe: Wartungscode 63 „sends a signal from the PC
  interface at 1200 baud“ (CEM S. 72).
- Baudrate, Format, Flusssteuerung, AT-Befehle, S-Register gibt es nur für die **V.24-Option** (CEM S. 51–58;
  Einstellung per Download aus der Anlage, S. 32). Für uns nicht relevant.

**Menü und Merkmale**
- Menübaum: `docs/img/d340_menuebaum.png` (CEM S. 66). `*` = Special Mode (Passwort 2468), `**` = Service Mode (12687).
- Toggle List: „TAPI: speech via accessory“ = Sprachweg auf die Audio-Schnittstelle; „TAPI: speech via phone“ =
  Freisprechen/Hörer/Headset am Telefon (UM S. 45, Glossar S. 97/98). Einträge erscheinen nur, wenn die Anlage
  TAPI für die Nebenstelle unterstützt.
- „X-input instead of mic.“ nur über programmierte Funktionstaste (UM S. 98).
- Voice out „Headset“ oder „Handset without hook“ schaltet den Gabelumschalter ab; dann ist eine Taste
  „On/off hook key for voice“ nötig (UM S. 54).
- ASCII-Tastatur: Infrarot, Kanal 1–3 (CEM S. 62/63). Nichts mit der DB9 zu tun.
- Stromversorgung: leitungsgespeist; Netzteil (8 V~) nur für V.24-Option oder DSS-Module (CEM S. 10, 18, 19).
- **Service-Menü nicht anfassen** (`set TEI`, `reset data`, `download request`, `clean`).

**Wartungsmodus** (CEM S. 69–72)
- Aufruf: Features → SetPhone → SetMode → 12687, dann im Ruhezustand Shift, Hold, nach rechts scrollen, MAINTAIN.
  Testcode + OK, Ende mit CANCEL. Anrufe bleiben annehmbar.
- 1–6 Softwareversionen, 11–14 Display/Tasten/LED (13 ist Umschalter), 61 „Y signal 0 on PC interface“,
  **63 Signal an der PC-Schnittstelle mit 1200 Baud**, 64 X-Interface gespiegelt, 67 V.24.
- Nach Schnittstellentests Hardware-Reset empfohlen (Leitungskabel ziehen).
- **Nie verwenden:** Codes 31–34 (EEPROM löschen) und Tasten `*`, `3`, `5` beim Einstecken des Leitungskabels.

## Gateway
- Konsole: Laptop (KDE neon), Zugriff per `ssh sopho-gw`, Schlüssel `~/.ssh/id_ed25519_sopho-gw`.
- Pi: Raspberry Pi 4, Raspberry Pi OS Lite 64 bit (Debian 13 Trixie), Hostname `sopho-gw`, Nutzer `pi`.
  In Betrieb seit 2026-10-01. Netz: DHCP an eth0 in einem anderen Netz als der Laptop, erreichbar über VPN;
  `.local` geht dort nicht, die IP steht deshalb nur in `~/.ssh/config` des Laptops (nicht im öffentlichen Repo).
  - Image 2026-09-15-raspios-trixie-arm64-lite, per `dd` geschrieben; Erststart per cloud-init
    (`user-data`/`network-config` auf bootfs): Hostname, Nutzer `pi` nur SSH-Schlüssel + NOPASSWD-sudo,
    Europe/Berlin, de, DHCP eth0, avahi, kein WLAN.
  - Der erste Pi 4 (Bootloader 2023-01-11) brach mit `FAT read failed` / `Block device timeout` ab, obwohl
    Netzteil (5,09 V) und Karte (vollständig gelesen, rootfs bytegleich mit dem Image) in Ordnung waren.
    Ein anderer Pi 4 bootet mit derselben Karte; Ursache vermutlich SD-Slot des ersten Geräts.
  - Grundeinrichtung: `ssh sopho-gw 'bash -s' < tools/pi_bootstrap.sh` (2026-10-01 ausgeführt: Pakete, Gruppen
    `dialout`/`audio`, NTP synchron). Repo: `~/Sopho2SIP` (Klon von GitHub, Tests laufen mit Python 3.13).
  - Dienst `sopho2sipd` (`gateway/betrieb/sopho2sipd.service`), seit 2026-10-01 aktiv und nach Neustart geprüft.
    Aktualisieren: `ssh sopho-gw 'cd ~/Sopho2SIP && git pull && sudo systemctl restart sopho2sipd'`.
    Ereignisse: `journalctl -u sopho2sipd -f`; Anrufe: `~/.local/share/sopho2sip/anrufe.jsonl`.
- USB-RS232: FTDI FT232R, `/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A97WEQGD-if00-port0` (am Pi).
  Auch als Logikanalysator nutzbar (`tools/bitbang_scope.py`, synchroner Bitbang, Zugriff über Gruppe `plugdev`).
- UCA222: ALSA-Karte `hw:?` (noch nicht angeschlossen).

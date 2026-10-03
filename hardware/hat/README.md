# Sopho2SIP-HAT (Entwurf 0.2)

HAT für den Raspberry Pi 4, der die Verbindung zur ErgoLine D340 auf eine Platine bringt: **isolierte RS-232** zur
PC-Schnittstelle (statt FTDI-Adapter) und **Audio-Codec mit Übertragern** zur Audio-Buchse (statt UCA222).

| Datei | Inhalt |
|---|---|
| `erzeuge_schaltplan.py` | erzeugt den Schaltplan aus den KiCad-Standardbibliotheken: `SOLL` (Verbindungen) und je Block eine Zeichenfunktion (`pi_leiste`, `hat_eeprom`, `codec`, `sprechweg`, `rs232`, `bedienung`); Generator-Grundlage `hardware/kicadgen.py` |
| `sopho2sip-hat.kicad_sch/.kicad_pro` | KiCad-10-Projekt (erzeugt) |
| `sopho2sip-hat.pdf` | Schaltplan zum Ansehen |
| `netzliste.txt` | Soll-Netzliste (Netz → Pins) aus `SOLL` |
| `stueckliste.csv` | Stückliste (KiCad-Export) |

Neu erzeugen und prüfen:
```
hardware/hat/erzeuge_schaltplan.py --pruefen     # ERC + Abgleich der KiCad-Netzliste mit SOLL (Stand: 0 / 0)
kicad-cli sch export pdf -o hardware/hat/sopho2sip-hat.pdf hardware/hat/sopho2sip-hat.kicad_sch
```
Der Plan ist gezeichnet wie von Hand: Funktionsblöcke mit Rahmen, Signalfluss von links nach rechts, Leitungen
innerhalb der Blöcke, Abblockkondensatoren an den Versorgungsschienen, Labels nur zwischen den Blöcken, galvanische
Trennung als Strichpunktlinie. Die Prüfung vergleicht die Pin-Gruppen der KiCad-Netzliste mit `SOLL`; so kann die
Zeichnung umgestaltet werden, ohne unbemerkt Verbindungen zu ändern. Änderungen am besten im Skript; wer in KiCad
weiterzeichnet, verlässt den Generator (dann ERC und Netzliste dort prüfen).

Versorgungsnetze: `GND`, `+3V3`, `+5V` (Pi), `+3.3VA` (Codec analog), `GNDA` (Telefonseite Audio),
`GND_ISO`, `+3V3_ISO` (isolierte RS-232-Seite) – jeweils als Power-Symbol mit sichtbarem Netznamen.

## Blöcke und Begründungen

| Block | Bauteile | Warum |
|---|---|---|
| Pi-Anschluss | J1 Buchsenleiste 2×20 | HAT-Standard |
| Seriell | **UART3** an GPIO4 (TXD3) / GPIO5 (RXD3) | PL011 – der Mini-UART (GPIO14/15) kann **keine Parität**, die D340 braucht **1200 Bd 8O1**; GPIO14/15 bleiben für Bluetooth, GPIO0/1 für das HAT-EEPROM |
| Trennung | U3 **ADuM5211** | Digitaltrenner (je ein Kanal hin/zurück) **mit eingebauter isolierter Versorgung** (VSEL = GND_ISO → 3,3 V) – ein Chip statt Trenner + DC-DC |
| RS-232 | U5 **MAX3232** (isolierte Seite), J3 **DE9-Stecker** | Pegel ±5 V wie gemessen; Stecker wie am PC (DTE): Pin 2 RxD, Pin 3 TxD, Pin 5 GND → vorhandenes 1:1-Kabel |
| Audio | U2 **WM8731SEDS** (SSOP-28, handlötbar), Y1 12,288 MHz | Linux-Treiber, Overlay `rpi-proto` (genau dieser Codec); 8 kHz direkt; ADC-Hochpass macht `dcsperre` überflüssig |
| Sprechweg | T1/T2 600:600, C21/C24 1 µF, J2 **RJ12** | wie die erprobte Verkabelung (`docs/audio_verkabelung.html`): beide Richtungen galvanisch getrennt; **LHPOUT** (Kopfhörerverstärker) treibt T2 – LOUT ist nur für ≥ 10 kΩ |
| Teiler-Option | R4 = 0 Ω, R5 unbestückt | im Test war kein Teiler nötig (Pegel per Software); Option bleibt |
| Analogversorgung | U4 **AP2112K-3.3** aus 5 V | eigene, ruhige 3,3 V für AVDD/HPVDD |
| HAT-ID | U1 **24LC32**, R1/R2 3,9 kΩ, R3 + JP1 | HAT-Spezifikation: EEPROM an ID_SD/ID_SC, Adresse 0x50, WP hoch (JP1 schließen zum Schreiben) |
| Bedienung | D1/D2 an GPIO23/24, SW1 an GPIO25 | Telefon-Status / Gespräch / Annehmen-Auflegen (interner Pull-up) |

Galvanische Verhältnisse: Telefonseite (TEL_GNDA, ISO_GND) ist vom Pi (GND) **vollständig getrennt** – Audio über die
Übertrager, Seriell über den ADuM5211. Im bisherigen Aufbau war die serielle Masse die einzige leitende Verbindung.

## Konfiguration auf dem Pi (`/boot/firmware/config.txt`)
```
dtparam=i2s=on
dtoverlay=rpi-proto        # WM8731 (I²C 0x1A), Codec erzeugt die Takte aus 12,288 MHz
dtoverlay=uart3            # GPIO4/5 → /dev/ttyAMA3 (Name nach dem Booten prüfen)
```
Danach: Daemon mit `--port /dev/ttyAMA3`, baresip `audio_player/audio_source alsa,plughw:<Karte>,0`. Mit
HAT-EEPROM kann der Pi die Overlays auch selbst laden (EEPROM mit `eepromutils` beschreiben).

## Vor der Fertigung prüfen (offen)
- **ADuM5211:** VDD1 = 3,3 V (Logikpegel zum Pi) bei VDDP = 5 V zulässig? Polarität von VSEL; Ausgangsleistung für
  MAX3232 + ADuM-Seite 2 (einige mA). Datenblatt.
- **WM8731:** Quarzbeschaltung (Lastkapazität des gewählten Quarzes → C10/C11), unbenutzte Eingänge (RLINEIN, MICIN)
  laut Datenblatt beschalten oder offen lassen.
- **Übertrager:** Bauteil auswählen (600:600, Platinenbauform, z. B. kleine SMD-Telefonübertrager) und Footprint
  zuordnen – im Schaltplan noch leer.
- **RJ12-Kabel:** Viele flache Telefonkabel sind gedreht (1↔6). Die Pinbelegung von J2 setzt ein 1:1 belegtes 6P6C
  voraus – mit dem Durchgangsprüfer gegen die D340-Buchse prüfen, sonst Belegung auf der Platine spiegeln.
- **Mechanik:** HAT-Maß 65 × 56,5 mm, Befestigungslöcher 58 × 49 mm; ein liegender DE9 ist hoch – evtl. auf die
  Kante setzen oder Pfostenstecker + Kabel.
- **ESD:** MAX3232**E** (±15 kV) wählen; TVS-Dioden an X_IN/X_OUT erwägen.
- Trägerplatine für das Compute Module 4 mit denselben Blöcken: `hardware/cm4/`.

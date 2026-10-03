# Sopho2SIP-Träger für Compute Module 4 (Entwurf 0.2)

Trägerplatine für das Raspberry Pi **Compute Module 4** mit derselben D340-Anbindung wie der HAT
(`hardware/hat/`): isolierte RS-232 zur PC-Schnittstelle, Audio-Codec mit Übertragern zur Audio-Buchse.

- **Speicher:** CM4 mit **eMMC** *oder* **CM4 Lite** mit **µSD-Karte**. Der Sockel ist immer bestückt. Beim
  eMMC-Modul sind die SD-Pins im Modul offen, der Sockel bleibt dann ungenutzt.
- **Netz:** **WLAN** über das CM4 mit Funk (Antenne auf dem Modul oder U.FL) *oder/und* **Ethernet 10/100**
  über eine MagJack-Buchse. Beides ist bestückbar; der Betrieb wird per Software gewählt.

| Datei | Inhalt |
|---|---|
| `erzeuge_schaltplan.py` | erzeugt das hierarchische Projekt: `SOLL_*` (Verbindungen je Blatt), `blatt_*()` (Zeichnung), `main()` (Wurzelblatt) |
| `sopho2sip-cm4.kicad_sch` | Wurzelblatt: Funktionsblöcke als hierarchische Blätter, über Blattpins verdrahtet. Blätter mit nur einem Block ohne Rahmen, Inhalt zentriert |
| `cm4.kicad_sch`, `versorgung.kicad_sch`, `sd.kicad_sch`, `ethernet.kicad_sch`, `codec.kicad_sch`, `sprechweg.kicad_sch`, `rs232.kicad_sch`, `bedienung.kicad_sch` | Kindblätter (erzeugt) |
| `sopho2sip.kicad_sym`, `sym-lib-table` | Projektbibliothek mit den beiden CM4-Steckern (erzeugt) |
| `sopho2sip-cm4.pdf` | alle 9 Blätter zum Ansehen |
| `netzliste.txt` | Soll-Netzliste (`Blatt/Netz` = lokal, sonst global oder über Blattpins) |
| `stueckliste.csv` | Stückliste (KiCad-Export) |

Neu erzeugen und prüfen:
```
hardware/cm4/erzeuge_schaltplan.py --pruefen     # ERC + Abgleich der Netzliste mit SOLL (Stand: 0 / 0)
kicad-cli sch export pdf -o hardware/cm4/sopho2sip-cm4.pdf hardware/cm4/sopho2sip-cm4.kicad_sch
```
Gemeinsamer Generator: `hardware/kicadgen.py` (Symbole, Platzierung, Leitungen, hierarchische Blätter, Prüfung).
Die Blöcke Audio-Codec, Sprechweg, RS-232 und Bedienung stammen aus `hardware/hat/erzeuge_schaltplan.py` und werden
nur verschoben. Eine Änderung dort wirkt in beiden Projekten. Danach beide Generatoren mit `--pruefen` laufen lassen.

## Blätter

| Blatt | Bauteile | Warum |
|---|---|---|
| CM4 | J11/J12 **Hirose DF40C-100DS** (2 × 100 Pins), C40/C41 | Pinbelegung aus dem CM4-Datenblatt (Pins 1–200); **GPIO_VREF = 3,3 V** (Pegel der GPIO-Bank 0) |
| | JP10 **nRPIBOOT** | gesteckt: das CM4 startet als USB-Gerät → `rpiboot` über USB-C, eMMC erscheint als Laufwerk |
| | D10 (ACT), Q10 **BSS84** + D11 (PWR) | Aktivitäts-Pin senkt bis 20 mA; PI_LED_nPWR muss laut Datenblatt gepuffert werden |
| Versorgung | J10 **USB-C** (16 P), F1 Polyfuse 2 A, D12 **SMAJ5.0CA**, R10/R11 5,1 kΩ, U10 **USBLC6-2SC6** | eine Buchse für 5 V und USB 2.0 (rpiboot); Rd = Senke, TVS an 5 V, ESD auf D+/D− |
| µSD | J13 Micro-SD, U11 **AP22804AW5**, R14 12 kΩ | Lastschalter für die Kartenspannung wie Datenblatt (dort RT9742), EN über SD_PWR_ON; R14 hält ihn ohne Ansteuerung an |
| Ethernet | J14 **HR911105A** (MagJack mit Übertrager), U12 **TPD4EUSB30**, C45, R15/R16 | Beschaltung wie Datenblatt: Mittelanzapfungen über 100 nF an GND, ESD an den Paaren, LEDs low-aktiv mit 470 Ω |
| Audio-Codec, Sprechweg, RS-232, Bedienung | wie HAT | GPIO-Belegung unverändert: UART3 (GPIO4/5), I²S (GPIO18–21), I²C (GPIO2/3), LEDs/Taste (GPIO23–25) |

Kein HAT-EEPROM: ID_SD/ID_SC bleiben offen, die Overlays stehen fest in `config.txt`.

## Konfiguration (`/boot/firmware/config.txt`)
```
dtparam=i2s=on
dtoverlay=rpi-proto        # WM8731
dtoverlay=uart3            # GPIO4/5 → /dev/ttyAMA3 (Name nach dem Booten prüfen)
dtparam=ant2               # nur bei externer WLAN-Antenne (U.FL)
```
eMMC beschreiben: JP10 stecken, USB-C mit dem Rechner verbinden, `rpiboot` ausführen, Image schreiben, JP10 ziehen.

## Vor der Fertigung prüfen (offen)
- **Ethernet:** Das CM4 hat einen Gigabit-PHY. Die 2-Paar-Buchse trägt nur 10/100. Prüfen, ob der PHY bei nur zwei
  Paaren sicher auf 100 Mbit herunterschaltet, sonst Geschwindigkeit per `ethtool` festlegen oder 4-Paar-MagJack
  verwenden (Paare 2/3 sind am CM4-Stecker vorhanden).
- **3,3 V vom CM4:** höchstens 600 mA. Verbraucher: Codec-Digitalteil, Logikseite des ADuM5211, µSD-Karte (bis
  ~100 mA), LEDs. Die Summe aus den Datenblättern bilden.
- **AP22804 statt RT9742:** Pinbelegung, EN-Polarität und Strombegrenzung gegen das Datenblatt prüfen.
- **USB_OTG_ID** (Pin 101) ist offen. Normalbetrieb als Host oder Gerät mit `dtoverlay=dwc2,dr_mode=…` festlegen.
  Das CM4-Datenblatt zur Beschaltung prüfen.
- **DF40-Stecker:** Bauhöhe (1,5 mm oder 3,0 mm) festlegen. Sie bestimmt den Platz unter dem Modul.
- **Befestigung:** H1–H4 für das Gehäuse; das CM4 braucht zusätzlich 4 Abstandsbolzen M2,5 an seinen Bohrungen.
- **WLAN-Antenne:** In einem Metallgehäuse eine externe Antenne (U.FL) und `dtparam=ant2` verwenden.
- Die Prüfpunkte des HAT gelten weiter (ADuM5211, WM8731-Quarz, Übertrager, RJ12-Kabel, MAX3232E): siehe
  `hardware/hat/README.md`.

# Sopho2SIP-Träger für Compute Module 4 (Entwurf 0.3)

Trägerplatine für das Raspberry Pi **Compute Module 4** als Gerät zum Einstecken: alle Kabel hinten, kurze Wege zur
D340, vorne µSD, Status-LEDs und drei Taster (Annehmen, Konfiguration, Ein/Aus); Lüfter temperaturgesteuert;
Gehäuse aus dem 3D-Drucker.

- **Speicher:** CM4 mit **eMMC** *oder* **CM4 Lite** mit **µSD-Karte**. Der Sockel ist immer bestückt. Beim
  eMMC-Modul sind die SD-Pins im Modul offen, der Sockel bleibt dann ungenutzt.
- **Netz:** **WLAN** über das CM4 mit Funk (Antenne auf dem Modul, zur linken Platinenkante; oder U.FL)
  *oder/und* **Ethernet 10/100** (RJ45 mit Übertrager). Der Betrieb wird per Software gewählt.
- **D340:** isolierte RS-232 (ADuM5211 + MAX3232, **4P4C-Buchse**) und Sprechweg über zwei Übertrager (RJ12).
  Zur D340 führt ein Adapterkabel 4P4C → DE9-Stecker (4P4C 1 → 5 GND, 2 → 2 RxD, 3 → 3 TxD).

| Datei | Inhalt |
|---|---|
| `erzeuge_schaltplan.py` | hierarchischer Schaltplan: `SOLL_*` (Verbindungen je Blatt), `blatt_*()` (Zeichnung), `main()` (Wurzelblatt) |
| `erzeuge_layout.py` | Leiterplatte aus der KiCad-Netzliste: Platzierung, Lagen, Flächen, Sperrzonen, Regeln, Routing, DRC, Fertigungsdaten |
| `erzeuge_bestellliste.py` | `stueckliste_digikey.csv` mit Herstellernummern und Digikey-Bestand |
| `sopho2sip-cm4.kicad_sch`, `*.kicad_sch` | Wurzelblatt und Kindblätter (erzeugt) |
| `sopho2sip-cm4.kicad_pcb`, `.kicad_dru` | Leiterplatte und JLCPCB-Regeln (erzeugt) |
| `sopho2sip.kicad_sym`, `sym-lib-table`, `fp-lib-table` | Projektbibliotheken; eigene Footprints in `hardware/bibliothek/` |
| `sopho2sip-cm4.pdf` | alle 9 Schaltplanblätter |
| `netzliste.txt`, `stueckliste.csv` | Soll-Netzliste, KiCad-Stückliste |
| `handlage/`, `.generiert.json` | von Hand nachgebesserte Blätter; Fingerabdrücke der zuletzt erzeugten Zeichnung |

Neu erzeugen und prüfen:
```
hardware/bibliothek/erzeuge_footprints.py         # eigene Footprints (Übertrager, RJ12, DF40 mit Pins 101–200)
hardware/cm4/erzeuge_schaltplan.py --pruefen      # ERC + Abgleich der Netzliste mit SOLL
hardware/cm4/erzeuge_layout.py --routen --pruefen # Platine, FreeRouting, DRC
hardware/cm4/erzeuge_layout.py --nur-fertigung    # Gerber/Bohrdaten/Bestückung/STEP/Bild nach fertigung/
hardware/cm4/erzeuge_bestellliste.py
```
Die UUIDs sind reproduzierbar: Schaltplan und Platine bleiben beim Neuerzeugen verknüpft („Platine aus Schaltplan
aktualisieren“ in KiCad funktioniert weiter).

**Zeichnung von Hand nachbessern:** Blätter in KiCad schöner setzen (Bauteile, Beschriftungen, Leitungen, Labels
verschieben) und speichern, dann den Generator laufen lassen. Er erkennt die geänderten Blätter am Fingerabdruck der
Zeichnung, prüft die Netzliste gegen SOLL und übernimmt sie nach `handlage/`. Ab dann kommt die Zeichnung dieser
Blätter von dort; Werte, Footprints und Symbole weiter aus SOLL (in KiCad geänderte Werte werden mit Hinweis
zurückgesetzt). Ändert die Handarbeit eine Verbindung, schreibt der Generator nichts und nennt die Abweichung.
```
hardware/cm4/erzeuge_schaltplan.py --pruefen                          # Änderungen im Projektordner übernehmen
hardware/cm4/erzeuge_schaltplan.py --handlage-aus ~/kopie --pruefen    # … aus einer Kopie des Projekts
hardware/cm4/erzeuge_schaltplan.py --handlage-verwerfen Bedienung      # Blatt wieder vom Generator zeichnen lassen
```
Kommt in SOLL ein Bauteil auf einem Blatt mit Handlage hinzu (oder fällt weg), bricht der Generator ab: das Blatt in
KiCad nachziehen oder die Handlage verwerfen.

**Texte** (Hinweiskästen, Texte, Blocktitel) gehören dem Generator. In KiCad geänderte Texte schreibt der Generator
an die Stelle im Quelltext zurück, an der sie entstehen (`p.notiz(…)`, `p.text(…)`, `rahmen_(…)`); ein neuer Absatz
im Kasten wird ein weiteres Argument von `notiz`. Ersetzt wird nur, wenn dort feste Literale genau den bisherigen
Text ergeben; sonst bleibt der Text als Handtext in `.generiert.json` und wird gemeldet. Ändert sich nur Text, nicht
die Lage, entsteht keine Handlage. In KiCad neu angelegte oder gelöschte Texte meldet der Generator nur.
Hinweise stehen in Textkästen (`notiz`): KiCad bricht innerhalb der Kastenbreite um, die Höhe schätzt der Generator.

## Blätter und Bauteile

| Blatt | Bauteile | Warum |
|---|---|---|
| CM4 | J11/J12 **Hirose DF40C-100DS-0.4V(51)** (1,5 mm Stapelhöhe), C40/C41, H5–H8 | Pinbelegung und Lage aus Datenblatt und CM4IO-Referenzlayout; **GPIO_VREF = 3,3 V** |
| | JP10 **nRPIBOOT** | gesteckt: das CM4 startet als USB-Gerät → `rpiboot` über USB-C, eMMC erscheint als Laufwerk |
| | D10 (ACT), Q10 **BSS84** + D11 (PWR) | Aktivitäts-Pin senkt bis 20 mA; PI_LED_nPWR muss laut Datenblatt gepuffert werden |
| Versorgung | J10 **USB-C** GCT USB4105, F1 Polyfuse 2 A, D12 **SMAJ5.0CA**, R10/R11 5,1 kΩ, U10 **USBLC6-2SC6** | eine Buchse für 5 V und USB 2.0 (rpiboot) |
| µSD | J13 Hirose DM3AT, U11 **AP22804AW5**, R14 12 kΩ | Lastschalter für die Kartenspannung wie Datenblatt (dort RT9742) |
| Ethernet | J14 **Würth 7499010211A** (RJ45 mit Übertrager, LEDs), U12 **TPD4E05U06**, C45, R15/R16 | Mittelanzapfungen über 100 nF an GND, ESD an den Paaren, LEDs low-aktiv |
| Audio-Codec | U2 **TI TLV320AIC3204** (VQFN-32), U6 Oszillator 12 MHz, U4 AP2112K-3.3 | **WM8731 ist abgekündigt**, SGTL5000/WM8960 ebenso bzw. nicht lieferbar. Der AIC3204 hat einen Linux-Treiber (`tlv320aic32x4`); Vorlage für das Overlay ist `audiosense-pi` (I²C 0x18, MCLK 12 MHz, Reset an GPIO26). **I²C an GPIO0/1 (I2C0)**, weil GPIO3 der Ein/Aus-Taster ist. LOL treibt den 600-Ω-Übertrager (Last ≥ 600 Ω laut Datenblatt) |
| Sprechweg | T1/T2 **Bourns SM-LP-5001** (600:600, 2 kV), J2 **Würth 615006138421** (RJ12/6P6C) | Amphenol 54601 ist abgekündigt |
| RS-232 | U3 **ADuM5211**, U5 **MAX3232E**, J3 **Würth 615004143821** (4P4C liegend) | statt DE9 (31 mm Kante, 13 mm hoch): verriegelnd, klein, nicht mit RJ12/RJ45 verwechselbar |
| CM4 selbst | M1 Platzhalter | steht in der Stückliste, wird gesteckt (nicht in den Bestückungsdaten); 3D-Modell 1,5 mm über J11/J12 |
| Bedienung | SW1 Annehmen/Auflegen (GPIO25), **SW2 Konfiguration (GPIO27)**, **SW3 Ein/Aus (GPIO3)**, D1–D3 (GPIO23/24/22) | D3 + SW2 für Einstellungen am Gerät; alle LEDs vorne für Lichtleiter |
| | SW3, R9 (unbestückt) | **Ein/Aus mit einem Taster:** im Betrieb fährt `gpio-shutdown` sauber herunter; im Halt weckt der Bootloader das CM4 über GPIO3 (`WAKE_ON_GPIO=1`, Werkseinstellung). GLOBAL_EN bleibt unbenutzt (Datenblatt: nur nach dem Herunterfahren auf Low ziehen) |
| Lüfter | Q11 **AO3400A**, D13 **MBR140SFT1G**, R17/R18, C46, J15 **JST PH 2-polig** | 5-V-Lüfter, Low-Side-Schalter an GPIO12 (PWM-fähig); die SoC-Temperatur des CM4 steuert über `gpio-fan` |

Die vollständige Bestellliste mit Digikey-Nummern und dem am 2026-10-03 geprüften Bestand steht in
`stueckliste_digikey.csv`. Keramikkondensatoren und Widerstände sind Standardteile; deren Bestand schwankt, der
Digikey-BOM-Manager schlägt gleichwertige Teile vor.

## Leiterplatte

- **Maße:** 110 × 85 mm, 4 Lagen, 1,6 mm, JLCPCB-Aufbau **JLC04161H-7628** (bei der Bestellung „Impedance Control“
  mit diesem Aufbau wählen).
- **Lagen:** F.Cu Signale · **In1 GND** · **In2 +3V3** · B.Cu Signale. Außenlagen nach dem Routing mit Masse gefüllt.
- **Impedanz** (berechnet, mit dem JLC-Rechner gegenprüfen): Ethernet 100 Ω differenziell = 0,20 mm / 0,17 mm,
  USB 90 Ω = 0,22 mm / 0,13 mm (Mikrostreifen über 0,21 mm Prepreg).
- **Anordnung:** hinten USB-C, RJ45, DE9, RJ12; CM4 links mit der Antenne zur linken Kante (kupferfreie Zone
  9,5 × 15 mm auf allen Lagen, Datenblatt: mind. 8 × 15 mm); vorne µSD, LEDs, Taster.
- **Isolation:** GND_ISO (RS-232) und GNDA (Sprechweg) sind eigene Bereiche mit eigenen Flächen auf allen Lagen.
  1 mm breite kupferfreie Trennstreifen auf allen Lagen; nur der ADuM5211 und die Übertrager überbrücken sie.
- **Regeln:** JLCPCB-Standard (Bahn/Abstand ≥ 0,09 mm, Bohrung ≥ 0,15 mm, Kupfer zur Kante ≥ 0,3 mm), in
  `sopho2sip-cm4.kicad_dru`; Standardbahn 0,15 mm, Durchkontaktierung 0,3/0,55 mm.
- **Routing:** Der Generator setzt zuerst selbst eine Durchkontaktierung an jedes SMD-Pad der Ebenennetze (GND,
  +3V3, GND_ISO, +3V3_ISO, GNDA; 144 Stück, mit Kollisionsprüfung), dann routet **FreeRouting 1.9.0** die übrigen
  Netze (Specctra DSN/SES, 30 Durchgänge, rund eine Stunde). FreeRouting 1.9 braucht eine Oberfläche und läuft
  unsichtbar über `xvfb-run` (Paket `xvfb`); das Werkzeug wird nach `hardware/.werkzeug/` geladen und per SHA-256
  geprüft. FreeRouting 2.x wurde verworfen: Telemetrie ab Werk an, hielt die Durchgangszahl nicht ein.
- **Stand:** vollständig geroutet, **DRC ohne Verstöße**, keine offenen Verbindungen, Schaltplan und Platine stimmen
  überein. Ethernet und USB sind vom Router als Einzelleitungen mit der Paarbreite verlegt, nicht als gekoppelte
  Differenzpaare (für 10/100 und USB 2.0 auf diesen Längen unkritisch; vor der Bestellung ansehen).
- **3D-Modelle:** CM4 offiziell von Raspberry Pi, die übrigen Herstellermodelle (Würth, Hirose, Bourns, ECS) liegen
  nur lokal in `hardware/bibliothek/3d/` (nicht weitergebbar, Quellen und Prüfsummen in `QUELLEN.md`).
  `hardware/bibliothek/richte_3d_aus.py` richtet sie auf die Footprints aus; die Steckerlagen sind im Rendering von
  unten geprüft (alle Pins, Zapfen und Schirmlaschen mittig in ihren Bohrungen).
- `--nur-nacharbeit` erneuert Beschriftung, Bestückungsattribute und Flächen ohne neues Routing. Konstruiert wird
  bei (100, 100); zum Schluss rückt die Platine auf dem A4-Blatt nach (93, 45), frei vom Schriftfeld. Alle
  Bauteiltexte stehen waagerecht.

## Konfiguration (`/boot/firmware/config.txt`)
```
dtparam=i2s=on
dtparam=i2c_vc=on          # I2C0 an GPIO0/1 für den Codec
dtoverlay=sopho2sip-codec  # noch zu schreiben (nach audiosense-pi, aber i2c0): TLV320AIC3204, 0x18, 12 MHz, Reset GPIO26
dtoverlay=gpio-shutdown,gpio_pin=3   # Ein/Aus-Taster: Druck = sauber herunterfahren
dtoverlay=gpio-fan,gpiopin=12,temp=60000   # Lüfter ab 60 °C SoC-Temperatur
dtoverlay=uart3            # GPIO4/5 → /dev/ttyAMA3 (Name nach dem Booten prüfen)
dtparam=ant2               # nur bei externer WLAN-Antenne (U.FL)
```
Bootloader-EEPROM: `WAKE_ON_GPIO=1` (Werkseinstellung) und `POWER_OFF_ON_HALT=0` lassen, sonst weckt der Taster
nicht. eMMC beschreiben: JP10 stecken, USB-C mit dem Rechner verbinden, `rpiboot` ausführen, Image schreiben, JP10 ziehen.

## Vor der Fertigung prüfen (offen)
- **Codec:** Overlay für I2C0 schreiben; Mixer-Einstellungen (IN1_L → ADC, DAC → LOL) mit `amixer` festlegen.
- **Ein/Aus:** Wecken über GPIO3 am CM4 erproben (bei Bedarf R9 als Pull-up bestücken).
- **Lüfter:** Lüftertyp festlegen (5 V, ≤ 200 mA, 2-polig mit JST-PH-Stecker oder umcrimpen) und im Deckel über dem
  CM4 vorsehen.
- **Ethernet:** Das CM4 hat einen Gigabit-PHY. Die 2-Paar-Buchse trägt nur 10/100. Prüfen, ob der PHY bei nur zwei
  Paaren sicher auf 100 Mbit herunterschaltet, sonst per `ethtool` festlegen.
- **3,3 V vom CM4:** höchstens 600 mA. Verbraucher: Codec (Digital, Oszillator), ADuM5211 (Logikseite), µSD-Karte
  (bis ~100 mA), LEDs. Summe aus den Datenblättern bilden.
- **AP22804 statt RT9742:** Pinbelegung, EN-Polarität und Strombegrenzung gegen das Datenblatt prüfen.
- **USB_OTG_ID** (Pin 101) ist offen. Normalbetrieb mit `dtoverlay=dwc2,dr_mode=…` festlegen.
- **RJ12-Footprint:** aus der Würth-Zeichnung abgeleitet; Lage der Steckseite zur Platinenkante am Muster prüfen.
- **Mechanik:** Gehäuse für den FDM-Druck in `hardware/gehaeuse/` (Lichtleiter über D1–D3, D10, D11; Biegezungen mit
  Stößel über SW1–SW3; Lüfter 30 mm). Erstdruck steht aus.
- Die Prüfpunkte des HAT gelten weiter (ADuM5211, Übertrager, RJ12-Kabel, MAX3232E): `hardware/hat/README.md`.

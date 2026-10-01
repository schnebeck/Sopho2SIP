# Protokoll der PC-Schnittstelle (ErgoLine D340, 9-polige Buchse)

Stand 2026-09-30. Nur der aktuelle Wissensstand. Irrwege: [`sackgassen.md`](sackgassen.md),
Mitschnitte: [`../logs/INDEX.md`](../logs/INDEX.md). Treiberadressen beziehen sich auf `ref/ergoline_tsp/Ergoline.tsp`
(Imagebase 0x10000000).

Kennzeichnung: **bestätigt** = am Gerät gemessen/mitgeschnitten, **Treiber** = aus `Ergoline.tsp` abgeleitet,
am Gerät noch nicht geprüft, **vermutet** = Deutung.

## 1. Voraussetzungen am Telefon
| Punkt | Wert | Status |
|---|---|---|
| Gerät | ERGOLINE 340-2/LG INT, Terminal-Software **V4.03.40.01** | bestätigt |
| Freischaltung | Merkmale → Optionen: **„TAPI: Sprache über Telefon“ = Ein** (seit 2026-09-30 16:28). Solange beide TAPI-Schalter aus sind, reagiert die Schnittstelle auf nichts. | bestätigt |
| Sprachweg | „TAPI: Sprache über Zusatzgerät“ legt die Sprache auf die Audio-Buchse (für das Gateway nötig, noch nicht getestet) | vermutet (Handbuch) |

## 2. Physikalische Ebene
| Punkt | Wert | Status |
|---|---|---|
| Stecker | DB9-Buchse, Telefon = DCE, 1:1-Kabel, Pin 2 (Telefon sendet), 3 (Telefon empfängt), 5 (GND) | bestätigt |
| Pegel | Ruhepegel −5 V auf beiden Datenleitungen | bestätigt |
| Rate | **1200 Baud** | bestätigt (Testcode 63, `bitbang_20260930_163321`) |
| Format | **8O1 (ungerade Parität)**; der Treiber schaltet zusätzlich Xon/Xoff ein (Port-Methode 0x100132c2) | bestätigt: Senden/Empfangen mit 8O1 ohne Xon/Xoff (2026-10-01) |
| Servicemodus | 9600 8N1 bzw. 8O1 („ASFD-Modus“, nur für Escape/Versionsabfrage, Abschnitt 7) | Treiber |

## 3. Rahmenformat (beide Richtungen)
`<Klasse> <Länge> <Länge Byte Nutzdaten>` — **bestätigt** (Mitschnitte) und **Treiber** (Rahmen-Assembler 0x1000dbe9:
Ringpuffer 1 KB, Länge als vorzeichenbehaftetes Byte, max. 127; keine Prüfsumme, kein Escaping, kein XOR).

| Klasse | Richtung | Bedeutung (Treibername) |
|---|---|---|
| `01` | PC → Telefon | Auftrag (Treiber) |
| `02` | Telefon → PC | Meldung, `L2_REQ_PHONE` |
| `03` | Telefon → PC | Ablehnung, `L2_REJ_PHONE` |
| `04` | Telefon → PC | Quittung, `L2_ACK_PHONE` |
| `05` | Telefon → PC | Fehler, `L2_ERR_PHONE` (unser `05 00` nach unverstandener Eingabe, ~1,5 s) |

Nutzdaten: Byte 2 = Typ, Byte 3 = `01` (Meldung) bzw. `00` (Auftrag), danach typabhängig.
Quittung: Nur Aufträge des PCs werden quittiert (`04`). Meldungen des Telefons quittiert der PC nicht (Treiber:
keine Sendestelle in Empfang/Parser).

## 4. Beobachtete Meldungen (Log `serial_20260930_163534.log`, 1200 passiv)
| Zeit | Aktion des Nutzers | Nutzdaten (hex) | Bedeutung |
|---|---|---|---|
| 16:35:47.2 | Anruf kommt an | `30 01 98 6c 0d` + `0101700000000` | RINGING, Anrufer (IE `6c`) = Amtsholung `01` + Nummer |
| 16:35:53.1 | Hörer abgenommen | `3b 01 0a` · `31 01` · `3b 01 30` | OFF HOOK · CONNECTED · DTMF ein |
| 16:36:15.3 | aufgelegt | `3a 01 30` · `32 01 98 08 00` · `39 01 98 08 00` · `3a 01 0a` | DTMF aus · DISCONNECTED · RELEASED · ON HOOK |
| 16:37:26.7 | Hörer daneben, ohne Wahl | `36 01` · `3b 01 0a` | DIALTONE · OFF HOOK |
| 16:37:36.9 | (10,2 s später) | `36 01` | DIALTONE (Wiederholung, Grund offen) |
| 16:37:42.5 | aufgelegt | `39 01 98 08 00` · `3a 01 0a` | RELEASED · ON HOOK |
| 16:38:37.8 | abgehoben, Nummer getippt (Meldung erst bei Wahlende) | `36 01` · `3b 01 0a` | DIALTONE · OFF HOOK |
| 16:38:38.1 | | `19 01 98 70 0d` + `0101700000000` | MORE_INFO, gewählte Nummer (IE `70`) inkl. Amtsholung |
| 16:38:43.9 | | `3e 01` | PROCEEDING |
| 16:38:49.5 | Gegenseite nimmt an | `31 01` · `3b 01 30` | CONNECTED · DTMF ein |
| 16:39:11.5 | Gegenseite legt auf | `32 01 98 08 01 8f` · `3a 01 30` | DISCONNECTED, Ursache 0x8f · DTMF aus |
| 16:39:19.9 | Hörer aufgelegt | `39 01 98 08 00` · `3a 01 0a` | RELEASED · ON HOOK |

Im Ruhezustand sendet das Telefon nichts. Abheben/Einzelziffern kamen erst bei Wahlende (Blockwahl).

## 5. Meldungstypen (Treiber, Parser 0x100172b9)
| Typ | Name | | Typ | Name |
|---|---|---|---|---|
| `19` | `L3_MORE_INFO` (Nummer, UUI) | | `38` | `L3_STATUSCAMPONBUSY` |
| `30` | `L3_STATUSRINGING` | | `39` | `L3_STATUSRELEASED` |
| `31` | `L3_STATUSCONNECTED` | | `3a` | `L3_STATUSFACILITYDEACTIVATED` |
| `32` | `L3_STATUSDISCONNECTED` | | `3b` | `L3_STATUSFACILITYACTIVATED` |
| `33` | `L3_STATUSIDLE` | | `3c` | `L3_STATUSFACILITYREJECTED` |
| `34` | `L3_STATUSHOLD` | | `3d` | `L3_STATUSERROR` |
| `35` | `L3_STATUSUNHOLD` | | `3e` | `L3_STATUSPROCEEDING` |
| `36` | `L3_STATUSDIALTONE` | | `3f`/`40` | `L3_STATUSCALLWAITINGACT`/`…DEACT` |
| `37` | `L3_STATUSBUSY` | | `41` | `L3_STATUSUSERTOUSER` |
| | | | `44` | `L3_STATUSNOHOLD` |

Merkmalskennung (Byte 4) bei `3b`/`3a`: `0a` OFF/ON HOOK, `30` DTMF-Töne ein/aus, `01` Umleitung, `16` wartenden
Anruf anzeigen, `17` wartenden Anruf annehmen, `1a` Rückruf (ARB), `1d` Aufschalten, `1f` Konferenz vorbereiten,
weitere über 0x30 (DND, Pickup, Reconnect).
Informationselemente wie Q.931: `6c` Anrufer, `70` Ziel, `08` Ursache (`08 00` = keine), `7e` User-to-User.
Rufnummern vom Telefon: reine ASCII-Ziffern; externe Nummern mit **Amtsholung `01`** davor (Angabe Nutzer,
passt zu beiden Mitschnitten). Im Wahlauftrag des PCs steht laut Treiber das Typ-Oktett `0x81` vor den Ziffern.
`98` (Byte 4 in Nummern-/Auslösemeldungen): Bedeutung offen.

## 6. Aufträge PC → Telefon (Treiber; Anmelden, Keepalive, Annehmen, Auflegen am Gerät bestätigt 2026-10-01)
Der Treiber wartet nach jedem Auftrag bis 5 s auf `04` (`AckEvent`); ohne Quittung gilt der Auftrag als gescheitert.
**Bestätigt:** Quittung ist immer `04 00`, nach 100–150 ms (Logs `test_20261001_*`). Nach „Anmelden“ folgt 50 ms später
die Meldung `02 04 01 01 02 00` (Typ `01`). Der Treiber wertet sie **nicht** aus: einziger Rahmenweg Empfang 0x10014219 →
Parser 0x100172b9 → `default` (0x1001934a, nur Trace) → CompareOldStateNewState `default` (0x10019d4e). Für einen Daemon ignorierbar. Deutung (vermutet, Nutzer 2026-10-01): **READY**, Bereitmeldung nach der Anmeldung. „Annehmen“ lässt das Telefon abheben (Freisprechen bei
„TAPI: Sprache über Telefon“), danach `3b…0a` + `31`. „Auflegen“ beendet das Gespräch: `32` (Ursache leer), `39`, `3a…0a`.
Im Freisprechbetrieb beendet auch die Lautsprecher-Taste am Telefon das Gespräch (Ursache leer).

| Auftrag | Rahmen | Treiberstelle |
|---|---|---|
| Keepalive | `01 02 00 00` | Thread 0x1001a1a7, nach 15 s ohne Empfang |
| Anmelden (Betriebsmodus) | `01 02 01 00` | Init 0x100147b0 |
| Leitung belegen (nur im Ruhezustand, vor der Wahl) | `01 02 11 00` | lineMakeCall → 0x10014b0c |
| **Wählen** | `01 <n+6> 19 00 98 70 <n+1> 81 <n ASCII-Ziffern>` | lineMakeCall 0x10014b0c, lineDial 0x10014eb9 |
| **Annehmen** (klingelnder Anruf) | `01 02 14 00` | lineAnswer → 0x10015d57 |
| **Auflegen** (ein Anruf) | `01 02 13 00` | lineDrop → 0x100168ce |
| Merkmalsauftrag | `01 03 26 00 <Kennung>`: `16`/`17` Anklopfen anzeigen/annehmen, `C3`/`EE` Reconnect (je nach Version), `52`, `1e` | Answer/Drop/Konferenz |
| weitere | `15`, `18`, `1b`, `1c`, `1d`, `21`–`24`, `27`, `25` (UUI) | Hold/Unhold/Transfer/Conference/CompleteCall |

Beispiel „Wählen 123“: `01 09 19 00 98 70 04 81 31 32 33`.
Im Treiber nicht unterstützt (`LINEERR_OPERATIONUNAVAIL`): Redirect, BlindTransfer, Accept.

## 6a. Zustandsautomat des Treibers (Treiber, statisch analysiert 2026-10-01)
Der Treiber führt für das Telefon eine **Anruftabelle** (Telefonobjekt `+0x14d4`, 31 Plätze; der Platzindex ist die
interne Anrufkennung) und je Anruf einen Zustand im **TAPI-Format `LINECALLSTATE_*`** samt Modus.
Die Rahmen tragen **keine Anrufkennung** (Byte „Leitung“ ist immer `01`): Der Treiber ordnet jede Meldung dem Anruf zu,
der sich gerade in einem passenden Zustand befindet (`SUCHE_ZUSTAND` 0x100075a3). Ein Daemon muss das genauso machen.

Ablauf je empfangenem Rahmen (Empfang 0x10014219): Ereignisobjekt anlegen → Parser 0x100172b9 setzt Ereigniscode(s)
→ Behandler 0x1000ab4f (legt bei Wählton-Codes `0f`–`14` bzw. Angebot `3c` einen neuen Anruf an) → Übergang
0x100069eb (alter Zustand × Code → neuer Zustand) → Modus 0x1000b70b → TAPI-Meldung `LINE_CALLSTATE` (0x1000a515).

**Ereigniscodes** (CompareOldStateNewState 0x10019bbb): `02` unbekannt · `0a` Freigabe · `0b`–`0e` besetzt
(Modus STATION/TRUNK/UNKNOWN/UNAVAIL) · `0f`–`14` Wählton (NORMAL/SPECIAL/INTERNAL/EXTERNAL/UNKNOWN/UNAVAIL) ·
`15`–`19` Sonderinfo · `1a`–`25` Auslösung (LINEDISCONNECTMODE NORMAL, UNKNOWN, REJECT, PICKUP, FORWARDED, BUSY,
NOANSWER, …) · `29` Wahl · `2a` Proceeding · `2b` Ringback · `2c` Halten · `2d` Halten für Übergabe ·
`2e` Halten für Konferenz · `2f` Accept · `30` Konferenz · `32` Verbunden · `3c` Angebot.
Bei RESP_PROCEEDING folgen `2a` und `2b` direkt nacheinander; bei RESP_CONNECT auf einen Anruf in OFFERING/ACCEPTED
erst `2f`, dann `32`.

**Übergänge** (0x100069eb; in jedem Zustand gilt zusätzlich: `02` → UNKNOWN, `1a`–`25` → DISCONNECTED):

| alter Zustand | Code → neuer Zustand |
|---|---|
| UNKNOWN (neu) | `3c`→OFFERING · `0f`–`14`→DIALTONE · `29`→DIALING · `2a`→PROCEEDING · `2b`→RINGBACK · `0b`–`0e`→BUSY · `2f`→ACCEPTED · `32`→CONNECTED · `2c`→ONHOLD · `2d`→ONHOLDPENDTRANSFER · `2e`→ONHOLDPENDCONF · `30`→CONFERENCED · `0a`→IDLE |
| OFFERING | `2f`→ACCEPTED |
| ACCEPTED | `32`→CONNECTED |
| DIALTONE | `29`→DIALING |
| DIALING | `2a`→PROCEEDING · `0b`–`0e`→BUSY |
| PROCEEDING | `2b`→RINGBACK · `0b`–`0e`→BUSY · `30`→CONFERENCED |
| RINGBACK, BUSY | `32`→CONNECTED · `30`→CONFERENCED (nur RINGBACK) · `2b`→RINGBACK (nur BUSY) |
| CONNECTED | `2c`→ONHOLD · `2d`→ONHOLDPENDTRANSFER · `2e`→ONHOLDPENDCONF · `30`→CONFERENCED |
| ONHOLD, CONFERENCED | `32`→CONNECTED |
| ONHOLDPENDTRANSFER | `32`→CONNECTED · `30`→CONFERENCED |
| ONHOLDPENDCONF | `30`→CONFERENCED |
| DISCONNECTED | `0a`→IDLE (Platz wird frei) |

**Meldung → Zustand** (über Treibernamen, passt zu den Mitschnitten): `30` RINGING → OFFERING (neuer Anruf) ·
`36` DIALTONE → DIALTONE (neuer Anruf) · `19` MORE_INFO → DIALING · `3e` PROCEEDING → PROCEEDING, RINGBACK ·
`31` CONNECTED → (ACCEPTED,) CONNECTED · `37` BUSY → BUSY · `34`/`35` HOLD/UNHOLD → ONHOLD/CONNECTED ·
`32` DISCONNECTED → DISCONNECTED, Modus aus IE `08` · `39` RELEASED → IDLE, Platz frei.

**Vorbedingungen der Aufträge** (Sendefunktionen, siehe Abschnitt 6):
- Wählen: abgelehnt, solange ein Anruf DISCONNECTED ist. Kein Anruf → erst `11` belegen (ACK), dann `19` wählen.
  Ein Anruf in ONHOLD oder ONHOLDPENDTRANSFER → `19` direkt (Rückfragewahl, ohne Belegen). Sonst abgelehnt.
- Annehmen: genau ein Anruf in OFFERING → `14`. Zwei Anrufe, einer OFFERING (anklopfend) → `26 16`, dann `26 17`.
- Auflegen: ein Anruf → `13`. Zwei Anrufe → je nach Zuständen `15` und/oder `26 c3`/`26 ee` (Reconnect zum gehaltenen).
- Jeder Auftrag: genau einer offen, bis 5 s auf `04`.

**Folgerung für den Daemon:** Anruftabelle mit eigenen Kennungen; Zustand je Anruf als LINECALLSTATE (oder gleichwertig);
Zuordnung jeder Meldung über den Zustand; Aufträge nur senden, wenn die Vorbedingung erfüllt ist; Modus/Ursache
mitführen (für SIP-Statuscodes und die Anrufstatistik).

## 7. Initialisierung durch den Treiber (lineOpen 0x10007afc)
1. Port öffnen (9600).
2. „XSSEscape“: `02 02 0A 00`, 500 ms Pause.
3. Port 9600 8N1 („ChangeToASFDModus(0)“).
4. `05 88 00 89`, 2 s auf ACK. Ohne ACK: 9600 8O1, Escape wiederholen, zurück auf 8N1, erneut versuchen.
5. QueryVersion: `05 B0 00 B0` → ACK („ATS-Mode“) → ASCII `RQV:0\r` → ACK → `RQQ:1\r` → Einzelbyte `02`.
   Antwort als Textzeile (`ExamineVersionMessage`, Vergleich mit „1.07“).
6. Port 1200 8O1 Xon/Xoff („TAPI modus“).
7. `01 02 01 00`, 5 s auf ACK.

Schritte 2–5 sind ein Service-/Versionsmodus bei 9600; für den Betrieb vermutlich verzichtbar (vermutet).

Empfangsmodi im Treiber (OnData 0x10014219, Flags relativ zum Telefonobjekt):
- **Textmodus („ATS“)**: Flag `+0x14a6`, gesetzt nur in QueryVersion nach dem ACK auf `05 B0 00 B0`.
  Zeilen bis CR/LF, ausgewertet als Versionsantwort. Befehle dort: `RQV:0\r`, `RQQ:1\r` (kein Hayes-AT).
- **Rahmenmodus**: Flag `+0x14a5`, gesetzt nur in Init 0x100147b0 (`01 02 01 00`). Hat Vorrang vor dem Textmodus.
- Beide Flags werden nur im Konstruktor und beim Schließen (0x10014a17) zurückgesetzt.
- Einen Befehl, der die Baudrate des Telefons setzt, gibt es nicht. Die Rate hängt am Modus: 9600 im
  Service-/Textmodus, 1200 im Rahmenmodus. Umschaltung Telefon → Service vermutlich durch das Escape `02 02 0A 00`,
  zurück vermutlich durch `RQQ:1\r` + `02` (vermutet, Wirkung am Gerät nicht belegt).
- Ein Hayes-AT-Protokoll (`AT$…`) kommt in `Ergoline.tsp` nicht vor.

## 8. Offene Fragen
1. ~~Nimmt das Telefon `01 02 01 00` bei 1200 8O1 direkt an?~~ Ja, ACK `04 00` (2026-10-01). Meldung Typ `01`: im Treiber ungenutzt; Bedeutung nur noch per Versuch (Anmelden bei abgehobenem Hörer/im Gespräch) zu klären.
2. Xon/Xoff: Die Auftragstypen `11` und `13` sind zugleich die Xon/Xoff-Zeichen. Wie verhält sich das in der Praxis?
3. Bedeutung von `98` und der Aufträge `15`, `18`, `1b`–`24`, `27`.
4. Kommen Ereignisse ohne jede vorherige Eingabe (Neustart-Test)?
5. Warum wiederholt sich `36` nach 10 s?

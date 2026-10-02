# Betrieb auf dem Gateway-Pi

Stand 2026-10-01. Alle Dienste laufen auf `sopho-gw` (Raspberry Pi 4, Debian 13 Trixie).

```
D340 ─seriell─ sopho2sipd ─ctrl_tcp 127.0.0.1:4444─ baresip ─SIP 127.0.0.1:5070⇄5060─ Asterisk ─SIP 5060─ Softphones (tel1, tel2)
                   └─ Webportal :8080 (Anrufliste, Rückruf, Wähltastatur)
```

| Dienst | Unit | Konfiguration | Zweck |
|---|---|---|---|
| `sopho2sipd` | `gateway/betrieb/sopho2sipd.service` | Aufrufoptionen in der Unit | Telefon, Zustandsautomat, Anrufdatensätze, Portal, SIP-Brücke, Rückwärtssuche |
| `baresip` 4.12 | `gateway/betrieb/baresip.service` | `gateway/baresip/config` → `~/.baresip/` | SIP-Seite, Audio über UCA222 (`plughw:CODEC,0`), nur lokal |
| `asterisk` | Unit aus dem Quellbaum + Drop-in | `gateway/asterisk/*.conf` → `/etc/asterisk/` | Registrar für Softphones, Wählplan |
| `nftables` | Debian | `gateway/betrieb/sopho2sip.nft` | Firewall |

## Einrichten (vom Laptop, Reihenfolge)
```
ssh sopho-gw 'bash -s' < tools/pi_bootstrap.sh
ssh sopho-gw 'git clone https://github.com/schnebeck/Sopho2SIP.git'
tools/firewall.sh                                           # mit Rücknahme nach 120 s, falls SSH abreißt
scp tools/asterisk_build.sh sopho-gw:/tmp/ && ssh sopho-gw 'bash /tmp/asterisk_build.sh'   # ~15 min
scp tools/baresip_build.sh sopho-gw:/tmp/ && ssh sopho-gw 'bash /tmp/baresip_build.sh v4.12.0'   # ~5 min, /usr/local
ssh sopho-gw 'cd ~/Sopho2SIP && tools/asterisk_config.sh'   # Passwörter → ~/.config/sopho2sip/sip-zugaenge.txt
ssh sopho-gw 'cd ~/Sopho2SIP && sudo install -m 644 gateway/betrieb/sopho2sipd.service /etc/systemd/system/ \
  && sudo install -m 644 gateway/betrieb/sopho2sip.logrotate /etc/logrotate.d/sopho2sip \
  && sudo systemctl daemon-reload && sudo systemctl enable --now sopho2sipd'
ssh -t sopho-gw 'python3 ~/Sopho2SIP/gateway/portal.py passwort'
ssh sopho-gw 'python3 ~/Sopho2SIP/gateway/portal.py zertifikat && sudo systemctl restart sopho2sipd'
```

## Aktualisieren
`ssh sopho-gw 'cd ~/Sopho2SIP && git pull && sudo systemctl restart sopho2sipd'`
(Asterisk-/baresip-Dateien geändert: zusätzlich `tools/asterisk_config.sh`.)

## baresip 4.x: Besonderheiten
- Debian/Trixie liefert nur 1.1.0 (2021); `tools/baresip_build.sh` baut `re` + `baresip` aus dem Quelltext nach `/usr/local`.
- `module_tmp` gibt es nicht mehr: `account.so` als `module_app` laden, sonst kein Konto.
- Loopback wird aus den lokalen Adressen gefiltert; `net_interface 127.0.0.1` erzwingt sie (sonst „SIP register failed:
  Protocol not supported“ bei `sip_listen 127.0.0.1:…`).
- Jitterbuffer heißt `audio_jitter_buffer_type`/`audio_jitter_buffer_ms`.
- Eingehende Anrufe nur an den Benutzer des Kontos (`sip:gateway@…`), andere bekommen 404.
- `ctrl_tcp`: Ereignisfelder wie in 1.1.0; der Befehl `sndcode` existiert nicht mehr (DTMF senden brauchen wir nicht).

## Sicherheit
- Firewall: eingehend nur SSH (Schlüssel) von überall; Portal 8080, SIP 5060, RTP 10000–20000, mDNS nur aus
  `130.75.63.128/25` und dem VPN `10.8.6.0/24`. Zusätzlich PJSIP-ACL mit denselben Netzen.
- Portal: `https://130.75.63.159:8080/` mit selbstsigniertem Zertifikat (`python3 gateway/portal.py zertifikat`,
  Ausnahme einmal im Browser bestätigen, SHA-256-Fingerabdruck vergleichen). HTTPS ist Voraussetzung für
  Browser-Benachrichtigungen. HTTP-Basic-Auth (PBKDF2); ohne Passwortdatei nur auf 127.0.0.1
  (`ssh -L 8080:localhost:8080 sopho-gw`). POST-Aufträge brauchen den Kopf `X-Sopho2SIP: 1`.
- Anrufhinweis im Portal: Browser-Benachrichtigung (Klick holt den Tab nach vorn; selbst nach vorn holen darf
  sich ein Tab nicht), blinkender Tab-Titel, optional Klingelton. Einstellungen je Browser (localStorage).
- **Steuerung:** Ohne `--steuerung` sendet der Daemon nur Anmelden/Keepalive. Portal-Wahl, Rückruf und
  SIP-Anrufe zur Sopho werden abgewiesen; eingehende Anrufe lassen die Softphones nur klingeln (Anzeige).
  `--steuerung` erst nach dem Wähltest einschalten (`sudo systemctl edit sopho2sipd`).
- SIP-Zugänge `tel1`/`tel2`: Zufallspasswörter, nur auf dem Pi. Die externe Wahl über `01` macht die Konten
  zum Ziel für Gebührenbetrug; Passwörter nicht weitergeben.

## Rufweg und Nummern
- Sopho → SIP: baresip ruft `sip:<Anrufernummer>@127.0.0.1`; Asterisk (`von-sopho`) setzt daraus die Caller-ID
  (extern ohne Amtsholung, z. B. `0171…`; ohne Nummer `anonymous`) und ruft `tel1` und `tel2` 60 s lang.
  Nimmt ein Softphone ab, sendet der Daemon „Annehmen“ an die D340.
- SIP → Sopho: Asterisk (`von-intern`) ruft baresip mit der gewählten Nummer als Absender; der Daemon wählt sie
  an der D340 (`0…` bekommt die Amtsholung `01`, `010…` gilt als schon mit Amtsholung, `+` → `00`,
  ohne führende 0 = Nebenstelle). Meldet sich die Gegenseite, nimmt baresip an.
- DTMF vom Softphone (RFC 4733) → Ziffer als Nachwahl (Rahmen `19`, Treiber `TSPI_lineDial`). Ob die Gegenseite
  dabei Töne hört: **vermutet**, beim ersten Wähltest prüfen.
- Sprache: nur mit „TAPI: Sprache über Zusatzgerät“ am Telefon und angeschlossener UCA222 (`docs/audio_verkabelung.html`).

## Rückwärtssuche
Mit `--rueckwaertssuche` (in der Unit gesetzt) schlägt der Daemon beim Klingeln bzw. bei eigener Wahl den Namen
externer Nummern nach (`gateway/rueckwaerts.py`): zuerst 11880.com (JSON-LD, Telefonnummer muss passen), dann
Das Örtliche (nur bei Weiterleitung auf einen Eintrag). Name/Ort erscheinen im Portal und im Anrufdatensatz.
**Datenschutz:** Jede externe Anrufernummer geht an diese Dienste. Zwischenspeicher
`~/.local/share/sopho2sip/rueckwaerts.json` (Treffer 30 Tage, ohne Treffer 7 Tage). Nebenstellen werden nie gesucht.
Mobilnummern stehen selten in Verzeichnissen. Abschalten: Option aus der Unit entfernen.

## Erste SIP-Gespräche (2026-10-02/03)
- Handy → Nebenstelle → Softphone `tel1` (Laptop, baresip 1.0.0 über VPN) angenommen: Brücke nimmt an der D340 an,
  schaltet X-Eingang ein, Gespräch 118 s ohne Abbruch, Auflegen vom Softphone löst an der D340 aus.
- Messung mit automatisch annehmendem Testprofil (spielt eine Sprachnachricht, Asterisk-Mitschnitt `MITSCHNITT=1`):
  RTP in beiden Richtungen 0 Pakete verloren, Jitter ≤ 3,5 ms; Aufnahme „vom Pi“ (Anrufer) 54 s ohne Aussetzer;
  Nachricht kam beim Anrufer gut an. Zerhackter Ton im ersten Versuch: Laptop-Seite (Bluetooth-Headset an zwei
  Geräten, ALSA→PipeWire in baresip 1.0.0), nicht die Strecke über den Pi.
- Die Sprache vom Pi hat einen Gleichanteil von etwa −49 dBFS (UCA222-Eingang); unhörbar, Hochpass noch offen.
- Betriebsart: Standard ist „nur Anrufliste/Portal“ (Drop-in `/etc/systemd/system/sopho2sipd.service.d/steuerung.conf`);
  für SIP-Betrieb dort `--baresip 127.0.0.1:4444 --steuerung` ergänzen (Freigabe Nutzer).

## Beobachten
```
ssh sopho-gw journalctl -u sopho2sipd -f            # Telefon, Brücke, Aufträge
ssh sopho-gw journalctl -u baresip -f
ssh sopho-gw sudo asterisk -rvvv                     # Asterisk-Konsole
ssh sopho-gw tail ~/.local/share/sopho2sip/anrufe.jsonl
```
Rohprotokolle `~/Sopho2SIP/logs/ergo_*.log` rotieren täglich (14 Stück, höchstens 30 Tage); Anrufdatensätze nicht.

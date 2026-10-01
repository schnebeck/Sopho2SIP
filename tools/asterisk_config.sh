#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Asterisk- und baresip-Konfiguration aus dem Repo auf dem Pi einrichten (nach tools/asterisk_build.sh).
# Läuft auf dem Pi im Repo:  ssh sopho-gw 'cd ~/Sopho2SIP && tools/asterisk_config.sh'
# Erzeugt beim ersten Lauf Zufallspasswörter für die SIP-Konten (nur auf dem Pi, nie im Repo):
#   /etc/asterisk/pjsip_konten.conf (für Asterisk), ~/.config/sopho2sip/sip-zugaenge.txt (für dich, Modus 600).
# Idempotent: vorhandene Passwörter bleiben erhalten.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -x /usr/sbin/asterisk ] || { echo "Asterisk fehlt: erst tools/asterisk_build.sh"; exit 1; }

# --- Asterisk ---------------------------------------------------------------------------------------
for f in gateway/asterisk/*.conf; do
    sudo install -o asterisk -g asterisk -m 640 "$f" /etc/asterisk/
done

KONTEN=/etc/asterisk/pjsip_konten.conf
ZUGAENGE=$HOME/.config/sopho2sip/sip-zugaenge.txt
pw() { openssl rand -base64 24 | tr -d '/+=' | cut -c1-24; }
if ! sudo test -f "$KONTEN"; then
    PW_GW=$(pw); PW_T1=$(pw); PW_T2=$(pw)
    sudo install -o asterisk -g asterisk -m 640 /dev/stdin "$KONTEN" <<EOF
; erzeugt von tools/asterisk_config.sh am $(date -I) – nicht ins Repo
[gateway](endpunkt)
context = von-sopho
auth = gateway
aors = gateway
allow = !all,alaw
[gateway](zugang)
username = gateway
password = $PW_GW
[gateway](adresse)
max_contacts = 1

[tel1](endpunkt)
context = von-intern
auth = tel1
aors = tel1
[tel1](zugang)
username = tel1
password = $PW_T1
[tel1](adresse)

[tel2](endpunkt)
context = von-intern
auth = tel2
aors = tel2
[tel2](zugang)
username = tel2
password = $PW_T2
[tel2](adresse)
EOF
    mkdir -p "$(dirname "$ZUGAENGE")"
    install -m 600 /dev/stdin "$ZUGAENGE" <<EOF
SIP-Zugänge Sopho2SIP (Server: $(hostname -I | awk '{print $1}'), Port 5060 UDP/TCP, Codec G.711 A-law)
tel1  $PW_T1
tel2  $PW_T2
gateway (nur baresip auf dem Pi)  $PW_GW
EOF
    echo "== neue SIP-Zugänge in $ZUGAENGE"
fi
PW_GW=$(sudo awk '/^\[gateway\]\(zugang\)/{z=1} z&&/^password/{print $3; exit}' "$KONTEN")

# Logrotation der Asterisk-Logs (aus dem Quellbaum)
QUELL=$(ls -d /usr/local/src/asterisk/asterisk-*/ | tail -1)
[ -f /etc/logrotate.d/asterisk ] || sudo make -C "$QUELL" install-logrotate >/dev/null

# Native systemd-Unit aus dem Quellbaum (statt des generierten Init-Skripts), Laufzeitverzeichnis für den Nutzer
sudo install -m 644 "$QUELL/contrib/systemd/asterisk.service" /etc/systemd/system/asterisk.service
sudo mkdir -p /etc/systemd/system/asterisk.service.d
printf '[Service]\nRuntimeDirectory=asterisk\nRuntimeDirectoryPreserve=yes\n' |
    sudo tee /etc/systemd/system/asterisk.service.d/sopho2sip.conf >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --quiet asterisk
sudo systemctl restart asterisk

# --- baresip ----------------------------------------------------------------------------------------
mkdir -p "$HOME/.baresip"
install -m 644 gateway/baresip/config "$HOME/.baresip/config"
install -m 600 /dev/stdin "$HOME/.baresip/accounts" <<EOF
<sip:gateway@127.0.0.1>;auth_pass=$PW_GW;regint=300;audio_codecs=PCMA;answermode=manual
EOF
sudo install -m 644 gateway/betrieb/baresip.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --quiet baresip
sudo systemctl restart baresip

sleep 4
echo "== Asterisk: $(sudo /usr/sbin/asterisk -rx 'core show version' | head -1)"
sudo /usr/sbin/asterisk -rx 'pjsip show endpoints' | grep -E '^ Endpoint:' || true
systemctl is-active baresip

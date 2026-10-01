#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Asterisk 22 LTS aus dem Quelltext auf dem Pi bauen (Debian 13 Trixie enthält kein Asterisk-Paket).
# Läuft auf dem Pi, gestartet vom Laptop (Dauer auf einem Pi 4 etwa 30–60 min):
#   ssh sopho-gw 'bash -s' < tools/asterisk_build.sh > asterisk_build.log 2>&1
# Idempotent: ein vorhandenes /usr/sbin/asterisk derselben Version wird nicht neu gebaut.
# Konfiguration kommt nicht aus den Beispielen, sondern aus gateway/asterisk/ (tools/asterisk_config.sh).
set -euo pipefail

VERSION_ZWEIG=22
QUELLE=https://downloads.asterisk.org/pub/telephony/asterisk
BAU=/usr/local/src/asterisk

PKGS=(build-essential pkg-config wget bzip2 patch python3 libedit-dev libjansson-dev libxml2-dev uuid-dev
      libsqlite3-dev libssl-dev libsrtp2-dev libcurl4-openssl-dev libopus-dev)
sudo DEBIAN_FRONTEND=noninteractive apt-get -y install "${PKGS[@]}"

sudo mkdir -p "$BAU" && sudo chown "$USER" "$BAU" && cd "$BAU"
# Die Prüfsummendatei von "current" nennt das versionierte Archiv; genau dieses laden und prüfen.
wget -q -O current.sha256 "$QUELLE/asterisk-$VERSION_ZWEIG-current.sha256"
ARCHIV=$(awk '{print $2}' current.sha256)
wget -q -N "$QUELLE/$ARCHIV"
sha256sum -c current.sha256
VERZ=${ARCHIV%.tar.gz}
echo "== Quelle: $VERZ"
if [ -x /usr/sbin/asterisk ] && [ "$(/usr/sbin/asterisk -V)" = "Asterisk ${VERZ#asterisk-}" ]; then
    echo "== $VERZ ist bereits installiert"; exit 0
fi
rm -rf "$VERZ" && tar xzf "$ARCHIV" && cd "$VERZ"

./configure --with-jansson-bundled=no --with-pjproject-bundled >/dev/null
make menuselect.makeopts >/dev/null
# Portabel bauen (kein -march=native), keine Beispiel-Sounds nachladen.
menuselect/menuselect --disable BUILD_NATIVE --disable CORE-SOUNDS-EN-GSM --disable MOH-OPSOUND-WAV menuselect.makeopts
time make -j"$(nproc)" >/dev/null
sudo make install >/dev/null
sudo make config >/dev/null          # systemd-/Init-Einbindung
sudo ldconfig

# Eigener Systemnutzer statt root
id asterisk >/dev/null 2>&1 || sudo useradd --system --home /var/lib/asterisk --shell /usr/sbin/nologin asterisk
sudo usermod -aG audio,dialout asterisk
for d in /var/lib/asterisk /var/log/asterisk /var/spool/asterisk /var/run/asterisk /etc/asterisk; do
    sudo mkdir -p "$d" && sudo chown -R asterisk:asterisk "$d"
done
echo "== installiert: $(/usr/sbin/asterisk -V)"

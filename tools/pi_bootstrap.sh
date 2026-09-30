#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Grundeinrichtung des Gateway-Pi (Phase 1). Läuft auf dem Pi, gestartet vom Laptop:
#   ssh sopho-gw 'bash -s' < tools/pi_bootstrap.sh
# Idempotent, kann mehrfach laufen.
set -euo pipefail

PKGS=(git python3-venv python3-serial picocom minicom alsa-utils sox)

echo "== System: $(hostname), $(. /etc/os-release; echo "$PRETTY_NAME"), $(uname -m)"
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get -y full-upgrade
sudo DEBIAN_FRONTEND=noninteractive apt-get -y install "${PKGS[@]}"
sudo apt-get -y autoremove

sudo usermod -aG dialout,audio "$USER"
sudo timedatectl set-timezone Europe/Berlin
sudo timedatectl set-ntp true

echo "== Status"
timedatectl show -p NTPSynchronized -p Timezone
id "$USER"
ip -br addr | grep -v '^lo'
[ -f /var/run/reboot-required ] && echo "!! Neustart erforderlich (sudo reboot)" || true

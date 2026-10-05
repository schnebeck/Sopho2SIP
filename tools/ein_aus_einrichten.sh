#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Ein/Aus-Taster (SW3, GPIO3) und STATUS-LED (D3, GPIO22) des CM4-Trägers einrichten. Läuft auf dem Pi im Repo:
#   ssh sopho-gw 'cd ~/Sopho2SIP && tools/ein_aus_einrichten.sh'
# Idempotent. Auf einem Pi ohne CM4-Träger nur die logind-Einstellung (unschädlich), keine Overlays.
#   langer Druck (5 s) im Betrieb → sauber herunterfahren, STATUS leuchtet bis zum Halt
#   kurzer Druck im Halt          → starten (Bootloader: WAKE_ON_GPIO=1, POWER_OFF_ON_HALT=0)
set -euo pipefail
cd "$(dirname "$0")/.."
CONFIG=/boot/firmware/config.txt
ZEILEN=("dtoverlay=gpio-shutdown,gpio_pin=3" "dtoverlay=gpio-led,gpio=22,label=status,trigger=none")

sudo install -D -m 644 gateway/betrieb/logind-ein-aus.conf /etc/systemd/logind.conf.d/sopho2sip-ein-aus.conf
echo "== logind: kurzer Druck auf die Ein/Aus-Taste ignoriert, langer Druck fährt herunter"

modell=$(tr -d '\0' < /proc/device-tree/model)
case "$modell" in
  *"Compute Module 4"*) ;;
  *) echo "== $modell: kein CM4-Träger, Overlays und LED-Dienst ausgelassen"; exit 0 ;;
esac

[ -f /boot/firmware/overlays/gpio-led.dtbo ] || echo "!! /boot/firmware/overlays/gpio-led.dtbo fehlt"
grep -qE '^dtparam=i2c_arm=on' "$CONFIG" && echo "!! dtparam=i2c_arm=on belegt GPIO3 (I2C1-Takt): Zeile entfernen"
if ! grep -qxF "${ZEILEN[0]}" "$CONFIG" || ! grep -qxF "${ZEILEN[1]}" "$CONFIG"; then
  grep -qxF "# Sopho2SIP: Ein/Aus-Taster und STATUS-LED" "$CONFIG" || \
    printf '\n# Sopho2SIP: Ein/Aus-Taster und STATUS-LED\n[all]\n' | sudo tee -a "$CONFIG" >/dev/null
  for z in "${ZEILEN[@]}"; do
    grep -qxF "$z" "$CONFIG" || { echo "$z" | sudo tee -a "$CONFIG" >/dev/null; echo "   + $z"; }
  done
fi
echo "== $CONFIG:"; grep -E 'gpio-shutdown|gpio-led' "$CONFIG"

sudo install -m 644 gateway/betrieb/sopho2sip-herunterfahren.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sopho2sip-herunterfahren.service

if command -v rpi-eeprom-config >/dev/null; then
  eeprom=$(sudo rpi-eeprom-config)
  grep -q '^WAKE_ON_GPIO=0' <<<"$eeprom" && echo "!! Bootloader WAKE_ON_GPIO=0: Taster startet nicht (sudo -E rpi-eeprom-config --edit)"
  grep -q '^POWER_OFF_ON_HALT=1' <<<"$eeprom" && echo "!! Bootloader POWER_OFF_ON_HALT=1: Taster startet nicht (sudo -E rpi-eeprom-config --edit)"
  echo "== Bootloader: WAKE_ON_GPIO und POWER_OFF_ON_HALT geprüft"
fi
echo "== Fertig. Wirksam nach dem Neustart (sudo reboot)."

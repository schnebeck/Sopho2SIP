#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Firewall gateway/betrieb/sopho2sip.nft auf dem Pi aktivieren – mit Sicherheitsnetz gegen Aussperren:
# Vor dem Laden wird eine Rücknahme in 120 s geplant; sie wird nur abgebrochen, wenn danach eine NEUE
# SSH-Verbindung vom Laptop klappt. Aufruf auf dem Laptop:  tools/firewall.sh [sopho-gw]
set -euo pipefail
ZIEL=${1:-sopho-gw}
REGELN=$(dirname "$0")/../gateway/betrieb/sopho2sip.nft

scp -q "$REGELN" "$ZIEL":/tmp/sopho2sip.nft
ssh "$ZIEL" 'set -e
  sudo nft -c -f /tmp/sopho2sip.nft
  sudo systemctl stop sopho2sip-ruecknahme.timer 2>/dev/null || true
  sudo systemd-run --quiet --unit sopho2sip-ruecknahme --on-active=120 /usr/sbin/nft delete table inet sopho2sip
  sudo nft delete table inet sopho2sip 2>/dev/null || true
  sudo nft -f /tmp/sopho2sip.nft
  echo "Regeln geladen, Rücknahme in 120 s geplant"'

echo "Prüfe neue SSH-Verbindung …"
if ssh -o ConnectTimeout=10 "$ZIEL" 'sudo systemctl stop sopho2sip-ruecknahme.timer && echo "Rücknahme abgebrochen"'; then
    # Dauerhaft: /etc/nftables.conf lädt nur unsere Tabelle (Debian-Standard enthält nur eine leere Filtertabelle)
    ssh "$ZIEL" 'set -e
      sudo install -D -m 644 /tmp/sopho2sip.nft /etc/nftables.d/sopho2sip.nft
      printf "#!/usr/sbin/nft -f\nflush ruleset\ninclude \"/etc/nftables.d/sopho2sip.nft\"\n" | sudo tee /etc/nftables.conf >/dev/null
      sudo nft -c -f /etc/nftables.conf
      sudo systemctl enable --quiet nftables
      echo "dauerhaft eingerichtet (nftables.service)"'
else
    echo "!! Keine neue SSH-Verbindung – die Regeln werden in spätestens 120 s automatisch entfernt." >&2
    exit 1
fi

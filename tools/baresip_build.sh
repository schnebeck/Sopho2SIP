#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Aktuelles baresip (mit Bibliothek re) aus dem Quelltext auf dem Pi bauen; Debian/Trixie liefert nur 1.1.0 (2021).
# Läuft auf dem Pi:  scp tools/baresip_build.sh sopho-gw:/tmp/ && ssh sopho-gw 'bash /tmp/baresip_build.sh [v4.12.0]'
# Installiert nach /usr/local (bin/baresip, lib/baresip/modules, lib/libre.so); entfernt danach das Debian-Paket.
# Module werden nach vorhandenen Bibliotheken gewählt: ALSA, PipeWire (für Bluetooth-Headset), Opus, OpenSSL.
# Eigene Module aus <Repo>/gateway/baresip (APP_MODULES, derzeit: dcsperre = DC-Blocker) werden mitgebaut, wenn das
# Repo unter ~/Sopho2SIP liegt. Idempotent: dieselbe Version samt eigener Module wird nicht neu gebaut.
set -euo pipefail
VERSION=${1:-v4.12.0}
BAU=/usr/local/src/baresip
REPO=${REPO:-$HOME/Sopho2SIP}
EIGENE=(dcsperre)

PKGS=(build-essential cmake pkg-config git libssl-dev zlib1g-dev libasound2-dev libpipewire-0.3-dev libopus-dev)
sudo DEBIAN_FRONTEND=noninteractive apt-get -y install --no-install-recommends "${PKGS[@]}" >/dev/null

APP=()
if [ -d "$REPO/gateway/baresip" ]; then
    APP=(-DAPP_MODULES_DIR="$REPO/gateway/baresip" -DAPP_MODULES="$(IFS=';'; echo "${EIGENE[*]}")")
fi
vollstaendig() {
    /usr/local/bin/baresip -h 2>&1 | grep -q "baresip ${VERSION#v} " || return 1
    [ ${#APP[@]} -eq 0 ] && return 0
    for m in "${EIGENE[@]}"; do [ -f "/usr/local/lib/baresip/modules/$m.so" ] || return 1; done
}
if [ -x /usr/local/bin/baresip ] && vollstaendig; then
    echo "== baresip $VERSION (mit eigenen Modulen) ist bereits installiert"; exit 0
fi

sudo mkdir -p "$BAU" && sudo chown "$USER" "$BAU" && cd "$BAU"
for r in re baresip; do
    if [ "$(git -C "$r" describe --tags 2>/dev/null)" != "$VERSION" ]; then
        rm -rf "$r"
        git -c advice.detachedHead=false clone -q --depth 1 --branch "$VERSION" "https://github.com/baresip/$r.git"
    fi
    echo "== $r $(git -C "$r" describe --tags) $(git -C "$r" rev-parse --short HEAD)"
done

cmake -S re -B re/build -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build re/build -j"$(nproc)" >/dev/null
sudo cmake --install re/build >/dev/null
sudo ldconfig

cmake -S baresip -B baresip/build -DCMAKE_BUILD_TYPE=Release "${APP[@]}" >/dev/null
cmake --build baresip/build -j"$(nproc)" >/dev/null
sudo cmake --install baresip/build >/dev/null
sudo ldconfig

# Debian-Paket entfernen, damit nur eine Version existiert (Konfiguration in ~/.baresip bleibt)
if dpkg -s baresip-core >/dev/null 2>&1; then
    sudo DEBIAN_FRONTEND=noninteractive apt-get -y remove baresip-core >/dev/null
fi

echo "== installiert: $(/usr/local/bin/baresip -h 2>&1 | head -1)"
echo "== Module: $(ls /usr/local/lib/baresip/modules | sed 's/\.so$//' | tr '\n' ' ')"

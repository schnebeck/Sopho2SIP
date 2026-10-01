#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Audiotest auf dem Pi (Phase 4): eingehenden Anruf annehmen, X_OUT aufnehmen, Testton auf X_IN, auflegen.
#   tools/audio_test.sh [GESPRÄCH_S=30] [TON_AB_S=15] [PEGEL=-40dB]
# Ablauf: Dienst sopho2sipd anhalten (serielle Schnittstelle frei), PCM-Wiedergabe der UCA222 auf PEGEL,
# tools/ergo.py annahmetest (Annehmen/Auflegen: braucht Freigabe des Nutzers!), ab CONNECTED Aufnahme
# (48 kHz stereo, links = X_OUT), nach TON_AB_S s 3 s Sinus 1 kHz, danach Pegelauswertung; Dienst wieder starten.
# Aufnahmen enthalten Sprache: logs/audio_*.wav sind per .gitignore ausgeschlossen.
set -euo pipefail
cd "$(dirname "$0")/.."
GESPRAECH=${1:-30}; TON_AB=${2:-15}; PEGEL=${3:--40dB}
KARTE=CODEC; GERAET=plughw:$KARTE,0
STAMP=$(date +%Y%m%d_%H%M%S)
WAV=logs/audio_$STAMP.wav; ERGO_OUT=/tmp/audio_test_ergo_$STAMP.txt

aufraeumen() { kill "${AUFNAHME:-}" 2>/dev/null || true; sudo systemctl start sopho2sipd; }
trap aufraeumen EXIT
sudo systemctl stop sopho2sipd
amixer -q -c $KARTE sset PCM -- "$PEGEL"
echo "== Wiedergabe $PEGEL; warte bis 120 s auf einen Anruf …"

python3 -u tools/ergo.py annahmetest --freigabe --gespraech "$GESPRAECH" --warte 120 > "$ERGO_OUT" 2>&1 &
ERGO=$!
until grep -q "MELDUNG CONNECTED" "$ERGO_OUT"; do
    kill -0 $ERGO 2>/dev/null || { cat "$ERGO_OUT"; echo "!! kein Gespräch zustande gekommen"; exit 1; }
    sleep 0.2
done
echo "== verbunden: Aufnahme $GESPRAECH s → $WAV"
arecord -q -D $GERAET -f S16_LE -r 48000 -c 2 -d "$GESPRAECH" "$WAV" &
AUFNAHME=$!
sleep "$TON_AB"
echo "== Testton 1 kHz, 3 s"
sox -q -n -r 48000 -c 2 -b 16 -t alsa $GERAET synth 3 sine 1000 vol 0.5
wait $AUFNAHME || true
wait $ERGO || true
grep -E ">>|MELDUNG|Quittung|Ende" "$ERGO_OUT" | sed -E 's/(6c 0d|ANRUFER=).*/\1 …/'

echo "== Pegel X_OUT (linker Kanal), je 5 s:"
for ab in $(seq 0 5 $((GESPRAECH - 5))); do
    rms=$(sox "$WAV" -n remix 1 trim "$ab" 5 stat 2>&1 | awk '/RMS     amplitude/{print $3}')
    spitze=$(sox "$WAV" -n remix 1 trim "$ab" 5 stat 2>&1 | awk '/Maximum amplitude/{print $3}')
    printf "  %3d–%3d s  RMS %6.1f dBFS  Spitze %6.1f dBFS\n" "$ab" $((ab + 5)) \
        "$(python3 -c "import math;print(20*math.log10(max($rms,1e-9)))")" \
        "$(python3 -c "import math;print(20*math.log10(max($spitze,1e-9)))")"
done
echo "== Testton im Rückkanal? Bereich $TON_AB–$((TON_AB + 3)) s, 1 kHz-Anteil:"
sox "$WAV" -n remix 1 trim "$TON_AB" 3 sinc 900-1100 stat 2>&1 | awk '/RMS     amplitude/{printf "  RMS 1 kHz %.1f dBFS (Echo/Übersprechen, falls deutlich über Ruhe)\n", 20*log($3)/log(10)}'

#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Audiotest auf dem Pi (Phase 4): eingehenden Anruf annehmen, X_OUT aufnehmen, Testton auf X_IN, auflegen.
#   tools/audio_test.sh [GESPRÄCH_S=30] [TON_AB_S=15] [TÖNE_dBFS="-46 -36 -26 -16"] [NUMMER]
# Ohne NUMMER wird ein eingehender Anruf angenommen; mit NUMMER wählt der Pi (ergo.py waehltest, Freigabe!).
# NACHRICHT=datei.wav: statt der Töne diese Aufnahme spielen, je Wert in TÖNE mit dieser Verstärkung (dB).
# Ablauf: Dienst sopho2sipd anhalten (serielle Schnittstelle frei), PCM-Regler der UCA222 auf 0 dB,
# tools/ergo.py annahmetest (Annehmen/Auflegen: braucht Freigabe des Nutzers!), ab CONNECTED Aufnahme
# (48 kHz stereo, links = X_OUT), ab TON_AB_S je Pegel 2 s Sinus 1 kHz + 2 s Pause, danach sekundenweise
# Auswertung (Pegel X_OUT, 1-kHz-Anteil = Echo des Testtons); Dienst wieder starten.
# Aufnahmen enthalten Sprache: logs/audio_*.wav sind per .gitignore ausgeschlossen.
set -euo pipefail
export LC_ALL=C
cd "$(dirname "$0")/.."
GESPRAECH=${1:-30}; TON_AB=${2:-15}; TOENE=${3:-"-46 -36 -26 -16"}; NUMMER=${4:-}
KARTE=CODEC; GERAET=plughw:$KARTE,0
STAMP=$(date +%Y%m%d_%H%M%S)
WAV=logs/audio_$STAMP.wav; ERGO_OUT=/tmp/audio_test_ergo_$STAMP.txt

aufraeumen() { kill "${AUFNAHME:-}" 2>/dev/null || true; sudo systemctl start sopho2sipd; }
trap aufraeumen EXIT
sudo systemctl stop sopho2sipd
amixer -q -c $KARTE sset PCM -- 0dB
if [ -n "$NUMMER" ]; then
    echo "== PCM 0 dB, Töne $TOENE dBFS; wähle (bis 60 s bis zur Annahme) …"
    python3 -u tools/ergo.py waehltest "$NUMMER" --freigabe --warte 60 --gespraech "$GESPRAECH" > "$ERGO_OUT" 2>&1 &
else
    echo "== PCM 0 dB, Töne $TOENE dBFS; warte bis 120 s auf einen Anruf …"
    python3 -u tools/ergo.py annahmetest --freigabe --gespraech "$GESPRAECH" --warte 120 > "$ERGO_OUT" 2>&1 &
fi
ERGO=$!
until grep -q "MELDUNG CONNECTED" "$ERGO_OUT"; do
    kill -0 $ERGO 2>/dev/null || { cat "$ERGO_OUT"; echo "!! kein Gespräch zustande gekommen"; exit 1; }
    sleep 0.2
done
echo "== verbunden: Aufnahme $GESPRAECH s → $WAV"
arecord -q -D $GERAET -f S16_LE -r 48000 -c 2 -d "$GESPRAECH" "$WAV" &
AUFNAHME=$!
sleep "$TON_AB"
for pegel in $TOENE; do
    if [ -n "${NACHRICHT:-}" ]; then
        echo "== Nachricht $NACHRICHT, Verstärkung $pegel dB"
        sox -q "$NACHRICHT" -t alsa $GERAET gain "$pegel"
        sleep 1
    else
        echo "== Testton 1 kHz, 2 s, $pegel dBFS"
        sox -q -n -r 48000 -c 2 -b 16 -t alsa $GERAET synth 2 sine 1000 gain "$pegel"
        sleep 2
    fi
done
wait $AUFNAHME || true
wait $ERGO || true
grep -E ">>|MELDUNG|Quittung|Ende" "$ERGO_OUT" | sed -E 's/(6c 0d|70 0e 81|70 0d|ANRUFER=|ZIEL=).*/\1 …/'

db() { python3 -c "import math,sys;print(f'{20*math.log10(max(float(sys.argv[1]),1e-9)):6.1f}')" "$1"; }
wert() { sox "$WAV" -n remix "$1" trim "$2" 1 ${3:-} stat 2>&1 | awk -v k="$4" '$0 ~ k {print $3}'; }
echo "== je Sekunde: X_OUT RMS/Spitze, 1-kHz-Anteil (Echo des Testtons ab ${TON_AB} s), rechter Kanal"
echo "  s   RMS    Spitze  1kHz   rechts"
for s in $(seq 0 $((GESPRAECH - 1))); do
    printf "%3d %s %s %s %s\n" "$s" "$(db "$(wert 1 "$s" "" "RMS     amplitude")")" \
        "$(db "$(wert 1 "$s" "" "Maximum amplitude")")" "$(db "$(wert 1 "$s" "sinc 950-1050" "RMS     amplitude")")" \
        "$(db "$(wert 2 "$s" "" "RMS     amplitude")")"
done

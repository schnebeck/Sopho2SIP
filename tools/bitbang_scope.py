#!/usr/bin/env python3
"""Logikanalysator mit dem FT232R im synchronen Bitbang-Modus.

TXD (D0) wird als Ausgang benutzt und erzeugt freigegebene Befehle als UART-Rahmen (8N1),
RXD (D1) wird bei jedem Takt mitgelesen. Ergebnis: Pegelverlauf der Sendeleitung des Telefons
als Lauflängen (Pegel, µs) im Log, dazu die Rohabtastwerte als .bin (1 Byte je Takt, Bit 1 = RXD).

Achtung: Das Takten stockt zwischen den USB-Blöcken kurz (Lücken werden je Block mit
Zeitstempel protokolliert). Jeder Befehl liegt vollständig in einem Block und bleibt daher unverzerrt.

Benötigt pyftdi; der Kernel-Treiber ftdi_sio wird für die Dauer der Messung abgekoppelt.

Beispiel:
  ./bitbang_scope.py --serial A97WEQGD ATI0 ATI0
"""
import argparse
import datetime as dt
import pathlib
import sys
import time

from pyftdi.ftdi import Ftdi

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from serial_probe import SAFE, LOGDIR, ts  # noqa: E402

TX, RX = 0x01, 0x02
BLOCK = 64           # Abtastwerte je USB-Block; 2 Blöcke im Voraus (RX-FIFO des FT232R: 256 Byte)


def uart_frame(data: bytes, spb: int) -> bytes:
    """8N1-Rahmen als Abtastfolge für den TXD-Pin (Ruhe = 1)."""
    out = bytearray()
    for b in data:
        bits = [0] + [(b >> i) & 1 for i in range(8)] + [1]
        for bit in bits:
            out += bytes([TX if bit else 0]) * spb
    return bytes(out)


def runs(samples: bytes, fs: float):
    """Lauflängen des RXD-Pegels als (Pegel, Dauer µs)."""
    res, cur, n = [], None, 0
    for s in samples:
        lvl = 1 if s & RX else 0
        if lvl == cur:
            n += 1
        else:
            if cur is not None:
                res.append((cur, n * 1e6 / fs))
            cur, n = lvl, 1
    if cur is not None:
        res.append((cur, n * 1e6 / fs))
    return res


def uart_decode(samples: bytes, fs: float, baud: int):
    """RXD-Abtastwerte als UART 8N1 dekodieren: Liste (Abtastindex, Byte, Rahmenfehler)."""
    spb = fs / baud
    bits = [1 if s & RX else 0 for s in samples]
    res, i, n = [], 1, len(bits)
    while i < n:
        if bits[i - 1] == 1 and bits[i] == 0:              # fallende Flanke = Startbit
            mid = i + spb / 2
            if int(mid + 9 * spb) >= n:
                break
            if bits[int(mid)] == 0:
                val = sum(bits[int(mid + k * spb)] << (k - 1) for k in range(1, 9))
                stop = bits[int(mid + 9 * spb)]
                res.append((i, val, stop == 0))
                i = int(mid + 9 * spb)
                continue
        i += 1
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", required=True, help="FTDI-Seriennummer, z. B. A97WEQGD")
    ap.add_argument("--baud", type=int, default=9600, help="UART-Rate der erzeugten Befehle")
    ap.add_argument("--spb", type=int, default=4, help="Abtastwerte je Bit")
    ap.add_argument("--rx-baud", type=int, default=1200, help="UART-Rate zum Dekodieren von RXD")
    ap.add_argument("--gap", type=float, default=1.5, help="Zeit nach jedem Befehl (s)")
    ap.add_argument("--pre", type=float, default=0.0, help="Ruhezeit vor dem ersten Befehl (s)")
    ap.add_argument("commands", nargs="*")
    a = ap.parse_args()
    for c in a.commands:
        if c.upper() not in SAFE:
            sys.exit(f"Befehl {c!r} ist hier nicht freigegeben")

    fs = a.baud * a.spb
    idle = bytes([TX]) * BLOCK
    LOGDIR.mkdir(exist_ok=True)
    stamp = f"{dt.datetime.now():%Y%m%d_%H%M%S}"
    logfile, binfile = LOGDIR / f"bitbang_{stamp}.log", LOGDIR / f"bitbang_{stamp}.bin"

    f = Ftdi()
    real = f.open_bitbang_from_url(f"ftdi://ftdi:232r:{a.serial}/1", direction=TX, latency=1,
                                   baudrate=fs, sync=True)
    samples = bytearray()
    with open(logfile, "x", encoding="utf-8") as log:
        def out(line: str) -> None:
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()

        # Ablauf vorab komplett berechnen, dann mit Vorausschreiben lückenlos takten
        plan = bytearray(idle) + bytes([TX]) * int(a.pre * fs)
        for c in a.commands:
            raw = c.encode("ascii") + b"\r"
            out(f"{ts()} >> {raw!r} @ {a.baud} ab Abtastwert {len(plan)}")
            plan += uart_frame(raw, a.spb)
            plan += bytes([TX]) * int(a.gap * fs)
        chunks = [bytes(plan[i:i + BLOCK]) for i in range(0, len(plan), BLOCK)]
        t0 = time.perf_counter()
        ahead = 2
        for ch in chunks[:ahead]:
            f.write_data(ch)
        for n, ch in enumerate(chunks):
            if n + ahead < len(chunks):
                f.write_data(chunks[n + ahead])
            rx = f.read_data_bytes(len(ch), attempt=100)
            if len(rx) != len(ch):
                out(f"# WARN Block {n}: {len(ch)} erwartet, {len(rx)} gelesen")
            samples.extend(rx)
        span = time.perf_counter() - t0
        f.close()
        binfile.write_bytes(bytes(samples))

        out(f"# {len(samples)} Abtastwerte in {span:.3f} s Wandzeit -> effektiv {len(samples)/span:.0f} Hz "
            f"(Soll {fs}; Differenz = Lücken zwischen Blöcken)")
        out(f"# Rohdaten: {binfile}")
        pos = 0
        for lvl, us in runs(samples, fs):
            if not (lvl == 1 and us > 50_000):   # lange Ruhephasen nur kurz vermerken
                out(f"RX {'H' if lvl else 'L'} {us:10.1f} µs  @{pos}")
            else:
                out(f"RX H (Ruhe) {us/1000:8.1f} ms  @{pos}")
            pos += round(us * fs / 1e6)
        dec = uart_decode(samples, fs, a.rx_baud)
        out(f"# RXD dekodiert als {a.rx_baud} 8N1: {len(dec)} Byte")
        for idx, val, ferr in dec:
            out(f"RX @{idx:7d} (+{idx / fs:7.3f} s)  0x{val:02x} {chr(val)!r:6}{'  RAHMENFEHLER' if ferr else ''}")
        out(f"# {ts()} Ende, Log: {logfile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

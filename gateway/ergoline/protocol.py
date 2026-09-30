# SPDX-License-Identifier: GPL-3.0-or-later
"""Rahmenprotokoll der ErgoLine D340 an der PC-Schnittstelle (1200 Baud, 8O1).

Reine Protokoll-Logik ohne Ein-/Ausgabe. Quelle: ref/ergoline_tsp/Ergoline.tsp und Mitschnitte,
Beschreibung in docs/protocol.md. Rahmen: <Klasse> <Länge> <Länge Bytes Nutzdaten>.
"""
from __future__ import annotations

from dataclasses import dataclass

# Schicht 2: Klasse (Byte 0)
AUFTRAG, MELDUNG, REJ, ACK, ERR = 0x01, 0x02, 0x03, 0x04, 0x05
KLASSE = {AUFTRAG: "AUFTRAG", MELDUNG: "MELDUNG", REJ: "REJ", ACK: "ACK", ERR: "ERR"}
QUITTUNGEN = (REJ, ACK, ERR)

# Schicht 3: Typ der Meldungen des Telefons (Nutzbyte 0), Namen wie im Treiber (L3_STATUS…)
MELDUNGSTYP = {
    0x19: "MORE_INFO", 0x30: "RINGING", 0x31: "CONNECTED", 0x32: "DISCONNECTED", 0x33: "IDLE",
    0x34: "HOLD", 0x35: "UNHOLD", 0x36: "DIALTONE", 0x37: "BUSY", 0x38: "CAMPONBUSY",
    0x39: "RELEASED", 0x3A: "FACILITY_AUS", 0x3B: "FACILITY_EIN", 0x3C: "FACILITY_ABGELEHNT",
    0x3D: "ERROR", 0x3E: "PROCEEDING", 0x3F: "ANKLOPFEN_EIN", 0x40: "ANKLOPFEN_AUS",
    0x41: "USERTOUSER", 0x44: "NOHOLD",
}

# Typ der Aufträge des PCs (aus dem Treiber abgeleitet, am Gerät teils noch ungetestet)
AUFTRAGSTYP = {
    0x00: "KEEPALIVE", 0x01: "ANMELDEN", 0x11: "BELEGEN", 0x13: "AUFLEGEN", 0x14: "ANNEHMEN",
    0x15: "AUFTRAG_15", 0x19: "WAHL", 0x25: "UUI", 0x26: "MERKMAL", 0x27: "AUFTRAG_27",
}

# Merkmalskennung bei FACILITY_EIN/AUS (Meldung, Nutzbyte 2) und MERKMAL (Auftrag, Nutzbyte 2)
MERKMAL = {
    0x01: "UMLEITUNG", 0x0A: "HOERER", 0x16: "ANKLOPFEN_ANZEIGEN", 0x17: "ANKLOPFEN_ANNEHMEN",
    0x1A: "RUECKRUF", 0x1D: "AUFSCHALTEN", 0x1F: "KONFERENZ_VORBEREITEN", 0x30: "DTMF",
    0xC3: "RECONNECT", 0xEE: "RECONNECT_ALT",
}

# Informationselemente wie Q.931
IE_NAME = {0x08: "URSACHE", 0x6C: "ANRUFER", 0x70: "ZIEL", 0x7E: "UUI"}
FACILITY_TYPEN = (0x3A, 0x3B, 0x3C)


@dataclass(frozen=True)
class Rahmen:
    klasse: int
    daten: bytes = b""

    def to_bytes(self) -> bytes:
        if len(self.daten) > 127:
            raise ValueError("Nutzdaten länger als 127 Byte")
        return bytes([self.klasse, len(self.daten)]) + self.daten

    @property
    def typ(self) -> int | None:
        return self.daten[0] if self.daten else None

    def hex(self) -> str:
        return self.to_bytes().hex(" ")

    def beschreibung(self) -> str:
        return beschreibe(self)


class Assembler:
    """Setzt Rahmen aus einem Bytestrom zusammen (wie 0x1000dbe9 im Treiber)."""

    def __init__(self) -> None:
        self._puffer = bytearray()

    def feed(self, daten: bytes) -> list[Rahmen]:
        self._puffer += daten
        fertig = []
        while len(self._puffer) >= 2:
            laenge = self._puffer[1]
            if laenge > 127:                       # Treiber liest die Länge vorzeichenbehaftet
                raise ValueError(f"ungültige Länge {laenge:#04x} im Strom {bytes(self._puffer).hex(' ')}")
            if len(self._puffer) < laenge + 2:
                break
            fertig.append(Rahmen(self._puffer[0], bytes(self._puffer[2:2 + laenge])))
            del self._puffer[:2 + laenge]
        return fertig

    @property
    def rest(self) -> bytes:
        return bytes(self._puffer)


def ies(daten: bytes) -> list[tuple[int, bytes | None]]:
    """Informationselemente ab Nutzbyte 2. Einzeloktett-IEs (Bit 8 gesetzt) liefern Inhalt None."""
    out, i = [], 0
    while i < len(daten):
        kennung = daten[i]
        if kennung & 0x80:
            out.append((kennung, None))
            i += 1
            continue
        if i + 1 >= len(daten):
            out.append((kennung, b""))            # abgeschnitten
            break
        laenge = daten[i + 1]
        out.append((kennung, daten[i + 2:i + 2 + laenge]))
        i += 2 + laenge
    return out


AMTSHOLUNG = "01"   # Amtsholung der Sopho für externe Anrufe (Angabe Nutzer 2026-09-30)


def rufnummer(inhalt: bytes) -> str:
    """Ziffern aus IE 6c/70. Das Telefon liefert reine ASCII-Ziffern; ein führendes Typ-Oktett mit
    gesetztem Bit 8 (wie 0x81 im Wahlauftrag des Treibers) wird übersprungen."""
    if inhalt and inhalt[0] & 0x80:
        inhalt = inhalt[1:]
    return inhalt.decode("ascii", "replace")


def extern(nummer: str, amtsholung: str = AMTSHOLUNG) -> tuple[bool, str]:
    """(ist_extern, Nummer ohne Amtsholung). Interne Nebenstellen bleiben unverändert."""
    if amtsholung and nummer.startswith(amtsholung) and len(nummer) > len(amtsholung):
        return True, nummer[len(amtsholung):]
    return False, nummer


def beschreibe(r: Rahmen) -> str:
    kl = KLASSE.get(r.klasse, f"KLASSE_{r.klasse:02x}")
    if r.klasse in QUITTUNGEN or not r.daten:
        return f"{kl}" + (f" {r.daten.hex(' ')}" if r.daten else "")
    namen = MELDUNGSTYP if r.klasse == MELDUNG else AUFTRAGSTYP
    typ = r.daten[0]
    teile = [kl, namen.get(typ, f"TYP_{typ:02x}")]
    if len(r.daten) >= 2:
        teile.append(f"leitung={r.daten[1]:02x}")
    rest = r.daten[2:]
    if (r.klasse == MELDUNG and typ in FACILITY_TYPEN) or (r.klasse == AUFTRAG and typ == 0x26):
        if rest:
            teile.append(MERKMAL.get(rest[0], f"MERKMAL_{rest[0]:02x}"))
            if len(rest) > 1:
                teile.append(f"+{rest[1:].hex(' ')}")
        return " ".join(teile)
    for kennung, inhalt in ies(rest):
        if inhalt is None:
            teile.append(f"[{kennung:02x}]")
        elif kennung in (0x6C, 0x70):
            nr = rufnummer(inhalt)
            ext, rest_nr = extern(nr)
            teile.append(f"{IE_NAME[kennung]}={nr!r}" + (f" (extern {rest_nr!r})" if ext else " (intern)"))
        elif kennung == 0x08:
            teile.append("URSACHE=keine" if not inhalt else f"URSACHE={inhalt.hex(' ')}")
        else:
            teile.append(f"{IE_NAME.get(kennung, f'IE_{kennung:02x}')}={inhalt.hex(' ')}")
    return " ".join(teile)


# --- Aufträge (aus Ergoline.tsp, siehe docs/protocol.md Abschnitt 6) -------------------------------

def _auftrag(*nutzdaten: int) -> Rahmen:
    return Rahmen(AUFTRAG, bytes(nutzdaten))


def keepalive() -> Rahmen:
    return _auftrag(0x00, 0x00)


def anmelden() -> Rahmen:
    return _auftrag(0x01, 0x00)


def belegen() -> Rahmen:
    return _auftrag(0x11, 0x00)


def annehmen() -> Rahmen:
    return _auftrag(0x14, 0x00)


def auflegen() -> Rahmen:
    return _auftrag(0x13, 0x00)


def waehlen(nummer: str) -> Rahmen:
    if not nummer or any(c not in "0123456789*#" for c in nummer):
        raise ValueError(f"ungültige Rufnummer {nummer!r}")
    ziffern = nummer.encode("ascii")
    ie = bytes([0x70, len(ziffern) + 1, 0x81]) + ziffern
    return Rahmen(AUFTRAG, bytes([0x19, 0x00, 0x98]) + ie)


# Aufträge, die kein Gespräch auslösen oder beeinflussen (frei für Tests laut CLAUDE.md)
FREIE_AUFTRAEGE = {keepalive().to_bytes(), anmelden().to_bytes()}

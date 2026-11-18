# SPDX-License-Identifier: GPL-3.0-or-later
"""Anruf der ErgoLine D340: Zustände (TAPI LINECALLSTATE), Verlauf, Anrufdatensatz und Plausibilitätsgrenzen."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from . import protocol as p

# LINECALLSTATE (TAPI)
IDLE, OFFERING, ACCEPTED, DIALTONE, DIALING, RINGBACK, BUSY = 0x1, 0x2, 0x4, 0x8, 0x10, 0x20, 0x40
CONNECTED, PROCEEDING, ONHOLD, DISCONNECTED, UNKNOWN = 0x100, 0x200, 0x400, 0x4000, 0x8000
ZUSTANDSNAME = {IDLE: "IDLE", OFFERING: "OFFERING", ACCEPTED: "ACCEPTED", DIALTONE: "DIALTONE", DIALING: "DIALING",
                RINGBACK: "RINGBACK", BUSY: "BUSY", CONNECTED: "CONNECTED", PROCEEDING: "PROCEEDING",
                ONHOLD: "ONHOLD", DISCONNECTED: "DISCONNECTED", UNKNOWN: "UNKNOWN"}
AKTIV = (OFFERING, ACCEPTED, DIALTONE, DIALING, PROCEEDING, RINGBACK, BUSY, CONNECTED, ONHOLD)
# Longest plausible stay in a state without a further message; CONNECTED and ONHOLD have no limit.
GRENZE_S = {OFFERING: 600, ACCEPTED: 60, DIALTONE: 300, DIALING: 600, PROCEEDING: 600, RINGBACK: 600,
            BUSY: 300, DISCONNECTED: 120}


def _iso(t: float | None) -> str | None:
    return None if t is None else dt.datetime.fromtimestamp(t).astimezone().isoformat(timespec="milliseconds")


@dataclass
class Anruf:
    kennung: int
    richtung: str                       # "ein" oder "aus"
    beginn: float
    zustand: int = UNKNOWN
    nummer_roh: str = ""
    verbunden: float | None = None
    getrennt: float | None = None
    ende: float | None = None
    ursache: bytes | None = None        # Inhalt von IE 08 (b"" = keine)
    name: str | None = None             # aus der Rückwärtssuche (gateway/rueckwaerts.py)
    ort: str | None = None
    verlauf: list = field(default_factory=list)

    def ueberfaellig(self, zeit: float) -> bool:
        grenze = GRENZE_S.get(self.zustand)
        seit = self.verlauf[-1][0] if self.verlauf else self.beginn
        return grenze is not None and zeit - seit > grenze

    def setze(self, zustand: int, zeit: float) -> None:
        self.zustand = zustand
        self.verlauf.append((zeit, ZUSTANDSNAME[zustand]))

    def datensatz(self, amtsholung: str = p.AMTSHOLUNG) -> dict:
        ext, nummer = p.extern(self.nummer_roh, amtsholung) if self.nummer_roh else (False, "")
        if self.ursache is None:
            ausloeser = None
        else:   # beobachtet: leere Ursache = eigene Seite hat ausgelöst, sonst Gegenseite (vermutet)
            ausloeser = "eigene_seite" if self.ursache == b"" else "gegenseite"
        if self.richtung == "ein":
            ergebnis = "angenommen" if self.verbunden else "verpasst"
        elif not self.nummer_roh:
            ergebnis = "ohne_wahl"
        else:
            ergebnis = "verbunden" if self.verbunden else "nicht_erreicht"
        return {
            "kennung": self.kennung,
            "ergebnis": ergebnis,
            "richtung": self.richtung,
            "nummer": nummer,
            "extern": ext,
            "nummer_roh": self.nummer_roh,
            "name": self.name,
            "ort": self.ort,
            "beginn": _iso(self.beginn),
            "verbunden": _iso(self.verbunden),
            "ende": _iso(self.ende),
            "angenommen": self.verbunden is not None,
            "dauer_s": round(self.getrennt - self.verbunden, 1) if self.verbunden and self.getrennt else 0.0,
            "ursache": None if self.ursache is None else self.ursache.hex(),
            "ausloeser": ausloeser,
            "verlauf": [z for _, z in self.verlauf],
        }

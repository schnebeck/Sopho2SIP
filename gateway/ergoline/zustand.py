# SPDX-License-Identifier: GPL-3.0-or-later
"""Zustandsautomat für die Anrufe der ErgoLine D340 (nach dem Vorbild des Philips-Treibers).

Die Rahmen tragen keine Anrufkennung; jede Meldung wird – wie im Treiber – dem Anruf zugeordnet, der gerade in einem
passenden Zustand ist. Zustände wie TAPI LINECALLSTATE. Beschreibung: docs/protocol.md, Abschnitt 6a.

Telefon.verarbeite(rahmen, zeit) liefert Ereignisse; endet ein Anruf, enthält das Ereignis "ANRUF_ENDE" den
Anrufdatensatz (dict) für Statistik/Webhook. Telefon.auftraege_*() liefern die zu sendenden Rahmen samt Vorbedingung.
"""
from __future__ import annotations

import datetime as dt
import itertools
from dataclasses import dataclass, field

from . import protocol as p

# LINECALLSTATE (TAPI)
IDLE, OFFERING, ACCEPTED, DIALTONE, DIALING, RINGBACK, BUSY = 0x1, 0x2, 0x4, 0x8, 0x10, 0x20, 0x40
CONNECTED, PROCEEDING, ONHOLD, DISCONNECTED, UNKNOWN = 0x100, 0x200, 0x400, 0x4000, 0x8000
ZUSTANDSNAME = {IDLE: "IDLE", OFFERING: "OFFERING", ACCEPTED: "ACCEPTED", DIALTONE: "DIALTONE", DIALING: "DIALING",
                RINGBACK: "RINGBACK", BUSY: "BUSY", CONNECTED: "CONNECTED", PROCEEDING: "PROCEEDING",
                ONHOLD: "ONHOLD", DISCONNECTED: "DISCONNECTED", UNKNOWN: "UNKNOWN"}
AKTIV = (OFFERING, ACCEPTED, DIALTONE, DIALING, PROCEEDING, RINGBACK, BUSY, CONNECTED, ONHOLD)


class AuftragNichtMoeglich(Exception):
    """Vorbedingung für einen Auftrag nicht erfüllt (wie LINEERR_* im Treiber)."""


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


class Telefon:
    """Anruftabelle und Zustände einer D340 (eine Leitung, höchstens wenige gleichzeitige Anrufe)."""

    def __init__(self, amtsholung: str = p.AMTSHOLUNG) -> None:
        self.amtsholung = amtsholung
        self.anrufe: dict[int, Anruf] = {}
        self.hoerer_ab = False
        self.dtmf = False
        self.bereit = False
        self._kennungen = itertools.count(1)

    # --- Hilfen ---------------------------------------------------------------------------------
    def _suche(self, *zustaende: int) -> Anruf | None:
        """Wie SUCHE_ZUSTAND im Treiber: erster Anruf in einem der Zustände (älteste zuerst)."""
        for a in self.anrufe.values():
            if a.zustand in zustaende:
                return a
        return None

    def _neu(self, richtung: str, zeit: float) -> Anruf:
        a = Anruf(next(self._kennungen), richtung, zeit)
        self.anrufe[a.kennung] = a
        return a

    # --- Meldungen ------------------------------------------------------------------------------
    def verarbeite(self, r: p.Rahmen, zeit: float) -> list[tuple]:
        """Verarbeitet einen Rahmen des Telefons; liefert Ereignisse (name, Anruf|None, Zusatz)."""
        ev: list[tuple] = []
        if r.klasse != p.MELDUNG or not r.daten:
            return ev
        typ = p.MELDUNGSTYP.get(r.typ)
        ies = dict(p.ies(r.daten[2:])) if typ not in ("FACILITY_EIN", "FACILITY_AUS") else {}

        if typ == "READY":
            self.bereit = True
            ev.append(("BEREIT", None, None))
        elif typ == "RINGING":
            a = self._neu("ein", zeit)
            a.nummer_roh = p.rufnummer(ies.get(0x6C, b""))
            a.setze(OFFERING, zeit)
            ev.append(("ANRUF_EIN", a, a.nummer_roh))
        elif typ == "DIALTONE":
            if not self._suche(DIALTONE, DIALING):
                a = self._neu("aus", zeit)
                a.setze(DIALTONE, zeit)
                ev.append(("WAEHLTON", a, None))
        elif typ == "MORE_INFO":
            a = self._suche(DIALTONE, DIALING) or self._neu("aus", zeit)
            if 0x70 in ies:
                a.nummer_roh = p.rufnummer(ies[0x70])
            a.setze(DIALING, zeit)
            ev.append(("WAHL", a, a.nummer_roh))
        elif typ == "PROCEEDING":
            a = self._suche(DIALING)
            if a:
                a.setze(PROCEEDING, zeit)
                a.setze(RINGBACK, zeit)          # Treiber: RESP_PROCEEDING erzeugt 2a und 2b
                ev.append(("RUFT", a, None))
        elif typ == "BUSY":
            a = self._suche(DIALING, PROCEEDING)
            if a:
                a.setze(BUSY, zeit)
                ev.append(("BESETZT", a, None))
        elif typ == "CONNECTED":
            a = self._suche(OFFERING, ACCEPTED, RINGBACK, BUSY, PROCEEDING, DIALING, ONHOLD)
            if a:
                if a.zustand == OFFERING:
                    a.setze(ACCEPTED, zeit)      # Treiber: RESP_CONNECT auf OFFERING → 2f, dann 32
                a.setze(CONNECTED, zeit)
                a.verbunden = a.verbunden or zeit
                ev.append(("VERBUNDEN", a, None))
        elif typ == "HOLD":
            a = self._suche(CONNECTED)
            if a:
                a.setze(ONHOLD, zeit)
                ev.append(("GEHALTEN", a, None))
        elif typ == "UNHOLD":
            a = self._suche(ONHOLD)
            if a:
                a.setze(CONNECTED, zeit)
                ev.append(("ZURUECKGEHOLT", a, None))
        elif typ == "DISCONNECTED":
            a = self._suche(CONNECTED, RINGBACK, BUSY, PROCEEDING, DIALING, ACCEPTED, OFFERING, DIALTONE, ONHOLD)
            if a:
                a.ursache = ies.get(0x08, b"")
                a.getrennt = zeit
                a.setze(DISCONNECTED, zeit)
                ev.append(("GETRENNT", a, a.ursache.hex()))
        elif typ == "RELEASED":
            a = self._suche(DISCONNECTED) or self._suche(*AKTIV)
            if a:
                if a.getrennt is None:
                    a.getrennt = zeit
                if a.ursache is None and 0x08 in ies:
                    a.ursache = ies[0x08]
                a.ende = zeit
                a.setze(IDLE, zeit)
                del self.anrufe[a.kennung]
                ev.append(("ANRUF_ENDE", a, a.datensatz(self.amtsholung)))
        elif typ in ("FACILITY_EIN", "FACILITY_AUS"):
            ein = typ == "FACILITY_EIN"
            merkmal = p.MERKMAL.get(r.daten[2]) if len(r.daten) > 2 else None
            if merkmal == "HOERER":
                self.hoerer_ab = ein
                ev.append(("HOERER_AB" if ein else "HOERER_AUF", None, None))
            elif merkmal == "DTMF":
                self.dtmf = ein
            else:
                ev.append(("MERKMAL", None, (merkmal, ein)))
        else:
            ev.append(("UNBEKANNT", None, r.hex()))
        return ev

    # --- Aufträge mit Vorbedingung (wie die Sendefunktionen des Treibers) ------------------------
    def auftraege_waehlen(self, nummer: str) -> list[p.Rahmen]:
        if self._suche(DISCONNECTED):
            raise AuftragNichtMoeglich("ein Anruf ist noch nicht freigegeben")
        aktiv = [a for a in self.anrufe.values() if a.zustand in AKTIV]
        if not aktiv:
            return [p.belegen(), p.waehlen(nummer)]
        if self._suche(ONHOLD):
            return [p.waehlen(nummer)]           # Rückfrage aus gehaltenem Gespräch (Treiber)
        raise AuftragNichtMoeglich("Leitung belegt")

    def auftraege_ziffern(self, ziffern: str) -> list[p.Rahmen]:
        """Nachwahl/Tonwahl in einem bestehenden Anruf (Treiber TSPI_lineDial 0x100090f0: abgelehnt nur bei
        IDLE/DISCONNECTED, sonst derselbe Rahmen 19 wie bei der Wahl). DTMF zur Gegenseite: vermutet."""
        if self._suche(DISCONNECTED):
            raise AuftragNichtMoeglich("ein Anruf ist noch nicht freigegeben")
        if not [a for a in self.anrufe.values() if a.zustand in AKTIV]:
            raise AuftragNichtMoeglich("kein Anruf für Nachwahl")
        return [p.waehlen(ziffern)]

    def auftraege_wahl_oder_ziffern(self, nummer: str) -> list[p.Rahmen]:
        """Ohne Anruf: Leitung belegen und wählen; mit Anruf (Wählton, Gespräch …): Ziffern nachsenden."""
        if not [a for a in self.anrufe.values() if a.zustand in AKTIV]:
            return self.auftraege_waehlen(nummer)
        return self.auftraege_ziffern(nummer)

    def zustand_kurz(self) -> dict:
        """Kurzzustand für Anzeigen (Portal): erster laufender Anruf oder Ruhe."""
        namen = {OFFERING: "klingelt", ACCEPTED: "verbunden", DIALTONE: "waehlton", DIALING: "waehlt",
                 PROCEEDING: "ruft", RINGBACK: "ruft", BUSY: "besetzt", CONNECTED: "verbunden",
                 ONHOLD: "gehalten", DISCONNECTED: "getrennt"}
        for a in self.anrufe.values():
            ext, nummer = p.extern(a.nummer_roh, self.amtsholung) if a.nummer_roh else (False, "")
            return {"zustand": namen.get(a.zustand, "unbekannt"), "richtung": a.richtung, "nummer": nummer,
                    "extern": ext, "name": a.name, "ort": a.ort, "beginn": a.beginn, "verbunden": a.verbunden}
        return {"zustand": "ruhe"}

    def auftraege_annehmen(self) -> list[p.Rahmen]:
        klingelt = [a for a in self.anrufe.values() if a.zustand == OFFERING]
        if len(self.anrufe) == 1 and klingelt:
            return [p.annehmen()]
        raise AuftragNichtMoeglich("kein einzelner klingelnder Anruf (Anklopfen noch nicht umgesetzt)")

    def auftraege_auflegen(self) -> list[p.Rahmen]:
        aktiv = [a for a in self.anrufe.values() if a.zustand in AKTIV]
        if len(aktiv) == 1:
            return [p.auflegen()]
        if not aktiv:
            raise AuftragNichtMoeglich("kein Gespräch")
        raise AuftragNichtMoeglich("mehrere Gespräche (Reconnect noch nicht umgesetzt)")

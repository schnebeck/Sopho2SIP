# SPDX-License-Identifier: GPL-3.0-or-later
"""Zustandsautomat für die Anrufe der ErgoLine D340 (nach dem Vorbild des Philips-Treibers).

Die Rahmen tragen keine Anrufkennung; jede Meldung wird – wie im Treiber – dem Anruf zugeordnet, der gerade in einem
passenden Zustand ist. Welche Zustände passen und wohin sie führen, steht in der Übergangstabelle (uebergaenge.py);
nicht vorgesehene Kombinationen melden UNERWARTET, verletzte Invarianten INVARIANTE. Zustände wie TAPI
LINECALLSTATE. Beschreibung: docs/protocol.md, Abschnitt 6a.

Telefon.verarbeite(rahmen, zeit) liefert Ereignisse; endet ein Anruf, enthält das Ereignis "ANRUF_ENDE" den
Anrufdatensatz (dict) für Statistik/Webhook. Telefon.aufraeumen(zeit) verwirft Anrufe, die länger als ihre
Plausibilitätsgrenze (anruf.GRENZE_S) ohne weitere Meldung in einem Zustand stehen ("ANRUF_VERWORFEN"). Telefon.auftraege_*() liefern die zu sendenden Rahmen samt Vorbedingung.
"""
from __future__ import annotations

import itertools

from . import protocol as p
from .anruf import (ACCEPTED, AKTIV, BUSY, CONNECTED, DIALING, DIALTONE, DISCONNECTED, OFFERING, ONHOLD,
                    PROCEEDING, RINGBACK, ZUSTANDSNAME, Anruf)
from .uebergaenge import REGELN, verletzungen


class AuftragNichtMoeglich(Exception):
    """Vorbedingung für einen Auftrag nicht erfüllt (wie LINEERR_* im Treiber)."""


_VORRANG = (CONNECTED, ACCEPTED, BUSY, RINGBACK, PROCEEDING, DIALING, DIALTONE, OFFERING, ONHOLD, DISCONNECTED)
_ANZEIGE = {OFFERING: "klingelt", ACCEPTED: "verbunden", DIALTONE: "waehlton", DIALING: "waehlt",
            PROCEEDING: "ruft", RINGBACK: "ruft", BUSY: "besetzt", CONNECTED: "verbunden",
            ONHOLD: "gehalten", DISCONNECTED: "getrennt"}


class Telefon:
    """Anruftabelle und Zustände einer D340 (eine Leitung, höchstens wenige gleichzeitige Anrufe)."""

    def __init__(self, amtsholung: str = p.AMTSHOLUNG) -> None:
        self.amtsholung = amtsholung
        self.anrufe: dict[int, Anruf] = {}
        self.hoerer_ab = False
        self.dtmf = False
        self.x_eingang = False              # Merkmal 4f „X-Eingang statt Mikrofon“ (gilt je Gespräch)
        self.bereit = False
        self._kennungen = itertools.count(1)
        self._verletzt: set[str] = set()

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
    def aufraeumen(self, zeit: float) -> list[tuple]:
        """Verwirft überfällige Anrufe; das Ereignis trägt den Datensatz, ist aber kein Anrufende."""
        ev = []
        for a in [a for a in self.anrufe.values() if a.ueberfaellig(zeit)]:
            del self.anrufe[a.kennung]
            ev.append(("ANRUF_VERWORFEN", a, a.datensatz(self.amtsholung)))
        return ev

    def verarbeite(self, r: p.Rahmen, zeit: float) -> list[tuple]:
        """Verarbeitet einen Rahmen des Telefons; liefert Ereignisse (name, Anruf|None, Zusatz)."""
        if r.klasse != p.MELDUNG or not r.daten:
            return []
        ev = self.aufraeumen(zeit)
        typ = p.MELDUNGSTYP.get(r.typ)
        ies = dict(p.ies(r.daten[2:])) if typ not in ("FACILITY_EIN", "FACILITY_AUS", "FACILITY_ABGELEHNT") else {}

        if typ in REGELN:
            self._anwenden(typ, REGELN[typ], r, ies, zeit, ev)
            ev += self._pruefe_invarianten()
        elif typ == "READY":
            self.bereit = True
            ev.append(("BEREIT", None, None))
        elif typ in ("FACILITY_EIN", "FACILITY_AUS"):
            ein = typ == "FACILITY_EIN"
            merkmal = p.MERKMAL.get(r.daten[2]) if len(r.daten) > 2 else None
            if merkmal == "HOERER":
                self.hoerer_ab = ein
                ev.append(("HOERER_AB" if ein else "HOERER_AUF", None, None))
            elif merkmal == "DTMF":
                self.dtmf = ein
            elif merkmal == "X_EINGANG":
                self.x_eingang = ein
                ev.append(("X_EINGANG", None, ein))
            else:
                ev.append(("MERKMAL", None, (merkmal or f"{r.daten[2]:02x}" if len(r.daten) > 2 else None, ein)))
        elif typ == "FACILITY_ABGELEHNT":
            kennung = r.daten[2] if len(r.daten) > 2 else None
            ev.append(("MERKMAL_ABGELEHNT", None, p.MERKMAL.get(kennung, f"{kennung:02x}" if kennung is not None else "")))
        else:
            ev.append(("UNBEKANNT", None, r.hex()))
        return ev

    def _anwenden(self, typ: str, regel, r: p.Rahmen, ies: dict, zeit: float, ev: list) -> None:
        """Applies one rule of the transition table (uebergaenge.REGELN)."""
        a, nach = None, ()
        for von, nach in regel.uebergaenge:
            a = self._suche(von)
            if a:
                break
        if a is None:
            laufend = self._suche(*AKTIV) if regel.im_anruf else None
            if laufend:
                ev.append(self._im_anruf(laufend, r, ies))
                return
            if regel.neu is None:
                zustaende = ", ".join(ZUSTANDSNAME[x.zustand] for x in self.anrufe.values()) or "keine Anrufe"
                ev.append(("UNERWARTET", None, f"{typ} ohne passenden Anruf ({zustaende}): {r.hex()}"))
                return
            a, nach = self._neu(regel.neu, zeit), regel.start
        elif not nach:
            return                              # known repetition
        for z in nach:
            a.setze(z, zeit)
        ev.append(self._folgen(regel.ereignis, a, ies, zeit))

    def _im_anruf(self, a: Anruf, r: p.Rahmen, ies: dict) -> tuple:
        """MORE_INFO within a call: IE 70 = digits dialled afterwards, IE 6c = party actually reached."""
        if 0x70 in ies:
            return ("NACHWAHL", a, p.rufnummer(ies[0x70]))
        if 0x6C in ies:
            return ("GEGENSTELLE", a, p.rufnummer(ies[0x6C]))
        return ("UNERWARTET", a, r.hex())

    def _folgen(self, ereignis: str, a: Anruf, ies: dict, zeit: float) -> tuple:
        """Call data carried by the message; returns the event of the transition."""
        if ereignis == "ANRUF_EIN":
            a.nummer_roh = p.rufnummer(ies.get(0x6C, b""))
            return (ereignis, a, a.nummer_roh)
        if ereignis == "WAHL":
            if 0x70 in ies:
                a.nummer_roh = p.rufnummer(ies[0x70])
            return (ereignis, a, a.nummer_roh)
        if ereignis == "VERBUNDEN":
            a.verbunden = a.verbunden or zeit
        elif ereignis == "GETRENNT":
            a.ursache = ies.get(0x08, b"")
            a.getrennt = zeit
            return (ereignis, a, a.ursache.hex())
        elif ereignis == "ANRUF_ENDE":
            if a.getrennt is None:
                a.getrennt = zeit
            if a.ursache is None and 0x08 in ies:
                a.ursache = ies[0x08]
            a.ende = zeit
            del self.anrufe[a.kennung]
            return (ereignis, a, a.datensatz(self.amtsholung))
        return (ereignis, a, None)

    def _pruefe_invarianten(self) -> list[tuple]:
        """Reports each violated invariant once, when it appears."""
        jetzt = verletzungen([a.zustand for a in self.anrufe.values()])
        neu, self._verletzt = jetzt - self._verletzt, jetzt
        return [("INVARIANTE", None, text) for text in sorted(neu)]

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
        """Kurzzustand für Anzeigen (Portal): der Anruf, um den es gerade geht, oder Ruhe.
        Vorrang hat das Gespräch, dann der abgehende Ruf, dann ein klingelnder, zuletzt ein gehaltener Anruf."""
        if not self.anrufe:
            return {"zustand": "ruhe"}
        a = min(self.anrufe.values(), key=lambda a: (_VORRANG.index(a.zustand) if a.zustand in _VORRANG
                                                     else len(_VORRANG), a.kennung))
        ext, nummer = p.extern(a.nummer_roh, self.amtsholung) if a.nummer_roh else (False, "")
        return {"zustand": _ANZEIGE.get(a.zustand, "unbekannt"), "richtung": a.richtung, "nummer": nummer,
                "extern": ext, "name": a.name, "ort": a.ort, "beginn": a.beginn, "verbunden": a.verbunden,
                "weitere": len(self.anrufe) - 1}

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

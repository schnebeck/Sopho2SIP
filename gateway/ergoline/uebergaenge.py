# SPDX-License-Identifier: GPL-3.0-or-later
"""Transition table of the call state machine (docs/protocol.md, section 6a).

Each call-related message has one rule. Its transitions are searched in the listed order: the oldest call in the
first occupied source state takes the message and passes through the target states. A message whose rule finds no
call either opens a new call (``neu``), belongs to any running call (``im_anruf``) or is reported as UNERWARTET.
An empty target tuple is a known repetition: the call keeps its state and no event is raised.

Source of each entry: T = driver, B = observed in a log, V = assumed (no log yet, e.g. call waiting, hold).
"""
from __future__ import annotations

from dataclasses import dataclass

from .anruf import (ACCEPTED, BUSY, CONNECTED, DIALING, DIALTONE, DISCONNECTED, IDLE, OFFERING, ONHOLD,
                    PROCEEDING, RINGBACK)

GESPRAECH = (ACCEPTED, CONNECTED)
AUFBAU = (DIALTONE, DIALING, PROCEEDING, RINGBACK, BUSY)


@dataclass(frozen=True)
class Regel:
    ereignis: str
    uebergaenge: tuple = ()     # ((source state, (target states ...)), ...) in search order
    neu: str | None = None      # direction of the call opened when no transition applies
    start: tuple = ()           # target states of that new call
    im_anruf: bool = False      # without a transition: information for the running call (MORE_INFO)


def _alle(quellen: tuple, ziel: int) -> tuple:
    return tuple((q, (ziel,)) for q in quellen)


REGELN = {
    # T: offering opens a call; several may ring at once (call waiting, V)
    "RINGING": Regel("ANRUF_EIN", neu="ein", start=(OFFERING,)),
    # T: dial tone opens a call; B: repeated within the same call (serial_20260930_163534.log)
    "DIALTONE": Regel("WAEHLTON", ((DIALTONE, ()), (DIALING, ())), neu="aus", start=(DIALTONE,)),
    # T: 29 → DIALING; B: seizing by the PC reports no dial tone, MORE_INFO opens the call;
    # B: after CONNECTED, MORE_INFO with IE 6c names the party reached (2026-11 logs)
    "MORE_INFO": Regel("WAHL", ((DIALTONE, (DIALING,)), (DIALING, (DIALING,))), neu="aus", start=(DIALING,),
                       im_anruf=True),
    # T: RESP_PROCEEDING raises 2a and 2b
    "PROCEEDING": Regel("RUFT", ((DIALING, (PROCEEDING, RINGBACK)),)),
    # T: DIALING/PROCEEDING → BUSY
    "BUSY": Regel("BESETZT", _alle((DIALING, PROCEEDING), BUSY)),
    # T: OFFERING → 2f, 32; RINGBACK/BUSY → CONNECTED; B: DIALING → CONNECTED for internal calls (2026-11-16);
    # V: ONHOLD → CONNECTED when the held call is taken back by CONNECTED instead of UNHOLD
    "CONNECTED": Regel("VERBUNDEN", ((OFFERING, (ACCEPTED, CONNECTED)),)
                       + _alle((ACCEPTED, RINGBACK, BUSY, PROCEEDING, DIALING, ONHOLD), CONNECTED)),
    # T: CONNECTED → ONHOLD (2c); V: UNHOLD
    "HOLD": Regel("GEHALTEN", _alle((CONNECTED,), ONHOLD)),
    "UNHOLD": Regel("ZURUECKGEHOLT", _alle((ONHOLD,), CONNECTED)),
    # T: every state → DISCONNECTED; the conversation goes first, then calls being set up, the held one last
    "DISCONNECTED": Regel("GETRENNT", _alle(GESPRAECH[::-1] + AUFBAU[::-1] + (OFFERING, ONHOLD), DISCONNECTED)),
    # T: DISCONNECTED → IDLE; B: OFFERING and DIALTONE are released without DISCONNECTED (missed call, no digits);
    # V: a waiting call that gives up is released before the conversation
    "RELEASED": Regel("ANRUF_ENDE", _alle((DISCONNECTED, OFFERING) + AUFBAU + (ONHOLD,) + GESPRAECH, IDLE)),
}

# Messages without effect on the call table (meaning partly unknown); they are reported as UNBEKANNT.
OHNE_REGEL = ("IDLE", "CAMPONBUSY", "ERROR", "ANKLOPFEN_EIN", "ANKLOPFEN_AUS", "USERTOUSER", "NOHOLD")


def verletzungen(zustaende: list[int]) -> set[str]:
    """Invariants of a D340 (one line): at most one conversation, one call being set up, one being released."""
    gruppen = {"Gespräch": GESPRAECH, "Verbindungsaufbau": AUFBAU, "Auslösung": (DISCONNECTED,)}
    return {f"mehr als ein Anruf im Zustand {name}" for name, zs in gruppen.items()
            if sum(z in zs for z in zustaende) > 1}

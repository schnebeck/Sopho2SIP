# SPDX-License-Identifier: GPL-3.0-or-later
"""Rückwärtssuche für externe Rufnummern (Name/Ort zum Anrufer) mit Zwischenspeicher.

Quellen (am Pi geprüft 2026-10-01), der Reihe nach:
  11880.com/rueckwaertssuche/<nr>   Treffer = JSON-LD-Objekt mit name und telephone, dessen Ziffern zur Nummer passen
  dasoertliche.de/rueckwaertssuche  Treffer = Weiterleitung auf form_name=detail; Name/Ort aus dem Seitentitel
                                    (ohne Treffer bleibt die Suche stehen, der Titel enthält dann einen Ort per Geo-IP!)
Datenschutz: Jede gesuchte Nummer geht an diese Dienste. Nur externe Nummern, je Nummer höchstens einmal in 30 Tagen
(ohne Treffer: 7 Tage). Zwischenspeicher: ~/.local/share/sopho2sip/rueckwaerts.json
"""
from __future__ import annotations

import html
import json
import pathlib
import re
import threading
import time
import urllib.parse
import urllib.request

SPEICHER = pathlib.Path.home() / ".local" / "share" / "sopho2sip" / "rueckwaerts.json"
GUELTIG_S, GUELTIG_OHNE_S = 30 * 86400, 7 * 86400
AGENT = "Mozilla/5.0 (X11; Linux aarch64; rv:128.0) Gecko/20100101 Firefox/128.0"
LD = re.compile(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.S)


def ziffern(s: str) -> str:
    return re.sub(r"\D", "", s.replace("+49", "0"))


def _hole(url: str, timeout: float) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept-Language": "de-DE,de;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read(1_000_000).decode("utf-8", errors="replace")


def aus_11880(seite: str, nummer: str) -> dict | None:
    for block in LD.findall(seite):
        try:
            daten = json.loads(block)
        except json.JSONDecodeError:
            continue
        for o in daten if isinstance(daten, list) else daten.get("@graph", [daten]):
            if not isinstance(o, dict) or not o.get("name"):
                continue
            tel = o.get("telephone") or []
            tel = [tel] if isinstance(tel, str) else tel
            if any(ziffern(t) == nummer for t in tel):
                adr = o.get("address") or {}
                ort = adr.get("addressLocality") if isinstance(adr, dict) else None
                return {"name": html.unescape(o["name"]).strip(), "ort": ort, "quelle": "11880"}
    return None


def aus_dasoertliche(url: str, seite: str) -> dict | None:
    if "form_name=detail" not in url:
        return None
    m = re.search(r"<title>\s*(.*?)\s+in\s+(.*?)\s*(?:&rArr;|⇒)", seite, re.S)
    if not m:
        return None
    return {"name": html.unescape(m.group(1)).strip(), "ort": html.unescape(m.group(2)).strip(),
            "quelle": "dasoertliche"}


def suche_online(nummer: str, timeout: float = 6.0) -> dict | None:
    """Fragt die Quellen nacheinander; None = kein Eintrag. Netzfehler werden als OSError weitergereicht."""
    fehler = None
    try:
        _, seite = _hole(f"https://www.11880.com/rueckwaertssuche/{nummer}", timeout)
        if treffer := aus_11880(seite, nummer):
            return treffer
    except OSError as e:
        fehler = e
    try:
        url, seite = _hole("https://www.dasoertliche.de/rueckwaertssuche/?ph=" + urllib.parse.quote(nummer), timeout)
        return aus_dasoertliche(url, seite)
    except OSError as e:
        raise fehler or e


class Rueckwaertssuche:
    def __init__(self, pfad: pathlib.Path = SPEICHER, suche=suche_online, echo=print) -> None:
        self.pfad, self._suche, self.echo = pfad, suche, echo
        self._lock = threading.Lock()
        try:
            self._speicher = json.loads(pfad.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            self._speicher = {}

    @staticmethod
    def suchbar(nummer: str) -> bool:
        """Nur externe Nummern (mit 0 beginnend, mindestens 6 Ziffern), keine Nebenstellen/anonym."""
        return nummer.isdigit() and nummer.startswith("0") and len(nummer) >= 6

    def bekannt(self, nummer: str) -> dict | None:
        """Nur aus dem Zwischenspeicher (für die Anrufliste, ohne Netz)."""
        with self._lock:
            e = self._speicher.get(nummer)
        return e if e and e.get("name") else None

    def frage(self, nummer: str) -> dict | None:
        """Zwischenspeicher, sonst online (blockiert bis ~12 s; im Hintergrund aufrufen)."""
        if not self.suchbar(nummer):
            return None
        with self._lock:
            e = self._speicher.get(nummer)
        if e and time.time() - e["zeit"] < (GUELTIG_S if e.get("name") else GUELTIG_OHNE_S):
            return e if e.get("name") else None
        try:
            treffer = self._suche(nummer)
        except OSError as ex:
            self.echo(f"  RÜCKWÄRTS    {nummer}: nicht erreichbar ({ex})")
            return None
        e = {**(treffer or {"name": None}), "zeit": time.time()}
        with self._lock:
            self._speicher[nummer] = e
            self.pfad.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.pfad.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._speicher, ensure_ascii=False, indent=0))
            tmp.replace(self.pfad)
        return treffer

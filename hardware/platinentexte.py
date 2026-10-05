# SPDX-License-Identifier: GPL-3.0-or-later
"""Beschriftung einer Leiterplatte als Daten (beschriftung.json) mit Rückführung von Handänderungen aus KiCad.

beschriftung.json:
  "texte":    Platinentexte (gr_text), je Eintrag "id", "text" und Attribute; Lage in Konstruktionskoordinaten
  "bauteile": Abweichungen der Bauteiltexte vom Standard: {Referenz: {Feld: Attribute}}; Feld = "Reference",
              "Value" oder "Text:<Inhalt>" (eigene Texte des Footprints); Lage relativ zum Footprint
Attribute: x, y, winkel, groesse [b, h], dicke, lage, sichtbar, ausrichtung [waagerecht, senkrecht], gespiegelt,
fett, kursiv, aufrecht, ausgespart.

Ablauf im Layout-Generator: uebernehmen() vergleicht die Platine mit dem Stand (.beschriftung_stand.json, so wie
der Generator sie zuletzt geschrieben hat) und trägt jede Abweichung in beschriftung.json ein – geänderte, neue
und gelöschte Platinentexte, geänderte Bauteiltexte. anwenden() setzt danach alles aus beschriftung.json;
stand() hält das Ergebnis fest. Inhalte von Referenz und Wert kommen aus dem Schaltplan und werden nie übernommen.
"""
from __future__ import annotations

import json
import pathlib
import uuid

import pcbnew

_NS = uuid.UUID("0b7d6a8e-6c55-4f0e-9d0a-3b1c2f4e5a61")      # Namensraum für die Kennungen der Platinentexte
MM, ZU_MM = pcbnew.FromMM, pcbnew.ToMM
WAAGERECHT = {pcbnew.GR_TEXT_H_ALIGN_LEFT: "links", pcbnew.GR_TEXT_H_ALIGN_CENTER: "mitte",
              pcbnew.GR_TEXT_H_ALIGN_RIGHT: "rechts"}
SENKRECHT = {pcbnew.GR_TEXT_V_ALIGN_TOP: "oben", pcbnew.GR_TEXT_V_ALIGN_CENTER: "mitte",
             pcbnew.GR_TEXT_V_ALIGN_BOTTOM: "unten"}


def kennung(text_id: str) -> str:
    return str(uuid.uuid5(_NS, f"platinentext:{text_id}"))


def _r(v: float) -> float:
    return round(v, 3)


def _attribute(t, board, versatz: tuple[float, float] | None) -> dict:
    """versatz=None: Bauteiltext (Lage relativ zum Footprint); sonst Platinentext in Konstruktionskoordinaten."""
    p = t.GetFPRelativePosition() if versatz is None else t.GetPosition()
    dx, dy = versatz or (0.0, 0.0)
    g = t.GetTextSize()
    return {"x": _r(ZU_MM(p.x) - dx), "y": _r(ZU_MM(p.y) - dy), "winkel": _r(t.GetTextAngleDegrees()),
            "groesse": [_r(ZU_MM(g.x)), _r(ZU_MM(g.y))], "dicke": _r(ZU_MM(t.GetTextThickness())),
            "lage": board.GetLayerName(t.GetLayer()), "sichtbar": bool(t.IsVisible()),
            "ausrichtung": [WAAGERECHT[t.GetHorizJustify()], SENKRECHT[t.GetVertJustify()]],
            "gespiegelt": bool(t.IsMirrored()), "fett": bool(t.IsBold()), "kursiv": bool(t.IsItalic()),
            "aufrecht": bool(t.IsKeepUpright()), "ausgespart": bool(t.IsKnockout())}


def _setzen(t, a: dict, board, versatz: tuple[float, float] | None) -> None:
    t.SetLayer(board.GetLayerID(a["lage"]))
    t.SetTextSize(pcbnew.VECTOR2I(MM(a["groesse"][0]), MM(a["groesse"][1])))
    t.SetTextThickness(MM(a["dicke"]))
    t.SetHorizJustify({v: k for k, v in WAAGERECHT.items()}[a["ausrichtung"][0]])
    t.SetVertJustify({v: k for k, v in SENKRECHT.items()}[a["ausrichtung"][1]])
    t.SetMirrored(a["gespiegelt"]); t.SetBold(a["fett"]); t.SetItalic(a["kursiv"])
    t.SetKeepUpright(a["aufrecht"]); t.SetIsKnockout(a["ausgespart"]); t.SetVisible(a["sichtbar"])
    t.SetTextAngleDegrees(a["winkel"])
    if versatz is None:
        t.SetFPRelativePosition(pcbnew.VECTOR2I(MM(a["x"]), MM(a["y"])))
    else:
        t.SetPosition(pcbnew.VECTOR2I(MM(a["x"] + versatz[0]), MM(a["y"] + versatz[1])))


def _bauteiltexte(fp):
    """(Feld, Textobjekt) eines Footprints; gleiche eigene Texte werden durchnummeriert."""
    yield "Reference", fp.Reference()
    yield "Value", fp.Value()
    zaehler: dict[str, int] = {}
    for g in fp.GraphicalItems():
        if g.GetClass() == "PCB_TEXT":
            n = zaehler[g.GetText()] = zaehler.get(g.GetText(), 0) + 1
            yield f"Text:{g.GetText()}" + (f"#{n}" if n > 1 else ""), g


def lesen(board, versatz: tuple[float, float]) -> dict:
    """Ist-Zustand aller Beschriftungen: Platinentexte nach UUID, Bauteiltexte nach Referenz und Feld."""
    texte = {d.m_Uuid.AsString(): {"text": d.GetText(), **_attribute(d, board, versatz)}
             for d in board.GetDrawings() if d.GetClass() == "PCB_TEXT"}
    bauteile = {fp.GetReference(): {feld: _attribute(t, board, None) for feld, t in _bauteiltexte(fp)}
                for fp in board.GetFootprints()}
    return {"texte": texte, "bauteile": bauteile}


def anwenden(board, daten: dict, versatz: tuple[float, float] = (0.0, 0.0)) -> None:
    """Platinentexte neu anlegen (vorhandene entfernen), Abweichungen der Bauteiltexte setzen."""
    for d in [d for d in board.GetDrawings() if d.GetClass() == "PCB_TEXT"]:
        board.Remove(d)
    for e in daten["texte"]:
        t = pcbnew.PCB_TEXT(board)
        t.SetText(e["text"])
        _setzen(t, e, board, versatz)
        t.SetUuid(pcbnew.KIID(kennung(e["id"])))
        board.Add(t)
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    for ref, felder in daten["bauteile"].items():
        if ref in fps:
            for feld, t in _bauteiltexte(fps[ref]):
                if feld in felder:
                    _setzen(t, felder[feld], board, None)


def uebernehmen(board, daten: dict, stand: dict | None, versatz: tuple[float, float]) -> list[str]:
    """Abweichungen der Platine vom Stand in daten eintragen; liefert Meldungen. Ohne Stand: nichts übernehmen."""
    if stand is None:
        return []
    ist, meldungen = lesen(board, versatz), []
    eintraege = {kennung(e["id"]): e for e in daten["texte"]}
    for u, a in ist["texte"].items():
        if stand["texte"].get(u) == a:
            continue
        if u in eintraege:
            eintraege[u].update(a)
            meldungen.append(f"Platinentext „{a['text']}“ geändert")
        else:
            nummern = [int(e["id"][4:]) for e in daten["texte"] if e["id"].startswith("hand") and e["id"][4:].isdigit()]
            daten["texte"].append({"id": f"hand{max(nummern, default=0) + 1}", **a})
            meldungen.append(f"Platinentext „{a['text']}“ neu")
    for u in set(stand["texte"]) - set(ist["texte"]):
        if u in eintraege:
            daten["texte"].remove(eintraege[u])
            meldungen.append(f"Platinentext „{stand['texte'][u]['text']}“ gelöscht")
    for ref, felder in ist["bauteile"].items():
        for feld, a in felder.items():
            alt = stand["bauteile"].get(ref, {}).get(feld)
            if alt is not None and a != alt:
                daten["bauteile"].setdefault(ref, {})[feld] = a
                unterschiede = ", ".join(k for k in a if a[k] != alt[k])
                meldungen.append(f"{ref} {feld}: {unterschiede}")
    return meldungen


def laden(pfad: pathlib.Path) -> dict:
    return json.loads(pfad.read_text(encoding="utf-8"))


def speichern(pfad: pathlib.Path, daten) -> None:
    pfad.write_text(json.dumps(daten, indent=1, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")

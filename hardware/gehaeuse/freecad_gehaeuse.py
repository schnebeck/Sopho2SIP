# SPDX-License-Identifier: GPL-3.0-or-later
"""Gehäuse für den CM4-Träger (FDM-Druck): Unterschale, Deckel, Lichtleiter. Läuft in FreeCAD (freecadcmd):

  flatpak run --command=freecadcmd org.freecad.FreeCAD $PWD/hardware/gehaeuse/freecad_gehaeuse.py

Eingaben: masse.json und platine_bestueckt.step (beide aus erzeuge_masse.py). Ausgaben in diesem Ordner:
gehaeuse.step (Einbaulage), gehaeuse.FCStd, druck/*.stl (Drucklage, ohne Stützmaterial), pruefung.txt
(Kollisionsprüfung gegen die bestückte Platine).

Koordinaten: x nach rechts, y nach hinten (FreeCAD-Rahmen des Platinen-STEP), z = 0 Platinenunterseite.
Die Funktionen nehmen Platinenmaße wie in KiCad (y nach vorn) und setzen y → −y um.
Die Leiterplatte liegt auf Stützen der Unterschale; vier Schrauben M2.5×10 von unten durch Unterschale und
Platine (H1–H4) in Gewindeeinsätze der Deckelsäulen klemmen alles zusammen.
"""
import json
import os

import FreeCAD
import Import
import MeshPart
import Part

V = FreeCAD.Vector
HIER = os.path.dirname(os.path.abspath(__file__))
M = json.load(open(os.path.join(HIER, "masse.json"), encoding="utf-8"))
BT = M["bauteile"]
B, T, D = M["platine"]["breite"], M["platine"]["tiefe"], M["platine"]["dicke"]
SCHRIFT = "/usr/share/fonts/dejavu/"

# Wandaufbau (mm)
SPALT, WAND, BODEN, DECKE = 0.4, 2.4, 2.0, 2.0
R_AUSSEN = 3.0
Z_TEIL = D                       # Trennebene = Platinenoberseite
Z_BODEN = -3.5                   # Oberkante Boden (tiefster Lötpin −1,81)
Z_UNTEN = Z_BODEN - BODEN
Z_DECKE = 17.6                   # Unterkante Deckel (höchste Buchse 16,55)
Z_OBEN = Z_DECKE + DECKE
LIPPE_H, LIPPE_B, LIPPE_LUFT = 2.0, 1.2, 0.15
X0, X1 = -SPALT - WAND, B + SPALT + WAND
Y0, Y1 = -SPALT - WAND, T + SPALT + WAND      # Platinenmaß (y nach vorn)

# Schrauben und Einsätze (M2.5)
SAEULE_D, EINSATZ_D, EINSATZ_T = 7.5, 3.6, 6.5     # Gewindeeinsatz M2.5 × 5,7 (z. B. Ruthex), Loch 3,6
DURCHGANG_D, KOPF_D, KOPF_T = 2.9, 5.2, 2.6         # Zylinderkopf ISO 4762 M2.5: Ø4,5 × 2,5

# Bedienelemente
TASTE_SPIEL = 0.35               # Stößel über Tasterkappe (TL3342: 3,13 über z = 0)
TASTE_OBEN = 3.13
ZUNGE_B, ZUNGE_L, ZUNGE_D, SCHLITZ = 8.0, 16.0, 1.2, 0.8
STOESSEL_D = 4.0
LED_OBEN = 2.70
LL_D, LL_BOHRUNG, LL_KOPF_D, LL_KOPF_T, ROHR_D = 3.0, 3.4, 4.2, 0.8, 5.0
LL_SPIEL = 0.7                   # Lichtleiter-Ende über LED

# Lüfter 30 × 30 × 7, Lochabstand 24, über dem SoC des CM4 (Mitte aus dem Platinen-STEP)
LUEFTER = (33.0, 49.0)
LUEFTER_A, LUEFTER_H, LUEFTER_LOCH = 30.0, 7.0, 24.0

LEDS = [("D11", "PWR"), ("D10", "ACT"), ("D1", "TEL"), ("D2", "GESPR"), ("D3", "STATUS")]
TASTER = [("SW1", "TASTE"), ("SW2", "KONFIG"), ("SW3", "EIN/AUS")]
BUCHSEN_HINTEN = [("J10", "5V"), ("J14", "LAN"), ("J3", "D340 PC"), ("J2", "D340 AUDIO")]
# Gehäuse der RJ-Buchsen an der Stirnseite: x von–bis, Oberkante (aus dem Platinen-STEP). Der Footprint-Ursprung
# liegt nicht in der Buchsenmitte; Ausschnitt und Beschriftung richten sich nach dem Buchsengehäuse.
RJ_BUCHSEN = {"J14": (24.77, 41.07, 15.42), "J3": (56.29, 68.75, 16.55), "J2": (90.80, 105.20, 16.30)}


def ausschnitt_mitte(ref):
    """x der Mitte des Wandausschnitts einer hinteren Buchse (USB-C: Footprint-Mitte = Buchsenmitte)."""
    if ref in RJ_BUCHSEN:
        xa, xb, _ = RJ_BUCHSEN[ref]
        return (xa + xb) / 2
    return pos(ref)[0]


def pos(ref):
    return BT[ref]["x"], BT[ref]["y"]


def rr(x0, x1, y0, y1, z0, z1, r=0.0):
    """Quader in Platinenmaßen (y nach vorn), senkrechte Kanten mit Radius r."""
    k = Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, -y1, z0))
    if r > 0:
        k = k.makeFillet(r, [e for e in k.Edges if abs(e.Vertexes[0].Point.z - e.Vertexes[1].Point.z) > 1e-6])
    return k


def zyl(x, y, d, z0, z1):
    return Part.makeCylinder(d / 2, z1 - z0, V(x, -y, z0))


def langloch_y(x, z, b, h, y0, y1):
    """Langloch in einer Wand quer zu y: Breite b (x), Höhe h (z), Enden rund."""
    r = min(b, h) / 2
    if b >= h:
        k = Part.makeBox(b - h, y1 - y0, h, V(x - (b - h) / 2, -y1, z - h / 2))
        for dx in (-(b - h) / 2, (b - h) / 2):
            k = k.fuse(Part.makeCylinder(r, y1 - y0, V(x + dx, -y0, z), V(0, -1, 0)))
    else:
        k = Part.makeBox(b, y1 - y0, h - b, V(x - b / 2, -y1, z - (h - b) / 2))
        for dz in (-(h - b) / 2, (h - b) / 2):
            k = k.fuse(Part.makeCylinder(r, y1 - y0, V(x, -y0, z + dz), V(0, -1, 0)))
    return k.removeSplitter()


def schrift(text, h, datei="DejaVuSansCondensed-Bold.ttf"):
    """Textfläche in der XY-Ebene, Mittelpunkt im Ursprung."""
    zeichen = Part.makeWireString(text, SCHRIFT, datei, h, 0)
    flaechen = [Part.makeFace(w, "Part::FaceMakerBullseye") for w in zeichen if w]
    f = Part.makeCompound(flaechen)
    bb = f.BoundBox
    f.translate(V(-(bb.XMin + bb.XMax) / 2, -(bb.YMin + bb.YMax) / 2, 0))
    return f


def pruefe_beschriftung():
    """Tasterbeschriftungen dürfen sich nicht berühren (mindestens 1 mm Luft)."""
    breiten = [(pos(sw)[0], schrift(t, 1.9).BoundBox.XLength) for sw, t in TASTER]
    for (xa, ba), (xb, bb) in zip(breiten, breiten[1:]):
        assert xb - xa - (ba + bb) / 2 >= 1.0, f"Tasterbeschriftung zu breit: {breiten}"


def gravur_oben(text, h, x, y, tiefe=0.4, drehung=0):
    f = schrift(text, h)
    f.rotate(V(0, 0, 0), V(0, 0, 1), drehung)
    f.translate(V(x, -y, Z_OBEN - tiefe))
    return f.extrude(V(0, 0, tiefe + 0.1))


def gravur_wand(text, h, x, z, hinten, tiefe=0.4):
    """Schrift auf der Rück- (hinten=True) oder Vorderwand, von außen lesbar."""
    f = schrift(text, h)
    f.rotate(V(0, 0, 0), V(1, 0, 0), 90)               # (u, v) → (u, 0, v)
    if hinten:
        f.rotate(V(0, 0, 0), V(0, 0, 1), 180)          # von hinten gesehen: u → −x
        f.translate(V(x, -Y0 - tiefe, z))
        return f.extrude(V(0, tiefe + 0.1, 0))
    f.translate(V(x, -Y1 + tiefe, z))
    return f.extrude(V(0, -tiefe - 0.1, 0))


EINBAUTEN = []                    # Hüllquader der Einbauten im Hohlraum (für die Kollisionsprüfung)


def merke(teile):
    EINBAUTEN.extend(_aufgeweitet(t.BoundBox, 0.5) for t in teile)
    return teile


def vereinige(teile):
    erg = teile[0]
    if len(teile) > 1:
        erg = erg.fuse(teile[1:])
    return erg


# ---------------------------------------------------------------- Grundkörper
def schale():
    aussen = rr(X0, X1, Y0, Y1, Z_UNTEN, Z_OBEN, R_AUSSEN)
    innen = rr(-SPALT, B + SPALT, -SPALT, T + SPALT, Z_BODEN, Z_DECKE, 1.0)
    return aussen.cut(innen)


def oeffnungen():
    """Durchbrüche, die Unterschale und Deckel gemeinsam betreffen (über die Trennebene hinweg)."""
    o = {}
    # Rückwand: Buchsen (Stirnfläche bündig mit der hinteren Platinenkante)
    hinten = (Y0 - 1, 0.5)
    x, _ = pos("J10")
    o["USB-C"] = langloch_y(x, 2.78, 12.4, 6.6, *hinten)      # Platz für Steckertüllen bis 12 × 6,5
    for ref, (xa, xb, oben) in RJ_BUCHSEN.items():
        o[ref] = rr(xa - 0.3, xb + 0.3, hinten[0], hinten[1], Z_TEIL - 0.01, oben + 0.3)
    # Vorderwand: µSD-Schlitz und Griffmulde
    x, _ = pos("J13")
    o["µSD"] = rr(x - 6.5, x + 6.5, T - 0.5, Y1 + 1, Z_TEIL - 0.01, 3.9)
    mulde = Part.makeCylinder(4.0, 16.0, V(x - 8.0, -(Y1 + 2.6), 2.7), V(1, 0, 0))
    o["Griffmulde"] = mulde
    return o


def lippe():
    """Zentrierrand: äußere Wandhälfte der Unterschale ragt in eine Stufe des Deckels."""
    aussen = rr(X0, X1, Y0, Y1, Z_TEIL - 0.01, Z_TEIL + LIPPE_H, R_AUSSEN)
    innen = rr(X0 + LIPPE_B, X1 - LIPPE_B, Y0 + LIPPE_B, Y1 - LIPPE_B, Z_TEIL - 1, Z_TEIL + LIPPE_H + 1,
               R_AUSSEN - LIPPE_B)
    rand = aussen.cut(innen)
    w = LIPPE_B + LIPPE_LUFT
    a2 = rr(X0 - 1, X1 + 1, Y0 - 1, Y1 + 1, Z_TEIL - 0.01, Z_TEIL + LIPPE_H + 0.2)
    i2 = rr(X0 + w, X1 - w, Y0 + w, Y1 - w, Z_TEIL - 1, Z_TEIL + LIPPE_H + 1, R_AUSSEN - w)
    return rand, a2.cut(i2)


def loecher():
    return [pos(h) for h in ("H1", "H2", "H3", "H4")]


def saeule(x, y, z0, z1):
    """Säule Ø SAEULE_D; liegt sie näher als 3 mm an einer Wand, verbindet ein Steg sie mit der Wand
    (sonst bliebe ein nicht druckbarer Spalt)."""
    k = zyl(x, y, SAEULE_D, z0, z1)
    r = SAEULE_D / 2
    for nah, steg in ((x - r + SPALT < 3, rr(-SPALT - 0.5, x, y - r, y + r, z0, z1)),
                      (B + SPALT - (x + r) < 3, rr(x, B + SPALT + 0.5, y - r, y + r, z0, z1)),
                      (y - r + SPALT < 3, rr(x - r, x + r, -SPALT - 0.5, y, z0, z1)),
                      (T + SPALT - (y + r) < 3, rr(x - r, x + r, y, T + SPALT + 0.5, z0, z1))):
        if nah:
            k = k.fuse(steg)
    return k.removeSplitter()


# ---------------------------------------------------------------- Unterschale
def unterschale(grund, oeff, rand):
    teil = grund.common(rr(X0 - 1, X1 + 1, Y0 - 1, Y1 + 1, Z_UNTEN - 1, Z_TEIL)).fuse(rand)
    zusatz = [saeule(x, y, Z_BODEN - 0.5, 0.0) for x, y in loecher()]
    zusatz += [zyl(*pos(sw), 5.0, Z_BODEN - 0.5, 0.0) for sw, _ in TASTER]          # Stütze unter jedem Taster
    teil = teil.fuse(merke(zusatz))
    ab = list(oeff.values())
    for x, y in loecher():
        ab.append(zyl(x, y, DURCHGANG_D, Z_UNTEN - 1, 0.5))
        ab.append(zyl(x, y, KOPF_D, Z_UNTEN - 1, Z_UNTEN + KOPF_T))
    for x in (8.0, B - 8.0):                                # Mulden für Klebefüße Ø10
        for y in (8.0, T - 8.0):
            ab.append(zyl(x, y, 10.5, Z_UNTEN - 1, Z_UNTEN + 0.6))
    for ref, text in BUCHSEN_HINTEN:
        ab.append(gravur_wand(text, 2.4, ausschnitt_mitte(ref), -2.4, hinten=True))
    ab.append(gravur_wand("µSD", 2.4, pos("J13")[0], -2.4, hinten=False))
    return teil.cut(ab).removeSplitter()


# ---------------------------------------------------------------- Deckel
def deckel(grund, oeff, randschnitt):
    teil = grund.common(rr(X0 - 1, X1 + 1, Y0 - 1, Y1 + 1, Z_TEIL, Z_OBEN + 1)).cut(randschnitt)
    # Tasten: Biegezunge (Gelenk hinten, freies Ende über dem Taster), von innen auf ZUNGE_D gedünnt
    ab = []
    for sw, _ in TASTER:
        x, y = pos(sw)
        ya, yb = y - ZUNGE_L + 3.5, y + 3.5                      # Platinenmaß: yb = freies Ende vorn
        u = rr(x - ZUNGE_B / 2 - SCHLITZ, x + ZUNGE_B / 2 + SCHLITZ, ya, yb + SCHLITZ, Z_DECKE - 1, Z_OBEN + 1)
        zunge = rr(x - ZUNGE_B / 2, x + ZUNGE_B / 2, ya - 1, yb, Z_DECKE - 2, Z_OBEN + 2)
        ab.append(u.cut(zunge))
        ab.append(rr(x - ZUNGE_B / 2, x + ZUNGE_B / 2, ya, yb, Z_DECKE - 1, Z_OBEN - ZUNGE_D))
    teil = teil.cut(ab)
    zusatz = []
    for sw, _ in TASTER:
        x, y = pos(sw)
        zusatz.append(zyl(x, y, STOESSEL_D, TASTE_OBEN + TASTE_SPIEL, Z_OBEN - ZUNGE_D + 0.01))
    for x, y in loecher():
        zusatz.append(saeule(x, y, Z_TEIL, Z_DECKE + 0.5))
    for led, _ in LEDS:
        zusatz.append(zyl(*pos(led), ROHR_D, LED_OBEN + 0.6, Z_DECKE + 0.5))
    teil = teil.fuse(merke(zusatz))

    ab = list(oeff.values())
    for x, y in loecher():
        ab.append(zyl(x, y, EINSATZ_D, Z_TEIL - 1, Z_TEIL + EINSATZ_T))
    for led, text in LEDS:
        x, y = pos(led)
        ab.append(zyl(x, y, LL_BOHRUNG, LED_OBEN, Z_OBEN + 1))
        ab.append(zyl(x, y, LL_KOPF_D + 0.4, Z_OBEN - LL_KOPF_T, Z_OBEN + 1))
        ab.append(gravur_oben(text, 2.2, x, y - 7.0, drehung=90))
    for sw, text in TASTER:
        x, y = pos(sw)
        ab.append(gravur_oben(text, 1.9, x, y - ZUNGE_L + 1.4))
        ring = zyl(x, y, 6.0, Z_OBEN - 0.3, Z_OBEN + 1).cut(zyl(x, y, 5.0, Z_OBEN - 1, Z_OBEN + 2))
        ab.append(ring)
    # Lüfter: Gitter (Schlitze in einem Kreis Ø27) und vier Schraublöcher
    lx, ly = LUEFTER
    kreis = zyl(lx, ly, 27.0, Z_DECKE - 1, Z_OBEN + 1)
    schlitze = vereinige([rr(lx - 14, lx + 14, ly + k * 3.6 - 1.0, ly + k * 3.6 + 1.0, Z_DECKE - 1, Z_OBEN + 1)
                          for k in range(-3, 4)])
    ab.append(kreis.common(schlitze))
    for dx in (-LUEFTER_LOCH / 2, LUEFTER_LOCH / 2):
        for dy in (-LUEFTER_LOCH / 2, LUEFTER_LOCH / 2):
            ab.append(zyl(lx + dx, ly + dy, 3.4, Z_DECKE - 1, Z_OBEN + 1))
    # Abluft: senkrechte Schlitze in den Seitenwänden
    for y in range(30, 66, 4):
        ab.append(rr(X0 - 1, -SPALT + 0.5, y - 1.0, y + 1.0, 6.0, 14.0))
    for y in range(48, 76, 4):
        ab.append(rr(B + SPALT - 0.5, X1 + 1, y - 1.0, y + 1.0, 6.0, 14.0))
    ab.append(gravur_oben("Sopho2SIP", 6.0, 82.0, 45.0, tiefe=0.5))
    return teil.cut(ab).removeSplitter()


def lichtleiter():
    """Lichtleiter (transparent drucken, z. B. PETG klar), Einbaulage."""
    stuecke = []
    for led, _ in LEDS:
        x, y = pos(led)
        schaft = zyl(x, y, LL_D, LED_OBEN + LL_SPIEL, Z_OBEN - LL_KOPF_T + 0.01)
        kopf = zyl(x, y, LL_KOPF_D, Z_OBEN - LL_KOPF_T, Z_OBEN)
        stuecke.append(schaft.fuse(kopf).removeSplitter())
    return stuecke


def luefter_platzhalter():
    lx, ly = LUEFTER
    a = LUEFTER_A / 2
    return rr(lx - a, lx + a, ly - a, ly + a, Z_DECKE - LUEFTER_H, Z_DECKE)


# ---------------------------------------------------------------- Prüfung
def platine_teile():
    doc = FreeCAD.newDocument("platine")
    Import.insert(os.path.join(HIER, "platine_bestueckt.step"), doc.Name)
    teile = []
    for o in doc.Objects:
        if o.TypeId == "Part::Feature" and not o.Shape.isNull() and o.Shape.Solids:
            s = o.Shape.copy()
            s.Placement = o.getGlobalPlacement()
            teile.append((o.Label, s))
    return teile


def pruefe(koerper, platine):
    """Volumen der Überschneidung jedes Gehäuseteils mit jedem Bauteil. Vorauswahl: Bauteile, die aus dem
    Hohlraum hinausragen oder den Hüllquader eines Einbaus (Säule, Stößel, Rohr …) schneiden."""
    hohlraum = FreeCAD.BoundBox(-SPALT + 0.05, -(T + SPALT) + 0.05, Z_BODEN + 0.05,
                                B + SPALT - 0.05, SPALT - 0.05, Z_DECKE - 0.05)
    verdacht = [(label, s) for label, s in platine
                if not hohlraum.isInside(s.BoundBox) or any(z.intersect(s.BoundBox) for z in EINBAUTEN)]
    zeilen = [f"{len(verdacht)} von {len(platine)} Bauteilkörpern geprüft"]
    for name, k in koerper:
        bbk = k.BoundBox
        for label, s in (verdacht if name in ("Unterschale", "Deckel") else platine):
            if not bbk.intersect(s.BoundBox):
                continue
            v = k.common(s).Volume
            if v > 1e-3:
                bb = s.BoundBox
                zeilen.append(f"KOLLISION {name} × {label}: {v:.3f} mm³ bei x {bb.XMin:.1f}..{bb.XMax:.1f} "
                              f"y {-bb.YMax:.1f}..{-bb.YMin:.1f} z {bb.ZMin:.1f}..{bb.ZMax:.1f}")
    return zeilen + (["keine Kollision mit der bestückten Platine"] if len(zeilen) == 1 else [])


def abstand_min(koerper, platine, ziel):
    """Kleinster Abstand eines Gehäusekörpers zu den Bauteilen (nur die genannten Einbauten)."""
    erg = []
    for name, k in koerper:
        d = min(((k.distToShape(s)[0], label) for label, s in platine
                 if k.BoundBox.intersect(_aufgeweitet(s.BoundBox, ziel))), default=(float("inf"), "–"))
        erg.append(f"{name}: kleinster Abstand {d[0]:.2f} mm ({d[1]})")
    return erg


def _aufgeweitet(bb, d):
    b = FreeCAD.BoundBox(bb)
    b.enlarge(d)
    return b


# ---------------------------------------------------------------- Ausgabe
def drucklage(s, umdrehen):
    s = s.copy()
    if umdrehen:
        s.rotate(V(0, 0, 0), V(1, 0, 0), 180)
    bb = s.BoundBox
    s.translate(V(-bb.XMin, -bb.YMin, -bb.ZMin))
    return s


def stl(s, name):
    ordner = os.path.join(HIER, "druck")
    os.makedirs(ordner, exist_ok=True)
    m = MeshPart.meshFromShape(Shape=s, LinearDeflection=0.02, AngularDeflection=0.15, Relative=False)
    m.write(os.path.join(ordner, name))


def schnitte(teile, platine):
    """Schnitte für die Vorschau: x = Taster SW1 und LED D1 (Querschnitt y-z), Linienzüge als JSON."""
    erg = {}
    for ref in ("SW1", "D1", "H3"):
        x = pos(ref)[0]
        linien = []
        for art, k in teile + [("platine", s) for _, s in platine]:
            bb = k.BoundBox
            if not bb.XMin < x < bb.XMax:
                continue
            for w in k.slice(V(1, 0, 0), x):
                pkt = w.discretize(Distance=0.2)
                linien.append([art, [[-p.y, p.z] for p in pkt]])
        erg[ref] = {"x": x, "linien": linien}
    json.dump(erg, open(os.path.join(HIER, "schnitte.json"), "w"))


def main():
    pruefe_beschriftung()
    grund = schale()
    oeff = oeffnungen()
    rand, randschnitt = lippe()
    unten = unterschale(grund, oeff, rand)
    oben = deckel(grund, oeff, randschnitt)
    leiter = lichtleiter()
    for name, s in (("Unterschale", unten), ("Deckel", oben)):
        assert s.isValid() and len(s.Solids) == 1, f"{name}: {len(s.Solids)} Körper, gültig {s.isValid()}"

    doc = FreeCAD.newDocument("gehaeuse")
    objekte = []
    for name, s in [("Unterschale", unten), ("Deckel", oben)] + [(f"Lichtleiter_{l}", s)
                                                                 for (l, _), s in zip(LEDS, leiter)]:
        o = doc.addObject("Part::Feature", name)
        o.Shape = s
        objekte.append(o)
    doc.recompute()
    doc.saveAs(os.path.join(HIER, "gehaeuse.FCStd"))
    Import.export(objekte, os.path.join(HIER, "gehaeuse.step"))

    stl(drucklage(unten, False), "unterschale.stl")
    stl(drucklage(oben, True), "deckel.stl")
    satz = []
    for i, s in enumerate(leiter):                            # Kopf nach unten, nebeneinander
        s = drucklage(s, True)
        s.translate(V(i * 7.0, 0, 0))
        satz.append(s)
    stl(Part.makeCompound(satz), "lichtleiter_5x.stl")

    platine = platine_teile()
    luefter = luefter_platzhalter()
    zeilen = [f"Gehäuse außen {X1 - X0:.1f} × {Y1 - Y0:.1f} × {Z_OBEN - Z_UNTEN:.1f} mm "
              f"(B × T × H), Volumen Unterschale {unten.Volume / 1000:.1f} cm³, Deckel {oben.Volume / 1000:.1f} cm³"]
    kollision = pruefe([("Unterschale", unten), ("Deckel", oben), ("Lüfter", luefter)]
                       + [(f"Lichtleiter {l}", s) for (l, _), s in zip(LEDS, leiter)], platine)
    zeilen += kollision
    stoessel = [(f"Stößel {sw}", zyl(*pos(sw), STOESSEL_D, TASTE_OBEN + TASTE_SPIEL, Z_DECKE)) for sw, _ in TASTER]
    zeilen += abstand_min(stoessel + [("Lüfter", luefter)], platine, 6.0)
    open(os.path.join(HIER, "pruefung.txt"), "w", encoding="utf-8").write("\n".join(zeilen) + "\n")
    schnitte([("unterschale", unten), ("deckel", oben)] + [("lichtleiter", s) for s in leiter], platine)
    print("\n".join(zeilen))


main()

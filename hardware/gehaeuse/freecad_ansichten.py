# SPDX-License-Identifier: GPL-3.0-or-later
"""Ansichten des Gehäuses mit eingebauter Platine (FreeCAD-Oberfläche, ohne Bildschirm über xvfb):

  xvfb-run -a -s "-screen 0 1600x1200x24" flatpak run org.freecad.FreeCAD $PWD/hardware/gehaeuse/freecad_ansichten.py

Schreibt ansichten/*.png. Braucht gehaeuse.FCStd und platine_bestueckt.step (siehe freecad_gehaeuse.py).
"""
import os

import FreeCAD
import FreeCADGui
import ImportGui

HIER = os.path.dirname(os.path.abspath(__file__))
AUS = os.path.join(HIER, "ansichten")
os.makedirs(AUS, exist_ok=True)

doc = FreeCAD.openDocument(os.path.join(HIER, "gehaeuse.FCStd"))
ImportGui.insert(os.path.join(HIER, "platine_bestueckt.step"), doc.Name)
FreeCADGui.getMainWindow().resize(1600, 1200)
ansicht = FreeCADGui.getDocument(doc.Name).activeView()
FARBEN = {"Unterschale": (0.55, 0.58, 0.62), "Deckel": (0.22, 0.25, 0.30)}
GEHAEUSE = ["Unterschale", "Deckel"] + [o.Name for o in doc.Objects if o.Name.startswith("Lichtleiter")]


def vo(name):
    return FreeCADGui.getDocument(doc.Name).getObject(name)


for name, farbe in FARBEN.items():
    vo(name).ShapeColor = farbe
for o in doc.Objects:
    if o.Name.startswith("Lichtleiter"):
        vo(o.Name).ShapeColor = (0.75, 0.88, 1.0)
        vo(o.Name).Transparency = 30


def zeige(nur=None, transparenz=None):
    for o in doc.Objects:
        v = vo(o.Name)
        if v is None or not hasattr(v, "Visibility"):
            continue
        if nur is not None and o.Name in GEHAEUSE:
            v.Visibility = o.Name in nur or (o.Name.startswith("Lichtleiter") and "Lichtleiter" in nur)
    for name, t in (transparenz or {}).items():
        vo(name).Transparency = t


def bild(datei, richtung):
    for _ in range(2):                   # erster Aufruf nach dem Laden greift sonst nicht
        FreeCADGui.updateGui()
        getattr(ansicht, richtung)()
        ansicht.fitAll()
    FreeCADGui.updateGui()
    ansicht.saveImage(os.path.join(AUS, datei), 1600, 1200, "White")


zeige(nur=["Unterschale", "Deckel", "Lichtleiter"], transparenz={"Deckel": 0, "Unterschale": 0})
bild("gehaeuse_vorn.png", "viewIsometric")
bild("gehaeuse_hinten.png", "viewRear")
bild("gehaeuse_oben.png", "viewTop")
bild("gehaeuse_vorderseite.png", "viewFront")
zeige(nur=["Unterschale", "Deckel", "Lichtleiter"], transparenz={"Deckel": 70})
bild("einbau_durchsicht.png", "viewIsometric")
zeige(nur=["Unterschale"])
bild("unterschale_mit_platine.png", "viewIsometric")
FreeCAD.closeDocument(doc.Name)
os._exit(0)                      # Oberfläche ohne Rückfrage beenden

# 3D-Modelle (nicht im Repo)

Herstellermodelle dürfen meist nicht weitergegeben werden. Sie liegen nur lokal in diesem Ordner; `richte_3d_aus.py`
schreibt daraus die ausgerichteten Modelle nach `ausgerichtet/`, auf die die Footprints verweisen.

| Datei | Bauteil | Quelle | SHA-256 (Stand 2026-10-04) |
|---|---|---|---|
| `7499010211A.stp` | Würth RJ45 mit Übertrager (J14) | Würth Elektronik / SnapEDA | `2a6b6ec668fbc4a9c21a563d8db33cb856da3924e848cb36465a19cd7ed7a514` |
| `615006138421.stp` | Würth RJ12 6P6C (J2) | Würth Elektronik / SnapEDA | `efb0b04f23887a7a559d470d5be7c99286ea27d10c0ea032a4bb6ecd59463bb4` |
| `615004143821.stp` | Würth RJ10 4P4C (J3) | Würth Elektronik / SnapEDA | noch nicht vorhanden |
| `DF40C-100DS.stp` | Hirose DF40C-100DS-0.4V(51) (J11, J12) | Hirose | `dba37971e28389011f22bbda0a6b57ba5f8678b0b643a95ed294114efd44ff06` |
| `ECS-2520MV-120-BN-TR.step` | ECS Oszillator 12 MHz (U6) | ECS | `a44a5ab4269b68825e93a2435582f8c686c255dffdc670d1b2f04502b08554f2` |
| `SM-LP-5001.STEP` | Bourns Übertrager (T1, T2) | Bourns | `332b73098eab5d670e74056b19e481cb792afa2106a96331f6526169f70b6313` |
| `CM4-step.zip` | Raspberry Pi CM4 (M1) | https://datasheets.raspberrypi.com/cm4/CM4-step.zip (lädt das Skript selbst) | `667649c0728b260ea7ce6b595eb0458f53bd5eef5a3249d3a8b5415de81e23a5` |

Fehlt eine Datei, zeigt KiCad das Bauteil ohne Körper; elektrisch ändert sich nichts.

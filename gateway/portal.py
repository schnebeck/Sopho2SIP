# SPDX-License-Identifier: GPL-3.0-or-later
"""Webportal des Gateways: Anrufliste, Rückruf, Wähltastatur mit Tonwahl, Live-Zustand.

Läuft als Thread im Daemon (gateway/sopho2sipd.py --portal ADRESSE:PORT) und spricht nur mit dessen Gateway-Objekt.
Nur Standardbibliothek. Zugang per HTTP-Basic-Auth; Passwort setzen (auf dem Pi):
    python3 gateway/portal.py passwort [BENUTZER]
Ohne Passwortdatei lauscht das Portal nur auf 127.0.0.1 (Zugriff dann per ssh -L 8080:localhost:8080 sopho-gw).
HTTPS mit eigenem Zertifikat (nötig für Browser-Benachrichtigungen, schützt das Passwort):
    python3 gateway/portal.py zertifikat        # → ~/.config/sopho2sip/portal.crt/.key, danach Dienst neu starten
Liegt ein Zertifikat vor, spricht das Portal auf demselben Port nur noch HTTPS.

API (JSON):  GET /api/status · GET /api/anrufe?n=200 · GET /api/ereignisse (Server-Sent Events)
             POST /api/waehlen {"nummer": "…"} · POST /api/annehmen · POST /api/auflegen
POST verlangt den Kopf "X-Sopho2SIP: 1" (erzwingt CORS-Preflight, schützt gegen fremde Formulare).
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import json
import os
import pathlib
import queue
import secrets
import socket
import ssl
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

WEB = pathlib.Path(__file__).resolve().parent / "web"
PASSWORTDATEI = pathlib.Path.home() / ".config" / "sopho2sip" / "portal.json"
ZERTIFIKAT = PASSWORTDATEI.with_name("portal.crt")
SCHLUESSEL = PASSWORTDATEI.with_name("portal.key")
ITERATIONEN = 200_000


# --- Passwort -------------------------------------------------------------------------------------
def passwort_setzen(benutzer: str, passwort: str, pfad: pathlib.Path = PASSWORTDATEI) -> None:
    salz = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", passwort.encode(), salz, ITERATIONEN)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(pfad, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"benutzer": benutzer, "salz": salz.hex(), "hash": h.hex(), "iterationen": ITERATIONEN}, f)


def lade_zugang(pfad: pathlib.Path = PASSWORTDATEI) -> dict | None:
    try:
        return json.loads(pfad.read_text())
    except FileNotFoundError:
        return None


def pruefe(zugang: dict, kopf: str | None) -> bool:
    if not kopf or not kopf.startswith("Basic "):
        return False
    try:
        benutzer, _, passwort = base64.b64decode(kopf[6:]).decode().partition(":")
    except (ValueError, UnicodeDecodeError):
        return False
    h = hashlib.pbkdf2_hmac("sha256", passwort.encode(), bytes.fromhex(zugang["salz"]), zugang["iterationen"])
    return hmac.compare_digest(benutzer, zugang["benutzer"]) & hmac.compare_digest(h.hex(), zugang["hash"])


def zertifikat_erzeugen() -> None:
    """Selbstsigniertes Zertifikat (EC P-256, 10 Jahre) für alle IPv4-Adressen des Pi, Hostname und localhost."""
    ips = subprocess.run(["hostname", "-I"], capture_output=True, text=True).stdout.split()
    san = ",".join([f"IP:{ip}" for ip in ips if ":" not in ip] + ["IP:127.0.0.1", f"DNS:{socket.gethostname()}",
                                                                  "DNS:localhost"])
    ZERTIFIKAT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
                    "-days", "3650", "-nodes", "-subj", f"/CN={socket.gethostname()}/O=Sopho2SIP",
                    "-addext", f"subjectAltName={san}", "-keyout", str(SCHLUESSEL), "-out", str(ZERTIFIKAT)],
                   check=True, capture_output=True)
    SCHLUESSEL.chmod(0o600)
    fp = subprocess.run(["openssl", "x509", "-noout", "-fingerprint", "-sha256", "-in", str(ZERTIFIKAT)],
                        capture_output=True, text=True).stdout.strip()
    print(f"Zertifikat für {san}\n{fp}\nDienst neu starten: sudo systemctl restart sopho2sipd")


# --- HTTP -----------------------------------------------------------------------------------------
class Portal(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, adresse: tuple[str, int], gateway, zugang: dict | None,
                 zertifikat: tuple[pathlib.Path, pathlib.Path] | None = None):
        if zugang is None and adresse[0] not in ("127.0.0.1", "localhost", "::1"):
            raise SystemExit(f"Portal auf {adresse[0]} nur mit Passwort ({PASSWORTDATEI}); "
                             "setzen mit: python3 gateway/portal.py passwort")
        self.gateway, self.zugang = gateway, zugang
        super().__init__(adresse, Handler)
        self.tls = zertifikat is not None
        if self.tls:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.load_cert_chain(*zertifikat)
            # Handshake erst im Handler-Thread, damit ein langsamer Client das Annehmen nicht blockiert
            self.socket = ctx.wrap_socket(self.socket, server_side=True, do_handshake_on_connect=False)


class Handler(BaseHTTPRequestHandler):
    server: Portal
    protocol_version = "HTTP/1.1"
    server_version, sys_version = "Sopho2SIP", ""

    def log_message(self, fmt, *args):         # kein Zugriffsprotokoll im Journal
        pass

    def _antwort(self, code: int, daten, typ: str = "application/json; charset=utf-8") -> None:
        body = daten if isinstance(daten, bytes) else json.dumps(daten, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        if self.server.tls:
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        self.end_headers()
        self.wfile.write(body)

    def _erlaubt(self) -> bool:
        if self.server.zugang is None or pruefe(self.server.zugang, self.headers.get("Authorization")):
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Sopho2SIP", charset="UTF-8"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def do_GET(self):
        if not self._erlaubt():
            return
        url = urlparse(self.path)
        gw = self.server.gateway
        if url.path in ("/", "/index.html"):
            self._antwort(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/status":
            self._antwort(200, gw.status())
        elif url.path == "/api/anrufe":
            n = int(parse_qs(url.query).get("n", ["200"])[0])
            self._antwort(200, gw.anrufliste(max(1, min(n, 5000))))
        elif url.path == "/api/ereignisse":
            self._ereignisse()
        else:
            self._antwort(404, {"fehler": "unbekannt"})

    def do_POST(self):
        if not self._erlaubt():
            return
        if self.headers.get("X-Sopho2SIP") != "1":
            self._antwort(403, {"fehler": "Kopf X-Sopho2SIP fehlt"})
            return
        laenge = int(self.headers.get("Content-Length") or 0)
        try:
            daten = json.loads(self.rfile.read(laenge) or b"{}") if laenge <= 4096 else {}
        except json.JSONDecodeError:
            self._antwort(400, {"fehler": "kein JSON"})
            return
        art = urlparse(self.path).path.removeprefix("/api/")
        if art not in ("waehlen", "annehmen", "auflegen"):
            self._antwort(404, {"fehler": "unbekannt"})
            return
        ergebnis = self.server.gateway.auftrag(art, str(daten.get("nummer", "")))
        self._antwort(200 if ergebnis["ok"] else 409, ergebnis)

    def _ereignisse(self) -> None:
        q = self.server.gateway.abonniere()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            self.wfile.write(f"data: {json.dumps({'typ': 'STATUS', 'status': self.server.gateway.status()})}\n\n".encode())
            self.wfile.flush()
            while True:
                try:
                    ev = q.get(timeout=15)
                    self.wfile.write(f"data: {json.dumps(ev, ensure_ascii=False)}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.server.gateway.abbestelle(q)


def starte(adresse: str, gateway) -> Portal:
    host, _, port = adresse.rpartition(":")
    zugang = lade_zugang()
    if zugang is None and host not in ("127.0.0.1", "localhost", "::1"):
        print(f"Portal: kein Passwort ({PASSWORTDATEI}), lausche nur auf 127.0.0.1", file=sys.stderr, flush=True)
        host = "127.0.0.1"
    zert = (ZERTIFIKAT, SCHLUESSEL) if ZERTIFIKAT.exists() and SCHLUESSEL.exists() else None
    portal = Portal((host or "127.0.0.1", int(port)), gateway, zugang, zert)
    threading.Thread(target=portal.serve_forever, daemon=True, name="portal").start()
    return portal


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "zertifikat":
        zertifikat_erzeugen()
    elif len(sys.argv) >= 2 and sys.argv[1] == "passwort":
        benutzer = sys.argv[2] if len(sys.argv) > 2 else "sopho"
        pw = getpass.getpass(f"Neues Portal-Passwort für {benutzer}: ")
        if len(pw) < 8 or pw != getpass.getpass("Wiederholen: "):
            raise SystemExit("abgebrochen (mindestens 8 Zeichen, beide Eingaben gleich)")
        passwort_setzen(benutzer, pw)
        print(f"gespeichert: {PASSWORTDATEI}; Daemon neu starten: sudo systemctl restart sopho2sipd")
    else:
        print(__doc__)

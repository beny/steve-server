#!/usr/bin/env python3
"""Jednorázová autorizace Strava účtu.

Spusť, zadej Client ID + Secret z strava.com/settings/api, v prohlížeči
odklikni "Authorize" (přihlášený jako Steve) — skript chytí redirect,
vymění kód za tokeny a uloží je do strava_tokens.json. Víc není potřeba,
server si pak tokeny obnovuje sám.
"""

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from app.config import STRAVA_TOKENS_PATH

PORT = 8723
REDIRECT_URI = f"http://localhost:{PORT}/"

code_holder: dict = {}


class Callback(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if "code" in params:
            code_holder["code"] = params["code"][0]
            self.wfile.write("<h1>Hotovo, okno můžeš zavřít. 🐹</h1>".encode())
        else:
            self.wfile.write("<h1>Chybí code — zkus to znovu.</h1>".encode())

    def log_message(self, *args):
        pass


def main():
    client_id = input("Client ID: ").strip()
    client_secret = input("Client Secret: ").strip()

    url = "https://www.strava.com/oauth/authorize?" + urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "activity:write",
    })

    server = HTTPServer(("localhost", PORT), Callback)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print(f"\nOtevírám prohlížeč (přihlas se jako Steve a klikni Authorize):\n{url}\n")
    webbrowser.open(url)

    while "code" not in code_holder:
        pass
    server.shutdown()

    resp = httpx.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "code": code_holder["code"],
        },
        timeout=30,
    )
    resp.raise_for_status()
    tokens = resp.json()

    with open(STRAVA_TOKENS_PATH, "w") as f:
        json.dump(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "access_token": tokens["access_token"],
                "refresh_token": tokens["refresh_token"],
                "expires_at": tokens["expires_at"],
            },
            f,
            indent=2,
        )

    athlete = tokens.get("athlete", {})
    print(f"Tokeny uloženy do {STRAVA_TOKENS_PATH}")
    print(f"Autorizován účet: {athlete.get('firstname', '?')} {athlete.get('lastname', '')}")


if __name__ == "__main__":
    main()

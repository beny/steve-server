"""Strava API: obnova tokenů a upload FIT souborů.

Tokeny vytvoří jednorázově strava_auth.py; tenhle modul si access token
sám obnovuje z refresh tokenu a průběžně soubor aktualizuje.
"""

import json
import os
import time

import httpx

from .config import STRAVA_TOKENS_PATH

TOKEN_URL = "https://www.strava.com/oauth/token"
UPLOAD_URL = "https://www.strava.com/api/v3/uploads"


def configured() -> bool:
    return os.path.exists(STRAVA_TOKENS_PATH)


def _load() -> dict:
    with open(STRAVA_TOKENS_PATH) as f:
        return json.load(f)


def _save(tokens: dict) -> None:
    with open(STRAVA_TOKENS_PATH, "w") as f:
        json.dump(tokens, f, indent=2)


def _access_token() -> str:
    tokens = _load()
    if tokens.get("expires_at", 0) > time.time() + 60:
        return tokens["access_token"]

    resp = httpx.post(
        TOKEN_URL,
        data={
            "client_id": tokens["client_id"],
            "client_secret": tokens["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
        },
        timeout=30,
    )
    resp.raise_for_status()
    fresh = resp.json()
    tokens.update(
        access_token=fresh["access_token"],
        refresh_token=fresh["refresh_token"],
        expires_at=fresh["expires_at"],
    )
    _save(tokens)
    return tokens["access_token"]


def upload_activity(
    fit_data: bytes,
    name: str,
    description: str,
    external_id: str,
) -> int | None:
    """Nahraje FIT na Stravu, vrací upload id.

    Duplicitní upload (stejné external_id / obsah) Strava odmítne —
    bereme jako úspěch, aktivita už tam je.
    """
    resp = httpx.post(
        UPLOAD_URL,
        headers={"Authorization": f"Bearer {_access_token()}"},
        data={
            "data_type": "fit",
            "name": name,
            "description": description,
            "trainer": "1",
            "external_id": external_id,
        },
        files={"file": (f"{external_id}.fit", fit_data)},
        timeout=60,
    )
    body = resp.json()
    if "duplicate" in (body.get("error") or ""):
        return body.get("id")
    resp.raise_for_status()
    return body.get("id")

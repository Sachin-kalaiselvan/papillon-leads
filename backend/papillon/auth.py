"""Dashboard logins without Supabase: scrypt password hashes + signed tokens (standard library only)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Header, HTTPException

from . import db
from .config import cfg

TOKEN_DAYS = 30


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def check_password(password: str, stored: str | None) -> bool:
    try:
        _, salt_b64, hash_b64 = (stored or "").split("$")
        h = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), n=2**14, r=8, p=1)
        return hmac.compare_digest(h, base64.b64decode(hash_b64))
    except ValueError:
        return False


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def make_token(user_id: str) -> str:
    body = _b64(json.dumps({"u": user_id, "exp": int(time.time()) + TOKEN_DAYS * 86400}).encode())
    sig = _b64(hmac.new(cfg.signing_secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(token: str) -> str | None:
    try:
        body, sig = token.split(".")
    except ValueError:
        return None
    good = _b64(hmac.new(cfg.signing_secret.encode(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(good, sig):
        return None
    data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    return data["u"] if data.get("exp", 0) > time.time() else None


async def current_user(authorization: str = Header(default="")) -> dict:
    uid = read_token(authorization.removeprefix("Bearer ").strip()) if authorization else None
    user = await db.fetchone("select id, email, name, org, role from team_members where id = %s and active", [uid]) if uid else None
    if not user:
        raise HTTPException(401, "Please sign in again")
    return user

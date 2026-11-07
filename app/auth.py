"""Passwordless login by phone number for the Dial-a-Text dashboard.

Flow: POST /api/auth/request-code -> SMS with a 6-digit code ->
POST /api/auth/verify -> session cookie. Only hashes of codes and session
tokens are stored.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel

from app import dashboard_adapters as adapters
from app import dashboard_data as data

log = logging.getLogger("dialatext.dashboard")

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_NAME = "dat_session"
SESSION_DAYS = 7
CODE_MINUTES = 10
MAX_ATTEMPTS = 5
MAX_CODES_PER_HOUR = 3
SERVICES_LIVE = {"sms"}
SERVICES_SOON = {"whatsapp"}

# Seeded by scripts/seed_dashboard.py (Ofcom drama number, nobody real).
DEMO_PHONE = "+447700900001"


def api_error(status: int, message: str, field: str | None = None) -> HTTPException:
    return HTTPException(status_code=status, detail={"message": message, "field": field})


# --- secrets and hashing ----------------------------------------------------

_fallback_secret = secrets.token_hex(32)


def _secret() -> bytes:
    value = os.getenv("DASHBOARD_SECRET")
    if value:
        return value.encode()
    if adapters.demo_mode():
        # Stable across --reload in local demo so pending codes survive restarts.
        return b"dial-a-text-demo-only-secret"
    return _fallback_secret.encode()


def hash_code(phone: str, code: str) -> str:
    # Keyed hash: a leaked table of 6-digit code hashes can't be brute-forced
    # without the server secret.
    return hmac.new(_secret(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def cookie_secure() -> bool:
    return os.getenv("PUBLIC_URL", "").lower().startswith("https://")


# --- validation helpers (shared with dashboard_routes) -----------------------


def normalise_or_400(raw: str, field: str = "phone") -> str:
    try:
        return adapters.normalise_phone(raw)
    except adapters.PhoneError as exc:
        raise api_error(400, str(exc), field)


def clean_name(raw: str | None, *, required: bool) -> str | None:
    name = " ".join((raw or "").split())
    if not name:
        if required:
            raise api_error(400, "Please enter your name.", "name")
        return None
    if len(name) > 60:
        raise api_error(400, "That name is a bit long. Please keep it under 60 characters.", "name")
    return name


def clean_service(raw: str | None) -> str | None:
    if raw is None or raw == "":
        return None
    value = raw.strip().lower()
    if value in SERVICES_SOON:
        raise api_error(400, "WhatsApp is coming soon. Please choose SMS for now.", "preferred_service")
    if value not in SERVICES_LIVE:
        raise api_error(400, "Please choose SMS.", "preferred_service")
    return value


# --- sessions ---------------------------------------------------------------


def start_session(response: Response, user_id: int) -> None:
    token = secrets.token_urlsafe(32)  # 32 random bytes
    expires = data.utc_now() + timedelta(days=SESSION_DAYS)
    data.create_session(user_id, hash_token(token), data.to_db_time(expires))
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=cookie_secure(),
        path="/",
    )


def user_from_token(token: str | None) -> dict | None:
    if not token:
        return None
    return data.user_for_session(hash_token(token))


def current_user(dat_session: str | None = Cookie(default=None)) -> dict:
    user = user_from_token(dat_session)
    if not user:
        raise api_error(401, "Please log in.")
    return user


CurrentUser = Depends(current_user)


# --- endpoints --------------------------------------------------------------


class RequestCodeIn(BaseModel):
    phone: str
    name: str | None = None
    preferred_service: str | None = None


class VerifyIn(BaseModel):
    phone: str
    code: str


@router.get("/config")
def auth_config() -> dict:
    return {
        "demo_mode": adapters.demo_mode(),
        "service_number": adapters.service_number(),
    }


@router.post("/request-code")
def request_code(body: RequestCodeIn) -> dict:
    phone = normalise_or_400(body.phone)
    service = clean_service(body.preferred_service)
    user = data.get_user_by_phone(phone)
    new_user = user is None

    if new_user:
        name = clean_name(body.name, required=False)
        if not name:
            # Ask the page to collect name and service before sending a code.
            return {"status": "needs_details"}
        user = data.create_user(phone, name, service or "sms")
    elif body.name:
        # Someone who called first may have no name yet.
        name = clean_name(body.name, required=False)
        if name:
            data.fill_missing_name(user["id"], name)

    hour_ago = data.to_db_time(data.utc_now() - timedelta(hours=1))
    if data.count_codes_since(phone, hour_ago) >= MAX_CODES_PER_HOUR:
        raise api_error(
            429,
            "You've asked for 3 codes in the last hour. Please wait a while and try again.",
            "phone",
        )

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires = data.utc_now() + timedelta(minutes=CODE_MINUTES)
    data.insert_login_code(phone, hash_code(phone, code), data.to_db_time(expires))

    if adapters.demo_mode():
        log.warning("[DEMO_MODE] Login code for %s: %s", phone, code)

    try:
        adapters.send_sms(phone, f"Dial-a-Text code: {code}. Expires in {CODE_MINUTES} minutes.")
    except Exception as exc:  # trial credit, network, not wired up yet...
        log.error("Could not send login code to %s: %s: %s", phone, type(exc).__name__, exc)
        raise api_error(
            502,
            "We couldn't send a text to that number just now. While Dial-a-Text is on trial "
            "credit, texts only reach approved numbers. Please try again later.",
            "phone",
        )

    return {"status": "sent", "new_user": new_user, "expires_in": CODE_MINUTES * 60}


@router.post("/verify")
def verify(body: VerifyIn, response: Response) -> dict:
    phone = normalise_or_400(body.phone)
    code = "".join(body.code.split())
    if not (len(code) == 6 and code.isdigit()):
        raise api_error(400, "The code is 6 digits. Please check the text we sent you.", "code")

    row = data.latest_open_code(phone)
    if not row:
        raise api_error(400, "There's no code waiting for this number. Please ask for a new one.", "code")
    if row["attempts"] >= MAX_ATTEMPTS:
        raise api_error(429, "Too many wrong tries. Please ask for a new code.", "code")
    if row["expires_at"] <= data.now_str():
        raise api_error(400, "That code has expired. Please ask for a new one.", "code")

    if not hmac.compare_digest(row["code_hash"], hash_code(phone, code)):
        attempts = data.add_code_attempt(row["id"])
        left = MAX_ATTEMPTS - attempts
        if left <= 0:
            raise api_error(429, "Too many wrong tries. Please ask for a new code.", "code")
        raise api_error(
            400, f"That code isn't right. You have {left} {'try' if left == 1 else 'tries'} left.", "code"
        )

    user = data.get_user_by_phone(phone)
    if not user:
        raise api_error(400, "We couldn't find your account. Please start again.", "phone")
    data.consume_code(row["id"])
    start_session(response, user["id"])
    return {"user": user}


@router.post("/logout")
def logout(response: Response, dat_session: str | None = Cookie(default=None)) -> dict:
    if dat_session:
        data.delete_session(hash_token(dat_session))
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax", secure=cookie_secure())
    return {"ok": True}


@router.post("/demo")
def demo_login(response: Response) -> dict:
    if not adapters.demo_mode():
        raise api_error(404, "Not found.")
    user = data.get_user_by_phone(DEMO_PHONE)
    if not user:
        raise api_error(404, "The demo account isn't set up. Run: python scripts/seed_dashboard.py")
    start_session(response, user["id"])
    return {"user": user}

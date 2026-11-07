"""Dial-a-Text dashboard: JSON API under /api plus the /account pages.

Mount in app/main.py with one line:

    from app.dashboard_routes import router as dashboard_router
    app.include_router(dashboard_router)

This router includes the auth router and serves static/account/ itself, so
nothing else needs mounting. Every endpoint except /api/auth/* needs a session
and only ever touches the logged-in user's rows.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Cookie, Query
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from app import auth
from app import dashboard_adapters as adapters
from app import dashboard_data as data
from app.auth import CurrentUser, api_error, clean_name, clean_service, normalise_or_400

router = APIRouter()
router.include_router(auth.router)

LONDON = ZoneInfo("Europe/London")
STATIC_DIR = (Path(__file__).resolve().parent.parent / "static" / "account").resolve()
_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    # Explicit: Windows' registry can map .js to text/plain, which breaks ES modules.
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}
MESSAGE_STATUSES = {"queued", "sent", "delivered", "failed"}


service_number = adapters.service_number


# ---------------------------------------------------------------------------
# Pages and static assets
# ---------------------------------------------------------------------------


def _page(name: str) -> FileResponse:
    return FileResponse(STATIC_DIR / name, media_type=_TYPES[".html"], headers={"Cache-Control": "no-cache"})


@router.get("/account", include_in_schema=False)
def account_page(dat_session: str | None = Cookie(default=None)):
    if not auth.user_from_token(dat_session):
        return RedirectResponse("/account/login", status_code=303)
    return _page("index.html")


@router.get("/account/login", include_in_schema=False)
def login_page(dat_session: str | None = Cookie(default=None)):
    if auth.user_from_token(dat_session):
        return RedirectResponse("/account", status_code=303)
    return _page("login.html")


@router.get("/account/assets/{name:path}", include_in_schema=False)
def account_asset(name: str):
    path = (STATIC_DIR / name).resolve()
    if STATIC_DIR not in path.parents or not path.is_file() or path.suffix not in _TYPES:
        raise api_error(404, "Not found.")
    return FileResponse(path, media_type=_TYPES[path.suffix], headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------------------
# Me
# ---------------------------------------------------------------------------


class MePatch(BaseModel):
    name: str | None = None
    preferred_service: str | None = None


def _me(user: dict) -> dict:
    return {**user, "service_number": service_number()}


@router.get("/api/me")
def get_me(user: dict = CurrentUser) -> dict:
    return _me(user)


@router.patch("/api/me")
def patch_me(body: MePatch, user: dict = CurrentUser) -> dict:
    name = clean_name(body.name, required=True) if body.name is not None else None
    service = clean_service(body.preferred_service)
    return _me(data.update_user(user["id"], name=name, preferred_service=service))


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------


class ContactIn(BaseModel):
    name: str | None = None
    phone: str | None = None
    aliases: list[str] | None = None


def _clean_aliases(raw: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in raw or []:
        alias = " ".join(str(item).split())
        if not alias:
            continue
        if len(alias) > 40:
            raise api_error(400, f'The nickname "{alias[:20]}..." is too long (40 characters max).', "aliases")
        if alias.lower() not in seen:
            seen.add(alias.lower())
            out.append(alias)
    if len(out) > 15:
        raise api_error(400, "That's a lot of nicknames. Please keep it to 15 or fewer.", "aliases")
    return out


def _contact_name(raw: str | None) -> str:
    name = " ".join((raw or "").split())
    if not name:
        raise api_error(400, "Please enter a name for this contact.", "name")
    if len(name) > 60:
        raise api_error(400, "That name is a bit long. Please keep it under 60 characters.", "name")
    return name


def _check_duplicate_phone(user_id: int, phone: str, exclude_id: int | None = None) -> None:
    clash = data.find_contact_by_phone(user_id, phone, exclude_id)
    if clash:
        raise api_error(409, f"You already have {clash['name']} saved with that number.", "phone")


@router.get("/api/contacts")
def list_contacts(q: str | None = None, user: dict = CurrentUser) -> dict:
    return {"items": data.list_contacts(user["id"], (q or "").strip() or None)}


@router.post("/api/contacts", status_code=201)
def create_contact(body: ContactIn, user: dict = CurrentUser) -> dict:
    name = _contact_name(body.name)
    phone = normalise_or_400(body.phone or "")
    aliases = _clean_aliases(body.aliases)
    _check_duplicate_phone(user["id"], phone)
    return data.create_contact(user["id"], name, phone, aliases)


@router.get("/api/contacts/{contact_id}")
def get_contact(contact_id: int, user: dict = CurrentUser) -> dict:
    contact = data.get_contact(user["id"], contact_id)
    if not contact:
        raise api_error(404, "That contact doesn't exist.")
    return contact


@router.patch("/api/contacts/{contact_id}")
def update_contact(contact_id: int, body: ContactIn, user: dict = CurrentUser) -> dict:
    if not data.get_contact(user["id"], contact_id):
        raise api_error(404, "That contact doesn't exist.")
    fields: dict = {}
    if body.name is not None:
        fields["name"] = _contact_name(body.name)
    if body.phone is not None:
        fields["phone"] = normalise_or_400(body.phone)
        _check_duplicate_phone(user["id"], fields["phone"], exclude_id=contact_id)
    if body.aliases is not None:
        fields["aliases"] = _clean_aliases(body.aliases)
    return data.update_contact(user["id"], contact_id, fields)


@router.delete("/api/contacts/{contact_id}")
def delete_contact(contact_id: int, user: dict = CurrentUser) -> dict:
    if not data.delete_contact(user["id"], contact_id):
        raise api_error(404, "That contact doesn't exist.")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Messages log
# ---------------------------------------------------------------------------


def _london_day_start_utc(value: str, field: str, plus_days: int = 0) -> str:
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise api_error(400, "Please use a date like 2026-11-07.", field)
    local = datetime.combine(day + timedelta(days=plus_days), time.min, tzinfo=LONDON)
    return data.to_db_time(local)


@router.get("/api/messages")
def list_messages(
    contact_id: int | None = None,
    number: str | None = None,
    direction: str | None = None,
    status: str | None = None,
    q: str | None = None,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = None,
    user: dict = CurrentUser,
) -> dict:
    if direction and direction not in {"out", "in"}:
        raise api_error(400, "Direction must be 'out' or 'in'.", "direction")
    if status and status not in MESSAGE_STATUSES:
        raise api_error(400, "Unknown status.", "status")
    return data.list_messages(
        user["id"],
        contact_id=contact_id,
        number=normalise_or_400(number, "number") if number else None,
        direction=direction or None,
        status=status or None,
        q=(q or "").strip() or None,
        # Dates are London calendar days; "to" is inclusive.
        from_utc=_london_day_start_utc(from_, "from") if from_ else None,
        to_utc=_london_day_start_utc(to, "to", plus_days=1) if to else None,
        limit=limit,
        cursor=cursor or None,
    )

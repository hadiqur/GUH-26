"""All SQL used by the Dial-a-Text dashboard lives in this file.

When the real schema from app/db.py lands, this is the only file to adapt.
Every query that reads user data takes a user_id and is scoped to it.

Tables and columns this file expects (created IF NOT EXISTS in dev; missing
columns are added to existing tables with defaults, never dropped):

users
    id INTEGER PK, phone TEXT UNIQUE (E.164), name TEXT,
    preferred_service TEXT DEFAULT 'sms', created_at TEXT (UTC)
    -- the same row the phone agent creates via register_user, matched by phone.

contacts
    id INTEGER PK, user_id INTEGER, name TEXT, phone TEXT (E.164),
    aliases TEXT (JSON list, e.g. ["Mom","Mam"]), created_at TEXT, updated_at TEXT

drafts
    id INTEGER PK, user_id INTEGER, contact_id INTEGER NULL, other_number TEXT,
    text TEXT, status TEXT DEFAULT 'pending', created_at TEXT

messages
    id INTEGER PK, user_id INTEGER, contact_id INTEGER NULL, other_number TEXT,
    direction TEXT ('out' | 'in'), text TEXT,
    status TEXT ('queued' | 'sent' | 'delivered' | 'failed') DEFAULT 'queued',
    parts INTEGER DEFAULT 1, encoding TEXT ('GSM-7' | 'Unicode') DEFAULT 'GSM-7',
    is_read INTEGER DEFAULT 0      -- incoming only; used by the agent's get_new_replies.
                                   -- The dashboard NEVER writes this column.
    vonage_message_id TEXT NULL    -- for the delivery receipt webhook
    created_at TEXT (UTC), updated_at TEXT (UTC)

opt_outs
    id INTEGER PK, phone TEXT (E.164), user_id INTEGER NULL (NULL = opted out of
    everyone), created_at TEXT

sessions (new)
    id INTEGER PK, user_id INTEGER, token_hash TEXT UNIQUE (sha256 hex),
    created_at TEXT, expires_at TEXT

login_codes (new)
    id INTEGER PK, phone TEXT, code_hash TEXT, created_at TEXT, expires_at TEXT,
    attempts INTEGER DEFAULT 0, consumed_at TEXT NULL

All times are stored as UTC text 'YYYY-MM-DD HH:MM:SS' (SQLite CURRENT_TIMESTAMP
format) and returned to the API as ISO 8601 with a trailing Z.

A message with contact_id NULL is matched to a contact at query time when the
user has a contact with the same number (see _UM), so saving an unknown number
as a contact moves its thread without rewriting messages.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

log = logging.getLogger("dialatext.dashboard")

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Connection and migrations
# ---------------------------------------------------------------------------


def db_path() -> str:
    return os.getenv("DASHBOARD_DB_PATH") or str(REPO_ROOT / "dev.db")


_init_lock = threading.Lock()
_initialised: set[str] = set()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open a connection, run migrations once per process, commit on success."""
    path = db_path()
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        if path not in _initialised:
            with _init_lock:
                if path not in _initialised:
                    migrate(conn)
                    _initialised.add(path)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_CREATE = [
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT NOT NULL UNIQUE,
        name TEXT,
        preferred_service TEXT NOT NULL DEFAULT 'sms',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        aliases TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        contact_id INTEGER,
        other_number TEXT,
        text TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        contact_id INTEGER,
        other_number TEXT NOT NULL,
        direction TEXT NOT NULL CHECK (direction IN ('out','in')),
        text TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'queued',
        parts INTEGER NOT NULL DEFAULT 1,
        encoding TEXT NOT NULL DEFAULT 'GSM-7',
        is_read INTEGER NOT NULL DEFAULT 0,
        vonage_message_id TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS opt_outs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT NOT NULL,
        user_id INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        token_hash TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        expires_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS login_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT NOT NULL,
        code_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        expires_at TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        consumed_at TEXT
    )""",
]

# Columns the dashboard needs on tables that may already exist with an older
# shape. (column, ALTER TABLE type/default, optional backfill SQL). SQLite's
# ADD COLUMN can't default to CURRENT_TIMESTAMP, so timestamps are backfilled.
_NOW_BACKFILL = "UPDATE {t} SET {c} = CURRENT_TIMESTAMP WHERE {c} IS NULL"
_REQUIRED_COLUMNS: dict[str, list[tuple[str, str, str | None]]] = {
    "users": [
        ("name", "TEXT", None),
        ("preferred_service", "TEXT NOT NULL DEFAULT 'sms'", None),
        ("created_at", "TEXT", _NOW_BACKFILL),
    ],
    "contacts": [
        ("aliases", "TEXT NOT NULL DEFAULT '[]'", None),
        ("created_at", "TEXT", _NOW_BACKFILL),
        ("updated_at", "TEXT", _NOW_BACKFILL),
    ],
    "drafts": [
        ("contact_id", "INTEGER", None),
        ("other_number", "TEXT", None),
        ("status", "TEXT NOT NULL DEFAULT 'pending'", None),
        ("created_at", "TEXT", _NOW_BACKFILL),
    ],
    "messages": [
        ("contact_id", "INTEGER", None),
        ("other_number", "TEXT NOT NULL DEFAULT ''", None),
        ("direction", "TEXT NOT NULL DEFAULT 'out'", None),
        ("text", "TEXT NOT NULL DEFAULT ''", None),
        ("status", "TEXT NOT NULL DEFAULT 'queued'", None),
        ("parts", "INTEGER NOT NULL DEFAULT 1", None),
        ("encoding", "TEXT NOT NULL DEFAULT 'GSM-7'", None),
        ("is_read", "INTEGER NOT NULL DEFAULT 0", None),
        ("vonage_message_id", "TEXT", None),
        ("created_at", "TEXT", _NOW_BACKFILL),
        ("updated_at", "TEXT", _NOW_BACKFILL),
    ],
    "opt_outs": [
        ("user_id", "INTEGER", None),
        ("created_at", "TEXT", _NOW_BACKFILL),
    ],
}

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_dash_messages_user_time ON messages(user_id, created_at, id)",
    "CREATE INDEX IF NOT EXISTS idx_dash_messages_vonage ON messages(vonage_message_id)",
    "CREATE INDEX IF NOT EXISTS idx_dash_contacts_user ON contacts(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_dash_login_codes_phone ON login_codes(phone, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_dash_opt_outs_phone ON opt_outs(phone)",
]


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Idempotent: safe to run any number of times, never drops data.

    Returns the list of "table.column" entries that had to be added.
    """
    for ddl in _CREATE:
        conn.execute(ddl)
    added: list[str] = []
    for table, cols in _REQUIRED_COLUMNS.items():
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, decl, backfill in cols:
            if col in existing:
                continue
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
            if backfill:
                conn.execute(backfill.format(t=table, c=col))
            added.append(f"{table}.{col}")
    for ddl in _INDEXES:
        conn.execute(ddl)
    conn.commit()
    if added:
        log.warning("Dashboard migration added columns: %s", ", ".join(added))
    return added


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

_FMT = "%Y-%m-%d %H:%M:%S"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_db_time(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime(_FMT)


def now_str() -> str:
    return to_db_time(utc_now())


def iso(value: str | None) -> str | None:
    """'2026-11-07 10:00:00' (UTC) -> '2026-11-07T10:00:00Z'."""
    if not value:
        return None
    return value[:19].replace(" ", "T") + "Z"


def _row(r: sqlite3.Row | None) -> dict | None:
    return dict(r) if r is not None else None


def _like(q: str) -> str:
    esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def _user_out(r: sqlite3.Row | dict | None) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    return {
        "id": d["id"],
        "phone": d["phone"],
        "name": d.get("name") or "",
        "preferred_service": d.get("preferred_service") or "sms",
        "created_at": iso(d.get("created_at")),
    }


def get_user_by_phone(phone: str) -> dict | None:
    with connect() as c:
        return _user_out(c.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone())


def get_user(user_id: int) -> dict | None:
    with connect() as c:
        return _user_out(c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def create_user(phone: str, name: str | None, preferred_service: str = "sms") -> dict:
    """Same row the phone agent's register_user creates; matched by phone."""
    with connect() as c:
        c.execute(
            "INSERT INTO users (phone, name, preferred_service, created_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(phone) DO NOTHING",
            (phone, name, preferred_service, now_str()),
        )
        return _user_out(c.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone())


def update_user(user_id: int, name: str | None = None, preferred_service: str | None = None) -> dict:
    with connect() as c:
        if name is not None:
            c.execute("UPDATE users SET name = ? WHERE id = ?", (name, user_id))
        if preferred_service is not None:
            c.execute("UPDATE users SET preferred_service = ? WHERE id = ?", (preferred_service, user_id))
        return _user_out(c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def fill_missing_name(user_id: int, name: str) -> None:
    """Set the name only if the user has none (e.g. they called first)."""
    with connect() as c:
        c.execute(
            "UPDATE users SET name = ? WHERE id = ? AND (name IS NULL OR name = '')",
            (name, user_id),
        )


def delete_user_and_data(user_id: int) -> None:
    """Delete the account: contacts, messages, drafts, sessions, login codes, user.

    opt_outs are kept: they record recipients who asked not to be texted.
    """
    with connect() as c:
        row = c.execute("SELECT phone FROM users WHERE id = ?", (user_id,)).fetchone()
        c.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        c.execute("DELETE FROM drafts WHERE user_id = ?", (user_id,))
        c.execute("DELETE FROM contacts WHERE user_id = ?", (user_id,))
        c.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        if row:
            c.execute("DELETE FROM login_codes WHERE phone = ?", (row["phone"],))
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))


# ---------------------------------------------------------------------------
# Login codes
# ---------------------------------------------------------------------------


def count_codes_since(phone: str, since: str) -> int:
    with connect() as c:
        return c.execute(
            "SELECT COUNT(*) FROM login_codes WHERE phone = ? AND created_at > ?", (phone, since)
        ).fetchone()[0]


def insert_login_code(phone: str, code_hash: str, expires_at: str) -> int:
    with connect() as c:
        # A new code replaces any older unused one.
        c.execute(
            "UPDATE login_codes SET consumed_at = ? WHERE phone = ? AND consumed_at IS NULL",
            (now_str(), phone),
        )
        cur = c.execute(
            "INSERT INTO login_codes (phone, code_hash, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (phone, code_hash, now_str(), expires_at),
        )
        return cur.lastrowid


def latest_open_code(phone: str) -> dict | None:
    """Most recent unconsumed code for this number (may be expired or locked)."""
    with connect() as c:
        return _row(
            c.execute(
                "SELECT * FROM login_codes WHERE phone = ? AND consumed_at IS NULL"
                " ORDER BY id DESC LIMIT 1",
                (phone,),
            ).fetchone()
        )


def add_code_attempt(code_id: int) -> int:
    with connect() as c:
        c.execute("UPDATE login_codes SET attempts = attempts + 1 WHERE id = ?", (code_id,))
        return c.execute("SELECT attempts FROM login_codes WHERE id = ?", (code_id,)).fetchone()[0]


def consume_code(code_id: int) -> None:
    with connect() as c:
        c.execute("UPDATE login_codes SET consumed_at = ? WHERE id = ?", (now_str(), code_id))


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def create_session(user_id: int, token_hash: str, expires_at: str) -> None:
    with connect() as c:
        c.execute("DELETE FROM sessions WHERE expires_at <= ?", (now_str(),))
        c.execute(
            "INSERT INTO sessions (user_id, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (user_id, token_hash, now_str(), expires_at),
        )


def user_for_session(token_hash: str) -> dict | None:
    with connect() as c:
        return _user_out(
            c.execute(
                "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id"
                " WHERE s.token_hash = ? AND s.expires_at > ?",
                (token_hash, now_str()),
            ).fetchone()
        )


def delete_session(token_hash: str) -> None:
    with connect() as c:
        c.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))


# ---------------------------------------------------------------------------
# Message helpers (shared SQL)
# ---------------------------------------------------------------------------

# Messages for one user, with the contact they belong to: the stored
# contact_id if it is this user's contact, else this user's contact with the
# same number. Always bind :uid.
_UM = """
um AS (
    SELECT m.*,
        COALESCE(
            (SELECT c.id FROM contacts c WHERE c.id = m.contact_id AND c.user_id = m.user_id),
            (SELECT c.id FROM contacts c WHERE c.user_id = m.user_id AND c.phone = m.other_number
             ORDER BY c.id LIMIT 1)
        ) AS eff_contact_id
    FROM messages m
    WHERE m.user_id = :uid
)
"""

_OPTED_OUT = (
    "EXISTS (SELECT 1 FROM opt_outs o WHERE o.phone = {phone}"
    " AND (o.user_id IS NULL OR o.user_id = :uid))"
)


def _message_out(r: sqlite3.Row) -> dict:
    d = dict(r)
    return {
        "id": d["id"],
        "contact_id": d.get("eff_contact_id"),
        "contact_name": d.get("contact_name"),
        "other_number": d["other_number"],
        "direction": d["direction"],
        "text": d["text"],
        "status": d["status"],
        "parts": d["parts"],
        "encoding": d["encoding"],
        "is_read": bool(d.get("is_read")),
        "created_at": iso(d["created_at"]),
    }


def _encode_cursor(created_at: str, msg_id: int) -> str:
    return base64.urlsafe_b64encode(f"{created_at}|{msg_id}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, int] | None:
    try:
        created_at, msg_id = base64.urlsafe_b64decode(cursor.encode()).decode().rsplit("|", 1)
        return created_at, int(msg_id)
    except Exception:
        return None


def list_messages(
    user_id: int,
    *,
    contact_id: int | None = None,
    number: str | None = None,
    direction: str | None = None,
    status: str | None = None,
    q: str | None = None,
    from_utc: str | None = None,
    to_utc: str | None = None,
    limit: int = 25,
    cursor: str | None = None,
) -> dict:
    """Flat log, newest first, keyset-paginated on (created_at, id)."""
    where = ["1=1"]
    params: dict[str, Any] = {"uid": user_id}
    if contact_id is not None:
        where.append("um.eff_contact_id = :cid")
        params["cid"] = contact_id
    if number:
        where.append("um.eff_contact_id IS NULL AND um.other_number = :num")
        params["num"] = number
    if direction:
        where.append("um.direction = :dir")
        params["dir"] = direction
    if status:
        where.append("um.status = :st")
        params["st"] = status
    if q:
        where.append(
            "(um.text LIKE :q ESCAPE '\\' OR c.name LIKE :q ESCAPE '\\' OR um.other_number LIKE :q ESCAPE '\\')"
        )
        params["q"] = _like(q)
    if from_utc:
        where.append("um.created_at >= :from_utc")
        params["from_utc"] = from_utc
    if to_utc:
        where.append("um.created_at < :to_utc")
        params["to_utc"] = to_utc

    base = f"WITH {_UM} SELECT {{cols}} FROM um LEFT JOIN contacts c ON c.id = um.eff_contact_id WHERE "
    filt = " AND ".join(where)

    page_where = filt
    if cursor:
        decoded = _decode_cursor(cursor)
        if decoded:
            page_where += " AND (um.created_at < :cc OR (um.created_at = :cc AND um.id < :ci))"
            params["cc"], params["ci"] = decoded

    with connect() as conn:
        total = conn.execute(base.format(cols="COUNT(*)") + filt, params).fetchone()[0]
        rows = conn.execute(
            base.format(cols="um.*, c.name AS contact_name")
            + page_where
            + " ORDER BY um.created_at DESC, um.id DESC LIMIT :lim",
            {**params, "lim": limit + 1},
        ).fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1]["created_at"], rows[-1]["id"]) if has_more and rows else None
    return {"items": [_message_out(r) for r in rows], "next_cursor": next_cursor, "total": total}


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------


def _contact_out(r: sqlite3.Row) -> dict:
    d = dict(r)
    try:
        aliases = json.loads(d.get("aliases") or "[]")
    except (TypeError, ValueError):
        aliases = []
    return {
        "id": d["id"],
        "name": d["name"],
        "phone": d["phone"],
        "aliases": aliases if isinstance(aliases, list) else [],
        "created_at": iso(d.get("created_at")),
        "sent_count": d.get("sent_count") or 0,
        "received_count": d.get("received_count") or 0,
        "last_activity": iso(d.get("last_activity")),
        "opted_out": bool(d.get("opted_out")),
    }


_CONTACT_SELECT = f"""
WITH {_UM},
agg AS (
    SELECT eff_contact_id AS cid,
        SUM(direction = 'out') AS sent_count,
        SUM(direction = 'in') AS received_count,
        MAX(created_at) AS last_activity
    FROM um WHERE eff_contact_id IS NOT NULL GROUP BY eff_contact_id
)
SELECT c.*, agg.sent_count, agg.received_count, agg.last_activity,
    {_OPTED_OUT.format(phone="c.phone")} AS opted_out
FROM contacts c LEFT JOIN agg ON agg.cid = c.id
WHERE c.user_id = :uid
"""


def list_contacts(user_id: int, q: str | None = None) -> list[dict]:
    sql = _CONTACT_SELECT
    params: dict[str, Any] = {"uid": user_id}
    if q:
        sql += " AND (c.name LIKE :q ESCAPE '\\' OR c.aliases LIKE :q ESCAPE '\\' OR c.phone LIKE :q ESCAPE '\\'"
        params["q"] = _like(q)
        digits = "".join(ch for ch in q if ch.isdigit()).lstrip("0")
        if len(digits) >= 3:
            sql += " OR c.phone LIKE :digits"
            params["digits"] = f"%{digits}%"
        sql += ")"
    sql += " ORDER BY c.name COLLATE NOCASE, c.id"
    with connect() as conn:
        return [_contact_out(r) for r in conn.execute(sql, params).fetchall()]


def get_contact(user_id: int, contact_id: int) -> dict | None:
    with connect() as conn:
        r = conn.execute(_CONTACT_SELECT + " AND c.id = :id", {"uid": user_id, "id": contact_id}).fetchone()
        return _contact_out(r) if r else None


def find_contact_by_phone(user_id: int, phone: str, exclude_id: int | None = None) -> dict | None:
    with connect() as conn:
        return _row(
            conn.execute(
                "SELECT id, name, phone FROM contacts WHERE user_id = ? AND phone = ? AND id != ?",
                (user_id, phone, exclude_id or -1),
            ).fetchone()
        )


def create_contact(user_id: int, name: str, phone: str, aliases: list[str]) -> dict:
    with connect() as conn:
        now = now_str()
        cur = conn.execute(
            "INSERT INTO contacts (user_id, name, phone, aliases, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, name, phone, json.dumps(aliases), now, now),
        )
        new_id = cur.lastrowid
    return get_contact(user_id, new_id)  # type: ignore[return-value]


def update_contact(user_id: int, contact_id: int, fields: dict) -> dict | None:
    sets, params = [], []
    for key in ("name", "phone"):
        if key in fields:
            sets.append(f"{key} = ?")
            params.append(fields[key])
    if "aliases" in fields:
        sets.append("aliases = ?")
        params.append(json.dumps(fields["aliases"]))
    if sets:
        sets.append("updated_at = ?")
        params.append(now_str())
        with connect() as conn:
            conn.execute(
                f"UPDATE contacts SET {', '.join(sets)} WHERE id = ? AND user_id = ?",
                (*params, contact_id, user_id),
            )
    return get_contact(user_id, contact_id)


def delete_contact(user_id: int, contact_id: int) -> bool:
    """Delete a contact. Their messages are kept (they fall back to the number)."""
    with connect() as conn:
        conn.execute(
            "UPDATE messages SET contact_id = NULL WHERE user_id = ? AND contact_id = ?",
            (user_id, contact_id),
        )
        cur = conn.execute("DELETE FROM contacts WHERE id = ? AND user_id = ?", (contact_id, user_id))
        return cur.rowcount > 0


def count_contacts(user_id: int) -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM contacts WHERE user_id = ?", (user_id,)).fetchone()[0]


# ---------------------------------------------------------------------------
# Integration helpers for the SMS sender and Vonage webhooks
# ---------------------------------------------------------------------------

_GSM7 = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
_GSM7_EXT = set("^{}\\[~]|€\f")


def sms_parts(text: str) -> tuple[int, str]:
    """Return (parts, encoding) for an SMS body, per GSM 03.38 rules."""
    if all(ch in _GSM7 or ch in _GSM7_EXT for ch in text):
        units = sum(2 if ch in _GSM7_EXT else 1 for ch in text)
        return (1 if units <= 160 else -(-units // 153)), "GSM-7"
    # UTF-16 code units: characters outside the BMP (most emoji) count twice.
    units = len(text.encode("utf-16-le")) // 2
    return (1 if units <= 70 else -(-units // 67)), "Unicode"


def record_message(
    user_id: int,
    other_number: str,
    direction: str,
    text: str,
    *,
    contact_id: int | None = None,
    status: str | None = None,
    vonage_message_id: str | None = None,
    created_at: str | None = None,
    is_read: bool = False,
) -> int:
    """Insert one message row. Intended for app/sms.py and vonage_routes.py."""
    parts, encoding = sms_parts(text)
    status = status or ("queued" if direction == "out" else "delivered")
    ts = created_at or now_str()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO messages (user_id, contact_id, other_number, direction, text, status,"
            " parts, encoding, is_read, vonage_message_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, contact_id, other_number, direction, text, status, parts, encoding,
             int(is_read), vonage_message_id, ts, ts),
        )
        return cur.lastrowid


def update_status_by_vonage_id(vonage_message_id: str, status: str) -> int | None:
    """For POST /vonage/sms/status. Returns the user_id of the message, if found."""
    with connect() as conn:
        conn.execute(
            "UPDATE messages SET status = ?, updated_at = ? WHERE vonage_message_id = ?",
            (status, now_str(), vonage_message_id),
        )
        r = conn.execute(
            "SELECT user_id FROM messages WHERE vonage_message_id = ?", (vonage_message_id,)
        ).fetchone()
        return r["user_id"] if r else None

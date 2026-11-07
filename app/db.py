"""The one storage layer for Dial-a-Text (stdlib sqlite3).

Rules:
- Every module uses get_conn() or the helpers below; nobody opens their own
  SQLite connection, and record_message() is the only way rows reach messages.
- Times are UTC ISO-8601 strings from now_utc(), e.g. "2026-11-07T13:45:00.123Z".
- Phone numbers are stored as E.164 with a "+" (helpers normalise via to_e164).
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv

from app.phone import to_e164

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = 1

# Same format as now_utc(), so SQL defaults and Python timestamps sort together.
_NOW_SQL = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"

TABLES = ["users", "contacts", "drafts", "messages", "opt_outs", "sessions", "login_codes"]

SCHEMA = [
    f"""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        phone TEXT NOT NULL UNIQUE,
        name TEXT,
        preferred_service TEXT NOT NULL DEFAULT 'sms',
        is_demo INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT {_NOW_SQL},
        last_call_at TEXT
    )""",
    f"""CREATE TABLE IF NOT EXISTS contacts (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        aliases TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL DEFAULT {_NOW_SQL},
        UNIQUE (user_id, phone)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_contacts_user ON contacts(user_id)",
    f"""CREATE TABLE IF NOT EXISTS drafts (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        conversation_id TEXT,
        contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
        to_number TEXT NOT NULL,
        text TEXT NOT NULL,
        parts INTEGER NOT NULL DEFAULT 1,
        encoding TEXT NOT NULL DEFAULT 'GSM-7',
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'sent', 'cancelled', 'expired')),
        created_at TEXT NOT NULL DEFAULT {_NOW_SQL},
        sent_at TEXT
    )""",
    f"""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
        other_number TEXT NOT NULL,
        direction TEXT NOT NULL CHECK (direction IN ('out', 'in')),
        text TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued'
            CHECK (status IN ('queued', 'sent', 'delivered', 'failed')),
        parts INTEGER NOT NULL DEFAULT 1,
        encoding TEXT NOT NULL DEFAULT 'GSM-7',
        provider_message_id TEXT,
        draft_id TEXT,
        conversation_id TEXT,
        read_by_agent INTEGER NOT NULL DEFAULT 0,
        error TEXT,
        created_at TEXT NOT NULL DEFAULT {_NOW_SQL},
        updated_at TEXT NOT NULL DEFAULT {_NOW_SQL}
    )""",
    "CREATE INDEX IF NOT EXISTS idx_messages_user_created ON messages(user_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_messages_user_number ON messages(user_id, other_number)",
    "CREATE INDEX IF NOT EXISTS idx_messages_provider_id ON messages(provider_message_id)",
    f"""CREATE TABLE IF NOT EXISTS opt_outs (
        phone TEXT PRIMARY KEY,
        created_at TEXT NOT NULL DEFAULT {_NOW_SQL}
    )""",
    f"""CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL DEFAULT {_NOW_SQL},
        expires_at TEXT NOT NULL
    )""",
    f"""CREATE TABLE IF NOT EXISTS login_codes (
        id INTEGER PRIMARY KEY,
        phone TEXT NOT NULL,
        code_hash TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT {_NOW_SQL}
    )""",
    "CREATE INDEX IF NOT EXISTS idx_login_codes_phone ON login_codes(phone)",
]

# Future additive columns go here as (table, column, declaration). Never drop or rename.
EXTRA_COLUMNS: list[tuple[str, str, str]] = []


# --- basics -----------------------------------------------------------------


def now_utc() -> str:
    """Current UTC time as an ISO-8601 string with millisecond precision and a Z."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def db_path() -> Path:
    """Database file from DATABASE_PATH (default data/dialatext.db), folder created."""
    path = Path(os.getenv("DATABASE_PATH") or "data/dialatext.db")
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """Yield a connection; commit on success, roll back on error, always close."""
    conn = sqlite3.connect(db_path(), timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> bool:
    """Add a column if it's missing (additive migrations only). Returns True if added."""
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column in cols:
        return False
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    except sqlite3.OperationalError as exc:  # another process got there first
        if "duplicate column" not in str(exc).lower():
            raise
        return False
    return True


def init_db() -> None:
    """Create tables and indexes if missing; safe on every startup and from several processes."""
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")  # serialise concurrent initialisers
        for stmt in SCHEMA:
            conn.execute(stmt)
        for table, column, decl in EXTRA_COLUMNS:
            ensure_column(conn, table, column, decl)
        if conn.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _e164_or_raise(phone: str) -> str:
    e164 = to_e164(phone)
    if not e164:
        raise ValueError(f"Not a valid phone number: {phone!r}")
    return e164


# --- users ------------------------------------------------------------------


def get_or_create_user(phone: str, name: str | None = None) -> dict:
    """Return the user for this number, creating it (and filling a missing name) if needed."""
    e164 = _e164_or_raise(phone)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (phone, name, created_at) VALUES (?, ?, ?) ON CONFLICT(phone) DO NOTHING",
            (e164, name, now_utc()),
        )
        if name:
            conn.execute(
                "UPDATE users SET name = ? WHERE phone = ? AND (name IS NULL OR name = '')", (name, e164)
            )
        return dict(conn.execute("SELECT * FROM users WHERE phone = ?", (e164,)).fetchone())


# --- drafts -----------------------------------------------------------------


def create_draft(
    user_id: int,
    conversation_id: str,
    to_number: str,
    text: str,
    parts: int,
    encoding: str,
    contact_id: int | None = None,
) -> dict:
    """Store a pending draft for this call and return it."""
    draft_id = uuid.uuid4().hex
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO drafts (id, user_id, conversation_id, contact_id, to_number, text, parts, encoding, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (draft_id, user_id, conversation_id, contact_id, _e164_or_raise(to_number), text, parts, encoding, now_utc()),
        )
        return dict(conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone())


def claim_draft(draft_id: str, conversation_id: str) -> dict | None:
    """Atomically mark a pending draft from this conversation as sent; None if already claimed or not ours."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE drafts SET status = 'sent', sent_at = ?"
            " WHERE id = ? AND status = 'pending' AND conversation_id = ?",
            (now_utc(), draft_id, conversation_id),
        )
        if cur.rowcount != 1:
            return None
        # Still inside the same write transaction, so nobody else can change it in between.
        return dict(conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone())


# --- messages ---------------------------------------------------------------


def record_message(
    user_id: int,
    other_number: str,
    direction: str,
    text: str,
    status: str = "queued",
    parts: int = 1,
    encoding: str = "GSM-7",
    provider_message_id: str | None = None,
    draft_id: str | None = None,
    conversation_id: str | None = None,
    contact_id: int | None = None,
) -> int:
    """Insert a message (the ONLY way messages are written) and return its id; fills contact_id by number."""
    number = _e164_or_raise(other_number)
    now = now_utc()
    with get_conn() as conn:
        if contact_id is None:
            row = conn.execute(
                "SELECT id FROM contacts WHERE user_id = ? AND phone = ?", (user_id, number)
            ).fetchone()
            contact_id = row["id"] if row else None
        cur = conn.execute(
            "INSERT INTO messages (user_id, contact_id, other_number, direction, text, status, parts, encoding,"
            " provider_message_id, draft_id, conversation_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, contact_id, number, direction, text, status, parts, encoding,
             provider_message_id, draft_id, conversation_id, now, now),
        )
        return cur.lastrowid


def set_message_status(provider_message_id: str, status: str, error: str | None = None) -> bool:
    """Update a message's status (and error) by the provider's message id; True if a row changed."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE messages SET status = ?, error = COALESCE(?, error), updated_at = ?"
            " WHERE provider_message_id = ?",
            (status, error, now_utc(), provider_message_id),
        )
        return cur.rowcount > 0


def unread_replies(user_id: int) -> list[dict]:
    """Incoming messages the phone agent hasn't read yet, oldest first, with contact_name."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT m.*, c.name AS contact_name FROM messages m"
            " LEFT JOIN contacts c ON c.id = m.contact_id"
            " WHERE m.user_id = ? AND m.direction = 'in' AND m.read_by_agent = 0"
            " ORDER BY m.created_at, m.id",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_replies_read(user_id: int, up_to_id: int | None = None) -> int:
    """Mark the user's unread replies as read by the agent (optionally only ids <= up_to_id); returns count."""
    sql = "UPDATE messages SET read_by_agent = 1 WHERE user_id = ? AND direction = 'in' AND read_by_agent = 0"
    params: list = [user_id]
    if up_to_id is not None:
        sql += " AND id <= ?"
        params.append(up_to_id)
    with get_conn() as conn:
        return conn.execute(sql, params).rowcount


# --- opt-outs ---------------------------------------------------------------


def is_opted_out(phone: str) -> bool:
    """True if this number replied STOP (or was otherwise opted out)."""
    e164 = to_e164(phone)
    if not e164:
        return False
    with get_conn() as conn:
        return conn.execute("SELECT 1 FROM opt_outs WHERE phone = ?", (e164,)).fetchone() is not None


def set_opt_out(phone: str, opted_out: bool) -> None:
    """Opt a number out (STOP) or back in (START)."""
    e164 = _e164_or_raise(phone)
    with get_conn() as conn:
        if opted_out:
            conn.execute(
                "INSERT INTO opt_outs (phone, created_at) VALUES (?, ?) ON CONFLICT(phone) DO NOTHING",
                (e164, now_utc()),
            )
        else:
            conn.execute("DELETE FROM opt_outs WHERE phone = ?", (e164,))

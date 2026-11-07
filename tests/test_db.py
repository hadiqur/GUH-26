import sqlite3
import threading

import pytest

HADI = "07700 900001"
MUM = "+447700900101"


def table_names(db):
    with db.get_conn() as conn:
        return {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_init_db_twice_is_fine(db):
    db.init_db()
    db.init_db()
    assert set(db.TABLES) <= table_names(db)
    with db.get_conn() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_init_db_concurrently(db):
    errors = []

    def run():
        try:
            db.init_db()
        except Exception as exc:  # pragma: no cover - only on failure
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_ensure_column_is_additive_and_idempotent(db):
    with db.get_conn() as conn:
        assert db.ensure_column(conn, "users", "nickname", "TEXT") is True
        assert db.ensure_column(conn, "users", "nickname", "TEXT") is False


def test_get_or_create_user_normalises_and_reuses(db):
    first = db.get_or_create_user(HADI)
    assert first["phone"] == "+447700900001"
    assert first["preferred_service"] == "sms"
    again = db.get_or_create_user("447700900001", name="Hadi")  # Vonage format
    assert again["id"] == first["id"]
    assert again["name"] == "Hadi"  # missing name filled in
    assert db.get_or_create_user(HADI, name="Someone else")["name"] == "Hadi"  # not overwritten
    with pytest.raises(ValueError):
        db.get_or_create_user("not a number")


def test_now_utc_format(db):
    ts = db.now_utc()
    assert ts.endswith("Z") and "T" in ts and len(ts) == 24


def test_claim_draft_once_only(db):
    user = db.get_or_create_user(HADI)
    draft = db.create_draft(user["id"], "conv-1", "07700 900101", "Hi Mum", 1, "GSM-7")
    assert draft["status"] == "pending" and draft["to_number"] == MUM

    assert db.claim_draft(draft["id"], "conv-OTHER") is None  # wrong call
    claimed = db.claim_draft(draft["id"], "conv-1")
    assert claimed["status"] == "sent" and claimed["sent_at"]
    assert db.claim_draft(draft["id"], "conv-1") is None  # second claim
    assert db.claim_draft("no-such-draft", "conv-1") is None


def test_claim_draft_races_have_one_winner(db):
    user = db.get_or_create_user(HADI)
    draft = db.create_draft(user["id"], "conv-1", MUM, "Hi", 1, "GSM-7")
    wins = []
    threads = [threading.Thread(target=lambda: wins.append(db.claim_draft(draft["id"], "conv-1"))) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for w in wins if w) == 1


def test_record_message_fills_contact_id(db):
    user = db.get_or_create_user(HADI)
    with db.get_conn() as conn:
        contact_id = conn.execute(
            "INSERT INTO contacts (user_id, name, phone) VALUES (?, 'Mum', ?)", (user["id"], MUM)
        ).lastrowid
    known = db.record_message(user["id"], "447700900101", "out", "Hi Mum")  # Vonage format
    unknown = db.record_message(user["id"], "07700 900555", "in", "Who's this?")
    with db.get_conn() as conn:
        rows = {r["id"]: r for r in conn.execute("SELECT * FROM messages")}
    assert rows[known]["contact_id"] == contact_id
    assert rows[known]["other_number"] == MUM
    assert rows[known]["status"] == "queued" and rows[known]["read_by_agent"] == 0
    assert rows[unknown]["contact_id"] is None


def test_record_message_rejects_bad_values(db):
    user = db.get_or_create_user(HADI)
    with pytest.raises(sqlite3.IntegrityError):
        db.record_message(user["id"], MUM, "sideways", "x")
    with pytest.raises(sqlite3.IntegrityError):
        db.record_message(user["id"], MUM, "out", "x", status="lost")
    with pytest.raises(ValueError):
        db.record_message(user["id"], "garbage", "out", "x")


def test_set_message_status_updates_row(db):
    user = db.get_or_create_user(HADI)
    msg_id = db.record_message(user["id"], MUM, "out", "Hi", provider_message_id="vonage-123")
    with db.get_conn() as conn:
        before = conn.execute("SELECT updated_at FROM messages WHERE id = ?", (msg_id,)).fetchone()[0]

    assert db.set_message_status("vonage-123", "delivered") is True
    assert db.set_message_status("vonage-missing", "delivered") is False
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
    assert row["status"] == "delivered"
    assert row["updated_at"] >= before

    db.set_message_status("vonage-123", "failed", error="Unreachable")
    with db.get_conn() as conn:
        row = conn.execute("SELECT status, error FROM messages WHERE id = ?", (msg_id,)).fetchone()
    assert (row["status"], row["error"]) == ("failed", "Unreachable")


def test_unread_replies_then_mark_read(db):
    user = db.get_or_create_user(HADI)
    other = db.get_or_create_user("07700 900002")
    db.record_message(user["id"], MUM, "out", "Hi Mum")
    r1 = db.record_message(user["id"], MUM, "in", "Hello love")
    r2 = db.record_message(user["id"], "07700 900102", "in", "Hi son")
    db.record_message(other["id"], MUM, "in", "Not yours")

    replies = db.unread_replies(user["id"])
    assert [r["id"] for r in replies] == [r1, r2]  # oldest first, only incoming, only this user

    assert db.mark_replies_read(user["id"], up_to_id=r1) == 1
    assert [r["id"] for r in db.unread_replies(user["id"])] == [r2]
    assert db.mark_replies_read(user["id"]) == 1
    assert db.unread_replies(user["id"]) == []
    assert db.mark_replies_read(user["id"]) == 0
    assert len(db.unread_replies(other["id"])) == 1  # other user untouched


def test_opt_outs(db):
    assert db.is_opted_out(MUM) is False
    db.set_opt_out("447700900101", True)
    db.set_opt_out(MUM, True)  # idempotent
    assert db.is_opted_out("07700 900101") is True
    db.set_opt_out(MUM, False)
    assert db.is_opted_out(MUM) is False
    assert db.is_opted_out("garbage") is False


def test_get_conn_rolls_back_on_error(db):
    with pytest.raises(RuntimeError):
        with db.get_conn() as conn:
            conn.execute("INSERT INTO users (phone) VALUES ('+447700900999')")
            raise RuntimeError("boom")
    with db.get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_healthz(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:  # runs the startup hook (init_db)
        assert client.get("/healthz").json() == {"ok": True}

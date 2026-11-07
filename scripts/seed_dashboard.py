"""Seed demo data for the Dial-a-Text dashboard.

    python scripts/seed_dashboard.py           # add anything missing (idempotent)
    python scripts/seed_dashboard.py --reset   # wipe the demo users and re-seed
                                               # (refreshes "2 min ago" times)

Only Ofcom's reserved drama numbers (07700 900000 to 07700 900999) are used,
so nobody real can ever be texted. Writes to the same DB as the dashboard
(DASHBOARD_DB_PATH, default ./dev.db).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import dashboard_data as data  # noqa: E402
from app.auth import DEMO_PHONE  # noqa: E402

D, H, M = (lambda n: timedelta(days=n)), (lambda n: timedelta(hours=n)), (lambda n: timedelta(minutes=n))

UNKNOWN = "+447700900555"

USERS = {
    "hadi": {
        "phone": DEMO_PHONE,
        "name": "Hadi",
        "joined_ago": D(12),
        "contacts": {
            "mum": ("Mum", "+447700900101", ["Mom", "Mam", "Mother"]),
            "dad": ("Dad", "+447700900102", ["Father", "Pops"]),
            "sarah_uni": ("Sarah (Uni)", "+447700900103", ["Sarah", "Uni Sarah"]),
            "sarah_work": ("Sarah (Work)", "+447700900104", ["Sarah", "Work Sarah"]),
            "alex": ("Alex", "+447700900105", []),
            "jordan": ("Jordan", "+447700900106", ["Jord"]),
        },
        "opt_outs": ["+447700900106"],
        # (how long ago, contact key or None for unknown, direction, text, status, is_read)
        "messages": [
            (D(9) + H(20), "mum", "out", "Hi Mum, I'll be round on Sunday for lunch. Do you need me to bring anything?", "delivered", 0),
            (D(9) + H(19), "mum", "in", "Lovely! Just bring yourself. And maybe some milk x", "delivered", 1),
            (D(9) + H(3), "dad", "out", "Dad, did you get the parcel I sent?", "delivered", 0),
            (D(8) + H(22), "dad", "in", "Yes thanks son, it came this morning. The postman left it with next door.", "delivered", 1),
            (D(8) + H(5), "sarah_uni", "out", "Are we still on for the library on Thursday?", "delivered", 0),
            (D(8) + H(4), "sarah_uni", "in", "Yes! 2pm by the front desk", "delivered", 1),
            (D(7) + H(6), "alex", "out", "Fancy watching the match on Saturday?", "delivered", 0),
            (D(7) + H(2), "alex", "in", "Go on then. Yours or mine?", "delivered", 1),
            (D(7) + H(1), "alex", "out", "Mine. Bring snacks.", "delivered", 0),
            (D(6) + H(8), "sarah_work", "out", "Running 10 minutes late for the 9am, sorry. Start without me.", "delivered", 0),
            (D(6) + H(7) + M(55), "sarah_work", "in", "No worries, we'll save you a coffee", "delivered", 1),
            (D(6) + H(1), "jordan", "out", "Hi Jordan, are you coming to the quiz night on Friday?", "delivered", 0),
            (D(6) + M(30), "jordan", "in", "STOP", "delivered", 1),
            (D(5) + H(10), "mum", "out",
             "Happy birthday Mum! 🎂🎉 Hope you have a wonderful day. I've booked the table at Luigi's "
             "for 7pm, Dad knows. Love you lots ❤️ see you tonight", "delivered", 0),
            (D(5) + H(9), "mum", "in", "Thank you darling! What a lovely surprise 😊", "delivered", 1),
            (D(4) + H(7), "dad", "out", "Can you pick me up from the station at 6?", "delivered", 0),
            (D(4) + H(6), "dad", "in", "Will do. Platform 2?", "delivered", 1),
            (D(4) + H(5), "dad", "out", "Yes, platform 2. Thanks Dad.", "delivered", 0),
            (D(3) + H(9), "alex", "out", "Did you leave your jacket at mine?", "failed", 0),
            (D(3) + H(8), "alex", "out", "Did you leave your jacket at mine?", "delivered", 0),
            (D(3) + H(4), "alex", "in", "Ha, yes! I'll grab it tomorrow", "delivered", 1),
            (D(2) + H(11), "sarah_uni", "out", "Can you send me the notes from today's lecture?", "delivered", 0),
            (D(2) + H(10), "sarah_uni", "in", "Sent them to your email. The exam is on the 20th by the way", "delivered", 1),
            (D(2) + H(2), None, "in", "Hi, is this Hadi? It's Tom from the football club. Alex gave me your number.", "delivered", 0),
            (D(1) + H(9), "mum", "out", "Remember your doctor's appointment tomorrow at 10.", "delivered", 0),
            (D(1) + H(8), "mum", "in", "I hadn't forgotten! Dad's taking me.", "delivered", 1),
            (D(1) + H(3), "sarah_work", "out", "Can we move our one-to-one to Friday?", "delivered", 0),
            (H(20), "sarah_work", "in", "Friday works. 11am?", "delivered", 0),
            (H(3), "dad", "out", "Are you watching the news? Ring me later.", "sent", 0),
            (H(2), "mum", "out", "On my way, see you in 20 minutes", "sent", 0),
            (M(40), "mum", "in", "Kettle's on! x", "delivered", 0),
            (M(10), "alex", "out", "Running late, save me a seat", "queued", 0),
        ],
    },
    # A second account, so you can check one user never sees another's data.
    "priya": {
        "phone": "+447700900002",
        "name": "Priya",
        "joined_ago": D(3),
        "contacts": {"ben": ("Ben", "+447700900201", ["Benny"])},
        "opt_outs": [],
        "messages": [
            (D(1) + H(2), "ben", "out", "Dinner at 8?", "delivered", 0),
            (D(1) + H(1), "ben", "in", "Perfect, see you there", "delivered", 0),
        ],
    },
}


def seed(reset: bool = False) -> None:
    now = data.utc_now()
    with data.connect() as conn:
        if reset:
            for spec in USERS.values():
                row = conn.execute("SELECT id FROM users WHERE phone = ?", (spec["phone"],)).fetchone()
                if row:
                    uid = row["id"]
                    for table in ("messages", "drafts", "contacts", "sessions"):
                        conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM opt_outs WHERE phone LIKE '+447700900%'")

        for key, spec in USERS.items():
            conn.execute(
                "INSERT INTO users (phone, name, preferred_service, created_at) VALUES (?, ?, 'sms', ?)"
                " ON CONFLICT(phone) DO NOTHING",
                (spec["phone"], spec["name"], data.to_db_time(now - spec["joined_ago"])),
            )
            uid = conn.execute("SELECT id FROM users WHERE phone = ?", (spec["phone"],)).fetchone()["id"]

            contact_ids: dict[str, int] = {}
            for ckey, (name, phone, aliases) in spec["contacts"].items():
                row = conn.execute(
                    "SELECT id FROM contacts WHERE user_id = ? AND phone = ?", (uid, phone)
                ).fetchone()
                if row is None:
                    ts = data.to_db_time(now - spec["joined_ago"])
                    row_id = conn.execute(
                        "INSERT INTO contacts (user_id, name, phone, aliases, created_at, updated_at)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        (uid, name, phone, json.dumps(aliases), ts, ts),
                    ).lastrowid
                else:
                    row_id = row["id"]
                contact_ids[ckey] = row_id

            for phone in spec["opt_outs"]:
                if not conn.execute("SELECT 1 FROM opt_outs WHERE phone = ?", (phone,)).fetchone():
                    conn.execute(
                        "INSERT INTO opt_outs (phone, user_id, created_at) VALUES (?, NULL, ?)",
                        (phone, data.to_db_time(now - D(6))),
                    )

            for i, (ago, ckey, direction, text, status, is_read) in enumerate(spec["messages"], 1):
                seed_id = f"seed-{key}-{i:02d}"
                if conn.execute("SELECT 1 FROM messages WHERE vonage_message_id = ?", (seed_id,)).fetchone():
                    continue
                number = spec["contacts"][ckey][1] if ckey else UNKNOWN
                parts, encoding = data.sms_parts(text)
                ts = data.to_db_time(now - ago)
                conn.execute(
                    "INSERT INTO messages (user_id, contact_id, other_number, direction, text, status,"
                    " parts, encoding, is_read, vonage_message_id, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (uid, contact_ids.get(ckey) if ckey else None, number, direction, text, status,
                     parts, encoding, is_read, seed_id, ts, ts),
                )
        counts = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("users", "contacts", "messages", "opt_outs")
        }
    print(f"Seeded {data.db_path()}: {counts}")
    print(f"Demo user: Hadi, {DEMO_PHONE} (07700 900001)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="wipe the demo users' data and re-seed")
    seed(reset=parser.parse_args().reset)

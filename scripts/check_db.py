"""Quick look at the database:  python scripts/check_db.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import TABLES, db_path, get_conn, init_db  # noqa: E402

init_db()
print(f"Database: {db_path()}\n")
with get_conn() as conn:
    print("Row counts:")
    for table in TABLES:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:<12} {count}")

    print("\nLast 5 messages:")
    rows = conn.execute(
        "SELECT id, user_id, direction, other_number, status, created_at, text"
        " FROM messages ORDER BY created_at DESC, id DESC LIMIT 5"
    ).fetchall()
    if not rows:
        print("  (none)")
    for r in rows:
        text = r["text"] if len(r["text"]) <= 50 else r["text"][:47] + "..."
        print(f"  #{r['id']} user {r['user_id']} {r['direction']:<3} {r['other_number']} "
              f"{r['status']:<9} {r['created_at']}  {text!r}")

    orphans = conn.execute("SELECT COUNT(*) FROM messages WHERE user_id IS NULL").fetchone()[0]
    print(f"\nMessages with NULL user_id: {orphans}")

# Dial-a-Text

## Database

- All storage goes through `app/db.py`: `get_conn()` for queries, and the helpers
  (`get_or_create_user`, `create_draft`, `claim_draft`, `record_message`,
  `set_message_status`, `unread_replies`, `mark_replies_read`, `is_opted_out`,
  `set_opt_out`) for the common operations.
- All phone number handling goes through `app/phone.py` (`to_e164`, `is_uk_mobile`).
  Numbers are stored as E.164 with a `+`, e.g. `+447700900123`.
- No other module opens its own SQLite connection, and nothing inserts into
  `messages` directly: `record_message()` is the only way in.
- `claim_draft()` is what makes sending once-only: call it, and send the SMS only
  if it returns a draft.
- Times are UTC ISO-8601 strings from `db.now_utc()` (e.g. `2026-11-07T13:45:00.123Z`).
- Schema changes are additive only: new tables with `CREATE TABLE IF NOT EXISTS`,
  new columns via `EXTRA_COLUMNS` / `ensure_column()`. Never drop or rename.
  `init_db()` runs on every startup and is safe to run from several processes.
- Database file: `DATABASE_PATH` (default `data/dialatext.db`, git-ignored).
  `python scripts/init_db.py` creates it; `python scripts/check_db.py` shows what's in it.
- Use Ofcom drama numbers (07700 900000 to 07700 900999) in tests and seed data.
- Known exception to migrate: `app/dashboard_data.py` still uses its own `dev.db`
  connection and schema; it should move onto `app/db.py`.

# Google Sheet seed data

One Google Sheet with three tabs: `users`, `contacts`, `reminders`. The column
names must match exactly, because the n8n workflows look them up by name.

## Import

1. Create a Google Sheet. For each CSV: **File > Import > Upload**, choose
   **Insert new sheet(s)**, then rename the tab to `users`, `contacts` or `reminders`.
2. **Untick "Convert text to numbers, dates and formulas"**. Otherwise Sheets
   turns `+447700900123` into the number `447700900123`. The snippets cope
   (they run every number through `toE164`), but keep the `+` so the Sheet
   is easy to read on the projector.
3. Connect the Sheet in n8n (Google Sheets credential), and share it with that account.

## Real demo data stays out of git

The CSVs only use Ofcom drama numbers (07700 900000 to 07700 900999) and
`@example.com` emails, because this repo is public. Before the demo, replace
those placeholders **in the Sheet itself** with the real teammates who agreed
to play Mum, Dad, Sarah Khan and Sarah Lee, and with the demo caller's real
number in place of Adam's. Never commit those details. If you need a local
copy, save it as `*.local.csv` (git-ignored).

Keep both Sarahs: they make the "Which Sarah?" moment in the demo. Priya and
Ben are a second account, to show one caller never sees another's contacts.

# Brick backend (live)

The running Brick system: n8n Cloud workflows, the ElevenLabs voice agent, and the web dashboard. Everything is generated from the scripts in this folder, so edit here and push, never by hand in the n8n or ElevenLabs UI.

## Files

| File | What it does |
| --- | --- |
| `build.py` | Generates every n8n workflow and pushes them to n8n through its API (create or update by name, then activate). Standard library only. |
| `elevenlabs.py` | Creates or updates the "Brick" ElevenLabs agent and its 6 webhook tools. |
| `dashboard/index.html` | The web dashboard. `build.py` embeds it in the `Brick - Dashboard app` workflow, so n8n serves it at `/webhook/brick/app`. |
| `config.example.json` | Template for `config.json` (secrets, IDs). Copy it and fill it in. `config.json` is git-ignored. |
| `PRODUCT.md` | Product and design brief for the dashboard. |

## Run it

```bash
cp config.example.json config.json   # then fill in the values
python3 build.py            # writes workflows/*.json only
python3 build.py --push     # also creates/updates and activates them in n8n
python3 elevenlabs.py       # upserts the ElevenLabs agent and tools
```

`workflows/` is generated output and contains the secrets, so it is git-ignored too.

## How it fits together

```
Phone --call--> Vonage number --answer webhook--> n8n (NCCO) --SIP--> ElevenLabs agent
                                                                     | tool calls (X-Tool-Secret)
                                                                     v
                         Google Sheet "Brick data" <--> n8n workflows --> Gmail / Vonage SMS
Dashboard (served by n8n at /webhook/brick/app) --> n8n endpoints (SMS-code login, session token)
```

- **Storage:** a Google Sheet with tabs `users` (phone, name, created_at, email_connected, email_signature, allow_international), `contacts` (owner_phone, name, aliases, phone, email) and `reminders`.
- **Preferences** live in the `users` tab, so changing them needs no push. `email_connected` = TRUE lets that caller use the one connected Gmail.
- **Login:** the dashboard texts a 6-digit code; codes and 7-day session tokens are HMACs of the tool secret, so nothing extra is stored.
- **Reminders** are an n8n Wait node, so they fire even when every laptop is closed.

## Endpoints (base `https://<instance>.app.n8n.cloud/webhook`)

Agent tools (header `X-Tool-Secret`): `POST /brick/tools/send-email`, `/brick/tools/send-text`, `/brick/tools/set-reminder`, `/brick/tools/read-emails`, `/brick/contacts`, `/brick/register`. Call setup: `GET /brick/vonage/answer`, `POST /brick/vonage/event`, `POST /brick/init`.

Dashboard (session `token` in body or query, or the tool secret): `POST /brick/auth/request-code`, `POST /brick/auth/verify`, `GET /brick/dashboard`, `POST /brick/me`, `POST /brick/contacts`, `POST /brick/contacts/update`, `POST /brick/contacts/delete`, `GET /brick/app`.

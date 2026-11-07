# n8n workflows

Built in the n8n cloud UI, in this order (from `docs/PLAN.md`). Each starts with
a Webhook node set to respond **Using Respond to Webhook node**. Every tool
webhook checks the `X-Tool-Secret` header. Activate each workflow and use the
**production** webhook URLs, not the test ones. Update the status as you go.

| # | workflow | method | snippets (`n8n/code/`) | status |
|---|---|---|---|---|
| 1 | `vonage-answer` | GET | `normalise-phone.js` + `build-ncco.js` | not started |
| 2 | `init` | POST | `normalise-phone.js` + `build-init.js` | not started |
| 3 | `send_email` | POST, tool | `normalise-phone.js` + `find-contact.js` | not started |
| 4 | `set_reminder` | POST, tool | `reminder.js`, then `sms-clean.js` | not started |
| 5 | `send_text` | POST, tool | `normalise-phone.js` + `find-contact.js`, then `sms-clean.js` | not started |
| opt | `register_user` | POST, tool | `normalise-phone.js` | not started |
| opt | `read_emails` | POST, tool | none | not started |
| opt | `vonage-inbound-sms` | POST | `normalise-phone.js` + `find-contact.js`, `sms-clean.js` | not started |

Status: `not started / built / curl-tested / connected to agent`.
`node scripts/test-webhooks.mjs` checks 1, 2, 3 and 5 and the secret on every tool.

## 1. vonage-answer (GET)
- [ ] Vonage calls this when someone rings the number. Query params include `from` (caller), `to` and `uuid`.
- [ ] If `from` is empty or withheld: respond with a talk action, "Sorry, I can't see your number. Please call again without hiding it."
- [ ] Otherwise: respond with a connect action to ElevenLabs over SIP, headers `CALLER-ID` and `CALL-ID` (Vonage passes them on as `X-` headers).
- [ ] If SIP fails by 15:00: try UDP on port 5060 (`transport: "udp"` in `buildNcco`), then the Vonage–ElevenLabs websocket connector.

## 2. init (POST)
- [ ] ElevenLabs calls this at the start of every call, with the caller ID.
- [ ] Look the caller up in the Sheet (`users`, `contacts` tabs) and return the dynamic variables `caller_phone`, `user_name`, `is_new_user`, `contact_names`, `now`.
- [ ] Unknown number: `is_new_user: true`, `user_name: ""`.

## 3. send_email (POST, tool)
- [ ] Inputs: `caller_phone` (from the dynamic variable, never the model), `contact_name`, `subject`, `body`.
- [ ] Look up the contact's email in the Sheet. Not found: return `{"status":"not_found"}`.
- [ ] Gmail node, send. Return `{"status":"sent","to":"Sarah Khan"}`.

## 4. set_reminder (POST, tool)
- [ ] Inputs: `caller_phone`, `text`, `remind_at` (ISO 8601).
- [ ] Check the time (`checkRemindAt`): past or more than 7 days out must not reach the Wait node.
- [ ] Append a row to the `reminders` tab.
- [ ] **Respond to Webhook immediately** with `{"status":"set","when":"8pm today"}`. If the Wait node comes first, ElevenLabs times out and the call breaks.
- [ ] Wait node: resume "At specified time" = `remind_at`.
- [ ] Vonage SMS to `caller_phone`: "Reminder: take your tablets". Mark the row done.

## 5. send_text (POST, tool)
- [ ] Inputs: `caller_phone`, `contact_name` (or a phone number), `message`.
- [ ] Look up the contact's number. Ambiguous: return `{"status":"ambiguous","options":["Sarah Khan","Sarah Lee"]}`.
- [ ] Vonage SMS from the service number, text = `"<user_name>: <message>"` (`formatText`).
- [ ] Return `{"status":"sent","parts":1}`.

## Optional
- [ ] `register_user(name)`: adds a new caller to the `users` tab.
- [ ] `read_emails`: Gmail "get many" for unread messages, returning sender, subject and a one-line snippet each.
- [ ] `vonage-inbound-sms`: forwards a contact's reply to the user's phone, formatted "Mum: OK love".

## Pasting a snippet

1. Add a **Code** node, mode **Run Once for All Items**, language JavaScript.
2. If the snippet's header says "paste normalise-phone.js first", paste
   `normalise-phone.js` first, then the snippet below it, into the **same** node.
3. Paste everything **above** the `if (typeof module !== 'undefined')` line. The
   guard line itself is harmless if you paste it too.
4. Add the 2-3 `return ...` lines shown in the snippet's header, and rename the
   node references (`$('Webhook')`, `$('Contacts')`) to match your node names.
5. Run the node once with test data before wiring it to the agent.

When you change a file in `n8n/code/`, run `node --test`, then paste the new
version into every node listed in its header.

## Exported workflows (`workflows/`)

Export a workflow from n8n (**... > Download**) into `n8n/workflows/<name>.json`.
Before committing:

1. Replace any webhook secret or credential value with `__TOOL_SECRET__`.
2. Check the real secret is gone (PowerShell, from the repo root):
   ```powershell
   $secret = ((Get-Content .env | Select-String '^TOOL_SECRET=').Line -split '=', 2)[1]
   Select-String -Path n8n\workflows\*.json -Pattern $secret -SimpleMatch
   ```
   No output means it's clean.
3. Don't edit exports by hand: change the workflow in n8n and export again.
   Anything you can't scrub goes in `*.private.json` (git-ignored).

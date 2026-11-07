# Brick Agent

An AI assistant you reach by phoning a UK number from any phone, even a Nokia. It sends emails (Gmail), sets reminders and sends texts. Hackathon project (GreatUniHack 2026): submissions close at 18:00 on 7 Nov 2026, feature freeze 16:30. A working end-to-end result beats polish. The full plan is in `docs/PLAN.md`, and it wins if anything here conflicts with it.

## Architecture (we run no server of our own)
Vonage number -> n8n `vonage-answer` webhook (returns an NCCO) -> SIP -> ElevenLabs agent -> the agent calls the n8n `init` webhook and tool webhooks -> Gmail / Vonage SMS / Google Sheet (users, contacts, reminders). n8n, ElevenLabs and Vonage are configured in their web UIs. This repo holds what we keep in sync with them.

## Layout
- `n8n/code/`: pure JavaScript we paste into n8n Code nodes (no require, no npm). Tests in `tests/`.
- `n8n/workflows/`: exported workflow JSON, scrubbed of secrets.
- `agent/`: the ElevenLabs system prompt, tool definitions and example init response.
- `sheet/`: seed CSVs for the Google Sheet.
- `scripts/test-webhooks.mjs`: calls the live n8n webhooks.
- `docs/PLAN.md`: the plan.

## Commands
- `node --test` runs the unit tests.
- `node scripts/test-webhooks.mjs` runs the safe webhook checks. `--live` also sends one real text and sets one reminder, to `TEST_RECIPIENT_PHONE`.

## Rules that must hold
- Phone numbers are E.164 with a `+` everywhere. Vonage sends `from` without the `+`, so always run it through `toE164`.
- Every tool webhook checks the `X-Tool-Secret` header. `caller_phone` comes from the ElevenLabs dynamic variable, never from the model.
- In `set_reminder`, Respond to Webhook comes BEFORE the Wait node, or the call breaks.
- Texts go from the service number and start "Name: ...", cleaned to plain characters.
- Emails and texts are read back and sent only after a clear yes. That is a prompt rule, not server enforcement, so don't claim otherwise.
- Store text, not audio.

## Working agreements
- This repo is public. Never commit real phone numbers, real emails, API keys or the `TOOL_SECRET`. Seed and test data use only Ofcom drama numbers (07700 900000 to 07700 900999) and `@example.com`. Real demo data lives in the Google Sheet.
- A change to `n8n/code/*` or `agent/*` must also be pasted into n8n or ElevenLabs. Say which node or setting in the commit or reply.
- Never hand-edit exported workflow JSON: re-export from n8n.
- Commit messages: short, plain, imperative. No Co-Authored-By trailers and no "Generated with" lines.

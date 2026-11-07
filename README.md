# Brick Agent

**An AI assistant you reach by calling a phone number from any phone, even a 2005 Nokia.**
You get the useful parts of a smartphone (email, reminders, messaging) without the distractions.

More and more people choose basic "brick" phones on purpose, to escape feeds, notifications
and doomscrolling. The cost is losing the useful stuff: sending emails, setting proper
reminders, writing long texts on a keypad. Brick is one phone number. You call it, talk to a
natural-sounding AI agent, and it sends an email from your own Gmail, texts a contact, or
texts you back later with a reminder. There is no screen and no feed, so there is nothing to
scroll. It works from any phone with signal.

Built at GreatUniHack 2026 for people who chose a dumbphone, and for anyone who can speak
more easily than they can type.

## How it works

```
Phone --call--> Vonage number --answer webhook--> n8n (returns NCCO)
                     +--SIP (X-CALLER-ID)--> ElevenLabs agent --init + tool webhooks--> n8n
                                                         n8n --> Gmail / Vonage SMS / Google Sheet
```

The caller's number identifies them: no app, no login. We run no server of our own. All logic
lives in n8n cloud (always on, so reminders fire after the call ends), storage is a Google
Sheet, the voice agent is ElevenLabs and the number is Vonage.

## What's in this repo

| path | what |
|---|---|
| `n8n/code/` | Tested JavaScript pasted into n8n Code nodes: phone normalising, NCCO, init response, contact matching, reminder times, SMS cleaning |
| `tests/` | Unit tests for those snippets (`node:test`, zero dependencies) |
| `agent/` | ElevenLabs system prompt, first messages, tool reference, example init response |
| `sheet/` | Seed CSVs for the Google Sheet (placeholder numbers and emails only) |
| `scripts/test-webhooks.mjs` | Checks the live n8n webhooks without making a phone call |
| `n8n/README.md` | Workflow checklists and build status |
| `docs/PLAN.md` | The full plan |

## Run the checks

Node 18 or newer, no `npm install` needed.

```powershell
node --test                          # unit tests
copy .env.example .env               # then fill in N8N_WEBHOOK_BASE and TOOL_SECRET
node scripts/test-webhooks.mjs       # safe webhook checks, sends nothing
node scripts/test-webhooks.mjs --live  # also one real text and one reminder to TEST_RECIPIENT_PHONE
```

## Setup

Follow "Setup checklist" in `docs/PLAN.md`: Vonage number and Voice application, ElevenLabs
agent (SIP trunk, init webhook, tools), n8n credentials and workflows, then the Google Sheet
(`sheet/README.md`). Build the workflows in the order in `n8n/README.md`.

## Demo

1. **Reminder first:** "Remind me in 3 minutes to thank the judges."
2. **Email:** "Email Sarah Khan that I sent this from a Nokia without typing a letter." Brick reads it back, we say yes, and it arrives.
3. **Text:** "Text Sarah, ask if she wants lunch tomorrow." Brick asks "Which Sarah?", reads back "Do you want lunch tomorrow?", and her phone buzzes.
4. **Payoff:** hang up. The reminder text lands on the Nokia: it still works after the call.

## Limits, honestly

- Texts come from the Brick service number and start "Adam: ...", not from the user's own
  number: networks don't let a service send as a number it doesn't own. Emails do come from
  the user's own account.
- Reading the message back and sending only after a clear "yes" is a rule in the agent's
  prompt. The server does not enforce it.
- Caller ID identifies the user, and caller ID can be spoofed. We accept that for the demo;
  production would add a PIN and daily send limits.
- The hackathon build uses one connected Gmail account and one service number.

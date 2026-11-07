Brick Agent AI assistant for any phone (GUH 2026)
Brick Agent: AI assistant for any phone (GUH 2026)
Nov 7, 2026 · @Adam
Overview
Pitch: an AI assistant you reach by calling a phone number from any phone, even a 2005 Nokia. You get the useful parts of a smartphone (email, reminders, messaging) without the distractions.
The problem. More and more people are choosing basic "brick" phones on purpose to escape feeds, notifications and doomscrolling. The cost is losing the useful stuff: sending emails, setting proper reminders, writing long texts (dozens of key presses on a keypad). Today they have to pick between focus and convenience.
The idea. One phone number. You call it, talk to a natural-sounding AI agent, and it does things for you: sends an email from your own Gmail, texts a contact, or calls/texts you back later with a reminder. There is no screen and no feed, so there is nothing to scroll. The assistant lives in the cloud, so it works from any phone with signal.
Who it's for:
Main audience: people who chose a dumbphone on purpose (digital minimalists, many of them students and young professionals).
Second audience: older people, people with low vision or stiff hands, and anyone who can speak more easily than they can type.
Answer to "why not just use screen-time limits on a smartphone?": limits rely on willpower. This is built so there is nothing to resist. A voice call has no feed.
Phrase to use: it "works from any phone", not "lives on your Nokia". It's more accurate and sounds bigger.
Demo scope
The hackathon build does three things well: emails, reminders and texts. Three skills that work every time beat six that half work.
Skill
What the caller says
What happens
Sent from
Email
"Email Sarah that I'll send the report tomorrow"
Agent writes the email, reads it back, sends after a yes
The user's own Gmail (one demo account connected in n8n)
Reminder
"Remind me at 8 to take my tablets"
Saved, then at 8pm the Nokia gets a text (stretch: an AI phone call)
Service number
Text (partial)
"Text Mum I'll be late, save me dinner"
Agent writes the text, reads it back, sends after a yes. Starts "Adam: ..."
Service number (we can't send from the user's own number)

Stretch goals, only if the three above work on the real Nokia:
"Read me my unread emails": one Gmail node, the clearest example of the tech without the distraction.
Reminder as a phone call instead of a text (ElevenLabs outbound call).
Replies to texts forwarded back to the Nokia.
Out of scope for today (roadmap): a separate Gmail login per user, a separate phone number per user, calendar, more languages, partnerships with mobile networks.
How a call works
The caller's phone number is how we know who they are. No app, no login on the phone.
The user calls the service number (a Vonage UK mobile number) from their Nokia.
Vonage sends an "answer" webhook to n8n with the caller's number.
n8n replies with instructions (NCCO JSON) telling Vonage to connect the call to the ElevenLabs agent over SIP, passing the caller's number in an X-CALLER-ID header.
ElevenLabs takes the call and calls our init webhook in n8n. n8n looks up the caller in the Google Sheet and returns their name, contact names and the current date and time.
The agent greets them by name: "Hi Adam, what can I do for you?"
The user says what they want. The agent calls a tool (an n8n webhook) such as send_email, send_text or set_reminder.
For emails and texts, the agent reads the exact message back and only sends after a clear "yes".
n8n does the work (Gmail node, Vonage SMS node) and returns a short result the agent says out loud.
For reminders, n8n replies "reminder set" straight away, then waits until the time and texts the Nokia. This keeps working after the call ends and with our laptops off, because n8n cloud is always on.
Unknown caller: the agent asks their first name and registers them in the Sheet.
Hidden caller ID: play "please call again without hiding your number" and hang up before the agent connects, so no AI minutes are used.
Architecture and tech stack
Everything runs on hosted services, so there is no laptop server, no ngrok, and nothing breaks if venue Wi-Fi drops.
Nokia --call--> Vonage number --answer webhook--> n8n (returns NCCO) | +--SIP (X-CALLER-ID)--> ElevenLabs agent | init webhook + tool calls v n8n workflows --> Gmail / Vonage SMS | Google Sheet (users, contacts, reminders)

Part
Service
Job
Phone number
Vonage (UK +447 number, Voice + SMS)
Receives calls, sends and receives texts
Voice agent
ElevenLabs Agents
Speech-to-text, LLM, voice, turn-taking, keypad input. No separate OpenAI key needed
Backend logic
n8n cloud
Every webhook and tool. Always on, so reminders fire with laptops closed
Storage
Google Sheet (or n8n Data Tables)
Users, contacts, reminders. A Sheet can go on the projector
Email
Gmail node in n8n
Sends from a real Gmail account
SMS
Vonage node / HTTP request in n8n
Texts to contacts and reminder texts to the user

Why n8n and not a Python server: reminders need something that's always on. A laptop behind ngrok stops working the moment the lid closes. n8n cloud is hosted, and it puts both sponsor tools at the centre of the build.
Trade-off: visual workflows are harder to debug than code, and the n8n trial has execution limits. Check yours before demo time.
n8n workflows
Five workflows, built in this order. Each starts with a Webhook node set to respond "Using Respond to Webhook node". Every tool webhook checks a shared secret header (X-Tool-Secret) so strangers can't call it.
1. vonage-answer (GET)
Vonage calls this when someone rings the number. Query params include from (caller), to and uuid.
If from is empty or withheld → respond with a talk action: "Sorry, I can't see your number. Please call again without hiding it."
Otherwise → respond with a connect action to ElevenLabs over SIP:
[{ "action": "connect", "endpoint": [{ "type": "sip", "uri": "sip:+<VONAGE_NUMBER>@sip.rtc.elevenlabs.io:5061;transport=tls", "headers": { "CALLER-ID": "<from, in +44 format>", "CALL-ID": "<uuid>" } }] }]

Vonage sends custom headers as X- headers, so ElevenLabs receives X-CALLER-ID.
2. init (POST)
ElevenLabs calls this at the start of every call ("conversation initiation" webhook) with the caller ID. Look the caller up in the Sheet and return dynamic variables:
{ "type": "conversation_initiation_client_data", "dynamic_variables": { "caller_phone": "+447700900123", "user_name": "Adam", "is_new_user": false, "contact_names": "Mum, Dad, Sarah Khan, Sarah Lee", "now": "Saturday 7 November 2026, 14:30, Europe/London" } }

now matters: without it the agent can't work out what "in 2 hours" or "at 8" means. Unknown number → is_new_user: true and user_name: "".
3. send_email (POST, tool)
Inputs: caller_phone (filled from a variable, never by the model), contact_name, subject, body.
Look up the contact's email in the Sheet. Not found → return {"status":"not_found"}.
Gmail node → send. Return {"status":"sent","to":"Sarah Khan"}.
Pre-save email addresses. Spelling an email address out loud doesn't work well over a phone line.
4. set_reminder (POST, tool)
Inputs: caller_phone, text, remind_at (ISO 8601, e.g. 2026-11-07T20:00:00+00:00).
Append a row to the reminders tab.
Respond to Webhook immediately with {"status":"set","when":"8pm today"}.
Wait node → resume "At specified time" = remind_at.
Vonage SMS to caller_phone: "Reminder: take your tablets". Mark the row done.
Gotcha: if the Wait node comes before the response, ElevenLabs times out waiting and the call breaks.
5. send_text (POST, tool)
Inputs: caller_phone, contact_name (or phone), message.
Look up the contact's number. Ambiguous (two Sarahs) → return {"status":"ambiguous","options":["Sarah Khan","Sarah Lee"]} so the agent asks which.
Vonage SMS from the service number, text = "<user_name>: <message>".
Return {"status":"sent","parts":1}.
Optional workflows
register_user(name): adds a new caller to the users tab.
read_emails: Gmail "get many" for unread messages → return sender + subject + a one-line snippet each.
vonage-inbound-sms: forwards a reply from a contact to the user's Nokia, formatted "Mum: OK love".
Data model (Google Sheet)
One Google Sheet with three tabs. Store every phone number in full international format (+447700900123) so lookups match.
Tab
Columns
users
phone, name, created_at
contacts
owner_phone, name, aliases (e.g. "Mum, Mom, Mam"), phone, email
reminders
id, owner_phone, text, remind_at, status (pending / sent), created_at

Seed data before the demo: your demo user, plus teammates' real phones and emails as Mum, Dad and two Sarahs. The second Sarah is there to show off the "Which Sarah?" question.
Name matching: check the name and aliases columns, ignoring case. If you have time, add fuzzy matching (n8n Code node) so misheard names like "Siobhan" still match.
ElevenLabs agent
Settings:
Voice: a warm British voice, the lowest-latency text-to-speech model, and the fastest LLM offered.
Turn eagerness: patient, so it doesn't cut people off mid-message.
Keypad (DTMF) input on, with # to finish. Lets callers type a number if speech fails.
Max call length 300 seconds. System tools: end_call.
Security tab: turn on "fetch initiation client data from webhook" (points at the n8n init webhook) and allow first-message override.
Phone numbers: import a SIP trunk number matching the Vonage number, inbound media encryption "Allowed", assign the agent.
Tools: one server (webhook) tool per n8n workflow. Fill caller_phone from the {{caller_phone}} dynamic variable, never from the model.
Testing: Preview mode doesn't run the init webhook, so type the variable values in by hand when testing there.
System prompt (starting point):
You are Brick, a warm, brief British phone assistant. Callers use basic phones on purpose to avoid distractions. You do things for them by voice. Caller: {{user_name}} (new: {{is_new_user}}). Phone: {{caller_phone}}. Contacts: {{contact_names}}. Current time: {{now}}. What you can do: send an email, send a text, set a reminder. Rules: 1. New caller: ask their first name, call register_user. 2. Work out what they want. If it's not one of your skills, say so kindly. 3. Let them finish speaking. Never cut in. If unsure they're done, ask "Is that everything?" 4. For emails and texts: keep their words, fix punctuation, drop "um"s, and turn reported speech into direct speech ("tell her I love her" -> "I love you"). Never add content. 5. Read the exact message back and ask "Shall I send it?" Only call send_email or send_text after a clear yes. For changes, edit and read back again. "No" or "cancel" sends nothing. 6. If a contact is ambiguous, ask which one. If not found, say so. 7. For reminders, turn the time into ISO 8601 using the current time, confirm it out loud ("8pm tonight, right?"), then call set_reminder. 8. One or two short sentences per turn. If a tool fails, say so simply and offer the next step. 9. After each task, offer another. Otherwise say goodbye and end the call.

Caveats, edge cases and guardrails
Issue
What we do
Texts can't come from the user's own number
Providers ban sending as a number you don't own. Texts come from the service number and start "Adam: ". Emails do come from the user's own account. Per-user numbers are on the roadmap
Spoofed caller ID could let someone use your account
Demo: accept the risk. Production: optional PIN and daily send limits
Model sends too early or changes the wording
Prompt rule: read back the exact text, send only after a clear yes. In n8n this is a prompt rule, not enforced by the server. Say that honestly if asked
Names get misheard ("Siobhan", "Nguyen")
Aliases column, contact names passed to the agent up front, "Which Sarah?" when ambiguous
Relative times ("in 2 hours", "at 8")
init passes the current time. Agent confirms the time out loud before saving
Poor phone audio (8 kHz, noisy hall)
Read-backs catch errors. Keypad fallback for numbers. Test in the actual hall
Long silences while the user thinks
Patient turn-taking, and "Is that everything?" instead of cutting in
Withheld number
Refusal message, hang up before the agent connects
Call drops mid-task
Nothing is sent unless the user already said yes
Emoji or curly quotes in a text
Each part drops from 160 to 70 characters. Replace with plain characters before sending
Abuse of a public "text anyone" number
Daily send cap per user, UK mobiles only, 5-minute call cap
Privacy (GDPR)
Say "this call is handled by an AI assistant" on first call. Store text, not audio. Keep ElevenLabs transcript retention short

Setup, roles and timeline
Setup checklist
Vonage: sign up and add about £15–20 credit (trial credit can't buy numbers, and topping up removes the trial watermark and recipient allowlist). Buy a UK mobile number with Voice + SMS.
Vonage Voice application: answer URL = GET <n8n vonage-answer webhook URL>, event URL = any n8n webhook that just returns 200. Link the number.
Vonage API settings: default SMS setting = "SMS API". Inbound SMS URL = n8n webhook (only needed for replies).
ElevenLabs: create the agent, import the SIP trunk number, set the init webhook, add the tools.
n8n: credentials for Gmail (demo account), Google Sheets and Vonage. Activate every workflow and use the production webhook URLs, not the test ones.
Google Sheet: three tabs, seeded with the demo user and contacts.
Check ElevenLabs plan minutes and n8n trial execution limits.
Submit the team and challenge tracks on the GUH dashboard.
Roles
Role
Owns
Telephony
Vonage number, SIP connection to ElevenLabs, vonage-answer, SMS sending
n8n
init, send_email, set_reminder, send_text, Google Sheet
Agent
Prompt, voice, tool definitions in ElevenLabs, running the test calls
Demo
Pitch, slides, seed data, backup video, submission

Timeline (today, hard deadline 18:00)
Time
Goal
14:15–14:45
Number bought, vonage-answer + bare agent. Milestone: the Nokia calls and hears the agent.
14:45–15:15
init working. Milestone: the agent greets the caller by name.
15:15–15:45
send_email + set_reminder. Test a reminder 2 minutes out
15:45–16:15
send_text, read-back prompt tuned, two-Sarah test
16:15–16:30
Full demo three times on the real Nokia, in the hall
16:30
Feature freeze. Record the backup video
16:30–17:45
Slides, write-up, submission

If SIP fails by 15:00: try UDP on port 5060 instead of TLS. Then the official Vonage–ElevenLabs websocket connector (keypad input won't work there, and you'll have to pass the caller's number in yourself).
Demo script, pitch and Q&A
Live demo (about 3 minutes, Nokia on speaker)
Hook (20 s): hold up the Nokia. "No apps, no feed, no notifications. But watch what it can do."
Reminder first: "Remind me in 3 minutes to thank the judges." Setting it first means it lands right at the end.
Email: "Email
judgeorteammate
that I sent this from a Nokia without typing a letter." Hear the read-back, say yes. Show the email arriving on a laptop.
Text: "Text Sarah, ask if she wants lunch tomorrow." Agent asks "Which Sarah?", then reads back "Do you want lunch tomorrow?" Say yes, and her phone buzzes.
Payoff: hang up. The reminder text arrives on the Nokia while you're talking. "It still works after you hang up."
Close (20 s): who it's for, then the roadmap.
Show the Google Sheet or the n8n run history on the projector while it runs, so judges see the steps happen.
Q&A prep
"Why not just use a smartphone with screen-time limits?" Limits rely on willpower. Here there's nothing to resist, because a voice call has no feed.
"Why do texts come from your number, not mine?" Phone networks don't let a service send as a number it doesn't own. Emails already come from your own account. Next step: a personal number per user that your contacts save under your name.
"What stops someone faking my number?" Daily limits now. A PIN option in production.
"What if it mishears me?" Nothing is sent until you hear the exact words read back and say yes.
"Business model?" Monthly subscription for dumbphone users, plus partnerships with mobile networks and dumbphone makers.
Roadmap: calendar, reading emails and replies aloud, a number per user, more languages, network partnerships.
Starter prompt for building
Paste this whole doc into the chat first, then this prompt. Change the part in brackets to the workflow you're building.
We're at a hackathon with about 3.5 hours left. The doc above is our full plan for "Brick": an AI assistant you reach by calling a phone number from a basic Nokia. Stack: Vonage (UK number, voice + SMS), ElevenLabs Agents (voice agent over SIP), n8n cloud (all backend logic), Google Sheets (storage), Gmail (sending email). Right now I'm building: [the n8n `set_reminder` workflow]. Please: 1. List the exact n8n nodes in order, with the settings for each one (field names as they appear in n8n). 2. Give me any expressions or Code node JavaScript I need, ready to paste. 3. Give me the matching ElevenLabs tool definition (name, description, parameters, which ones come from dynamic variables). 4. Tell me how to test it on its own with a curl command before wiring it to the agent. 5. Point out anything in our plan that won't work as written. Keep it short and practical. We need it working, not perfect.

Run one prompt per workflow, in the build order from the n8n section. Get each one working with curl before connecting it to the agent.

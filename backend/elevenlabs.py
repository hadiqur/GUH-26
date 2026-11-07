#!/usr/bin/env python3
"""
Brick: create or update the ElevenLabs agent and its webhook tools from config.json.

  python3 elevenlabs.py      -> upserts the 6 tools and the "Brick" agent (matched by name)

Source of truth for the agent: edit here and re-run, don't hand-edit in the ElevenLabs UI.
Standard library only.
"""
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "config.json")) as f:
    CFG = json.load(f)

API = "https://api.elevenlabs.io"
KEY = CFG.get("elevenlabs_api_key", "")
HOOK = CFG["n8n_url"].rstrip("/") + "/webhook"
AGENT_NAME = CFG.get("assistant_name", "Brick")
VOICE_ID = CFG.get("elevenlabs_voice_id", "JBFqnCBsd6RMkjVDRZzb")  # George: warm British
LLM = CFG.get("elevenlabs_llm", "gemini-2.5-flash")

SYSTEM_PROMPT = """You are Brick, a warm, brief British phone assistant. Callers use basic phones on purpose to avoid distractions. You do things for them by voice.

Caller: {{user_name}} (new: {{is_new_user}}). Phone: {{caller_phone}}.
Contacts: {{contact_names}}. Current time: {{now}}.

Tools: send_email, send_text, set_reminder, save_contact, register_user, read_emails.

Rules:
1. New caller: ask their first name, call register_user.
2. Work out what they want. If it's not one of your skills, say so kindly.
3. Let them finish speaking. Never cut in. If unsure they're done, ask "Is that everything?"
4. For emails and texts: keep their words, fix punctuation, drop "um"s, and turn reported speech into direct speech ("tell her I love her" -> "I love you"). Never add content.
5. Read the exact message back and ask "Shall I send it?" Only call send_email or send_text after a clear yes. For changes, edit and read back again. "No" or "cancel" sends nothing.
6. If a tool returns "ambiguous", ask which of the options they mean. If "not_found" for a text, ask them to type the number on the keypad and press hash, then call send_text with phone, and offer save_contact.
7. For reminders, turn the time into ISO 8601 with a UK offset using the current time, confirm it out loud ("8pm tonight, right?"), then call set_reminder.
8. For read_emails, read sender and subject only, then ask if they want any one in full.
9. One or two short sentences per turn. If a tool fails, say so simply and offer the next step.
10. After each task, offer another. Otherwise say goodbye and end the call."""


def dyn(var):
    """Body field filled from a dynamic variable, never by the LLM."""
    return {"type": "string", "dynamic_variable": var}


def llm(desc):
    return {"type": "string", "description": desc}


# name -> (path, description, llm/dynamic properties, required)
TOOLS = {
    "send_email": ("/brick/tools/send-email",
        "Send an email from the caller's Gmail to a saved contact. Only call after reading the email back and hearing a clear yes.",
        {"caller_phone": dyn("caller_phone"),
         "contact_name": llm("Name of the saved contact, as the caller said it"),
         "subject": llm("Short subject line"),
         "body": llm("The email body, in the caller's own words as read back")},
        ["caller_phone", "contact_name", "body"]),
    "send_text": ("/brick/tools/send-text",
        "Send a text message to a contact or a phone number. Only call after reading the text back and hearing a clear yes. Give contact_name, or phone if the caller typed a number.",
        {"caller_phone": dyn("caller_phone"),
         "user_name": dyn("user_name"),
         "contact_name": llm("Name of the saved contact, as the caller said it. Leave empty if using phone"),
         "phone": llm("Phone number typed on the keypad, only if the contact was not found"),
         "message": llm("The text message, in the caller's own words as read back")},
        ["caller_phone", "message"]),
    "set_reminder": ("/brick/tools/set-reminder",
        "Set a reminder that texts the caller at the given time, even after they hang up. Confirm the time out loud first.",
        {"caller_phone": dyn("caller_phone"),
         "text": llm("What to remind them about, short"),
         "remind_at": llm("When, as ISO 8601 with UK offset, e.g. 2026-11-07T20:00:00+00:00")},
        ["caller_phone", "text", "remind_at"]),
    "save_contact": ("/brick/contacts",
        "Save a new contact for the caller.",
        {"caller_phone": dyn("caller_phone"),
         "name": llm("Contact's name"),
         "phone": llm("Contact's phone number, digits"),
         "email": llm("Contact's email address, if given"),
         "aliases": llm("Other names for them, comma separated, e.g. Mum, Mom")},
        ["caller_phone", "name"]),
    "register_user": ("/brick/register",
        "Register a new caller with their first name.",
        {"caller_phone": dyn("caller_phone"),
         "name": llm("Caller's first name")},
        ["caller_phone", "name"]),
    "read_emails": ("/brick/tools/read-emails",
        "Get the caller's latest unread emails (sender, subject, snippet).",
        {"caller_phone": dyn("caller_phone")},
        ["caller_phone"]),
}


def api(method, path, body=None):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"xi-api-key": KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            t = r.read().decode()
            return json.loads(t) if t else {}
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:1500]}")


def tool_config(name):
    path, desc, props, required = TOOLS[name]
    return {
        "type": "webhook",
        "name": name,
        "description": desc,
        "response_timeout_secs": 20,
        "api_schema": {
            "url": HOOK + path,
            "method": "POST",
            "request_headers": {"X-Tool-Secret": CFG["tool_secret"]},
            "request_body_schema": {"type": "object", "description": f"{name} request",
                                    "properties": props, "required": required},
        },
    }


def upsert_tools():
    existing = {t["tool_config"]["name"]: t["id"] for t in api("GET", "/v1/convai/tools").get("tools", [])}
    ids = []
    for name in TOOLS:
        body = {"tool_config": tool_config(name)}
        if name in existing:
            api("PATCH", f"/v1/convai/tools/{existing[name]}", body)
            ids.append(existing[name]); print(f"  updated tool {name}")
        else:
            ids.append(api("POST", "/v1/convai/tools", body)["id"]); print(f"  created tool {name}")
    return ids


def agent_body(tool_ids):
    return {
        "name": AGENT_NAME,
        "conversation_config": {
            "agent": {
                "first_message": f"Hi, it's {AGENT_NAME}. What can I do for you?",
                "language": "en",
                "dynamic_variables": {"dynamic_variable_placeholders": {
                    "caller_phone": "+447700900123", "user_name": "Adam", "is_new_user": "false",
                    "contact_names": "Mum", "now": "Saturday 7 November at 15:30 UK time",
                }},
                "prompt": {
                    "prompt": SYSTEM_PROMPT,
                    "llm": LLM,
                    "temperature": 0.3,
                    "tool_ids": tool_ids,
                    "built_in_tools": {"end_call": {
                        "name": "end_call", "description": "",
                        "params": {"system_tool_type": "end_call"},
                    }},
                },
            },
            "tts": {"model_id": "eleven_flash_v2", "voice_id": VOICE_ID},
            "turn": {"turn_eagerness": "patient"},
            "conversation": {
                "max_duration_seconds": 300,
                # keypad input: finish with #, allow slow typing between digits
                "dtmf_input_settings": {"hash_terminator": True, "dtmf_input_timeout": 5.0, "redact_input": False},
            },
        },
        "platform_settings": {
            "workspace_overrides": {"conversation_initiation_client_data_webhook": {
                "url": HOOK + "/brick/init", "request_headers": {},
            }},
            "overrides": {
                "enable_conversation_initiation_client_data_from_webhook": True,
                "conversation_config_override": {"agent": {"first_message": True}},
            },
        },
    }


def main():
    if not KEY:
        sys.exit("Set elevenlabs_api_key in config.json.")
    print("Tools:")
    ids = upsert_tools()
    agents = {a["name"]: a["agent_id"] for a in api("GET", "/v1/convai/agents?page_size=100").get("agents", [])}
    body = agent_body(ids)
    if AGENT_NAME in agents:
        aid = agents[AGENT_NAME]
        api("PATCH", f"/v1/convai/agents/{aid}", body); print(f"Updated agent {AGENT_NAME}: {aid}")
    else:
        aid = api("POST", "/v1/convai/agents/create", body)["agent_id"]; print(f"Created agent {AGENT_NAME}: {aid}")


if __name__ == "__main__":
    main()

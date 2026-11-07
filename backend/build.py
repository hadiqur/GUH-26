#!/usr/bin/env python3
"""
Brick: generate (and optionally push) all n8n workflows from config.json.

  python build.py          -> writes workflows/*.json (paste or import into n8n)
  python build.py --push   -> also creates/updates them in n8n via the API and activates them

No dependencies beyond the Python standard library.
"""
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
NS = uuid.UUID("6f1c2b0e-8d4a-4e7b-9a51-0b7f3c2d1e00")


def load_config():
    path = os.path.join(HERE, "config.json")
    if not os.path.exists(path):
        sys.exit("config.json not found. Copy config.example.json to config.json and fill it in.")
    with open(path) as f:
        cfg = json.load(f)
    cfg["vonage_number"] = "".join(ch for ch in str(cfg.get("vonage_number", "")) if ch.isdigit())
    cfg["n8n_url"] = str(cfg.get("n8n_url", "")).rstrip("/")
    return cfg


CFG = load_config()

# Values the Code nodes can see. API secrets for Vonage live here too (fine for a hackathon).
JS_CFG = json.dumps({
    "tool_secret": CFG.get("tool_secret", ""),
    "vonage_api_key": CFG.get("vonage_api_key", ""),
    "vonage_api_secret": CFG.get("vonage_api_secret", ""),
    "vonage_number": CFG["vonage_number"],
    "default_email_signature": CFG.get("email_signature", ""),
    "assistant_name": CFG.get("assistant_name", "Brick"),
})

# Shared JavaScript helpers, prepended to every Code node.
JS_HELPERS = r'''
const CFG = __CFG__;
const digits = s => String(s ?? '').replace(/\D/g, '');
// Normalise any phone number to digits in international form, e.g. 07700 900123 -> 447700900123
function normPhone(s) {
  let d = digits(s);
  if (d.startsWith('00')) d = d.slice(2);
  else if (d.startsWith('0')) d = '44' + d.slice(1);
  return d;
}
function checkSecret() {
  const w = $('Webhook').first().json;
  const got = (w.headers || {})['x-tool-secret'] || (w.query || {}).key || (w.body || {}).key;
  if (got !== CFG.tool_secret) throw new Error('Unauthorized: bad or missing X-Tool-Secret header');
}
// Dashboard login: stateless SMS codes and session tokens, signed with the tool secret.
const crypto = require('crypto');
const hmac = s => crypto.createHmac('sha256', CFG.tool_secret).update(s).digest('hex');
const safeEq = (a, b) => { a = String(a ?? ''); b = String(b ?? ''); return a.length === b.length && crypto.timingSafeEqual(Buffer.from(a), Buffer.from(b)); };
const loginCode = (phone, exp) => String(parseInt(hmac(`code:${phone}:${exp}`).slice(0, 8), 16) % 1000000).padStart(6, '0');
function makeToken(phone) {
  const exp = Date.now() + 7 * 24 * 3600 * 1000;
  return `${phone}.${exp}.${hmac(`session:${phone}:${exp}`).slice(0, 32)}`;
}
function tokenPhone(t) {
  const [p, e, sig] = String(t || '').split('.');
  if (!p || !(Number(e) > Date.now())) return null;
  return safeEq(sig, hmac(`session:${p}:${e}`).slice(0, 32)) ? p : null;
}
// Who is calling: the agent (tool secret, phone taken from the body) or a dashboard session (phone from the token).
// Returns the acting phone as digits, or null when unauthorised.
function actorPhone(bodyPhone) {
  const w = $('Webhook').first().json, h = w.headers || {}, q = w.query || {}, b = w.body || {};
  if ((h['x-tool-secret'] || q.key || b.key) === CFG.tool_secret) return normPhone(bodyPhone);
  return tokenPhone(String(h.authorization || '').replace(/^Bearer\s+/i, '') || q.token || b.token);
}
const isAdmin = () => { const w = $('Webhook').first().json; return ((w.headers || {})['x-tool-secret'] || (w.query || {}).key || (w.body || {}).key) === CFG.tool_secret; };
const UNAUTHORISED = { status: 'unauthorised', message: 'Please log in again.' };
const truthy = v => v === true || /^(true|yes|1)$/i.test(String(v ?? '').trim());
// Per-user preferences stored as columns on the users tab
function prefsOf(user) {
  return {
    email_connected: truthy(user && user.email_connected),
    email_signature: user && user.email_signature != null && String(user.email_signature) !== '' ? String(user.email_signature) : CFG.default_email_signature,
    allow_international: truthy(user && user.allow_international),
  };
}
const userOf = phone => rowsOf('Read users').find(u => normPhone(u.phone) === phone) || null;
const norm = s => String(s ?? '').toLowerCase().normalize('NFKD').replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim();
// Rows from a Google Sheets "read" node, ignoring the empty item n8n emits when the sheet is empty
function rowsOf(nodeName) {
  try { return $(nodeName).all().map(i => i.json).filter(r => r && Object.keys(r).length > 0); }
  catch (e) { return []; }
}
// Match a spoken name against a user's contacts using the name and aliases columns
function findContacts(rows, owner, name) {
  const n = norm(name);
  if (!n) return [];
  const mine = rows.filter(r => normPhone(r.owner_phone) === owner);
  const namesOf = r => [r.name, ...String(r.aliases || '').split(',')].map(norm).filter(Boolean);
  const exact = mine.filter(r => namesOf(r).includes(n));
  if (exact.length) return exact;
  return mine.filter(r => namesOf(r).some(x => x.split(' ').includes(n) || x.startsWith(n) || n.includes(x)));
}
// Swap characters that would force an SMS into 70-char Unicode parts
function toGsm(s) {
  return String(s ?? '')
    .replace(/[‘’‚′]/g, "'")
    .replace(/[“”„″]/g, '"')
    .replace(/[–—−]/g, '-')
    .replace(/…/g, '...')
    .replace(/ /g, ' ');
}
const GSM_BASIC = "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà";
const GSM_EXT = "^{}\\[~]|€";
function smsInfo(text) {
  let units = 0, unicode = false;
  for (const ch of text) {
    if (GSM_BASIC.includes(ch)) units += 1;
    else if (GSM_EXT.includes(ch)) units += 2;
    else { unicode = true; break; }
  }
  if (unicode) {
    const len = [...text].length;
    return { unicode: true, parts: len <= 70 ? 1 : Math.ceil(len / 67) };
  }
  return { unicode: false, parts: units <= 160 ? 1 : Math.ceil(units / 153) };
}
function smsPayload(to, text) {
  const info = smsInfo(text);
  const p = { api_key: CFG.vonage_api_key, api_secret: CFG.vonage_api_secret, from: CFG.vonage_number, to, text };
  if (info.unicode) p.type = 'unicode';
  return { payload: p, parts: info.parts };
}
const londonTime = d => d.toLocaleString('en-GB', { timeZone: 'Europe/London', weekday: 'long', day: 'numeric', month: 'long', hour: 'numeric', minute: '2-digit' });
'''.replace("__CFG__", JS_CFG)


def js(body):
    return JS_HELPERS + "\n// ---- workflow logic ----\n" + body.strip() + "\n"


def sid(*parts):
    return str(uuid.uuid5(NS, "/".join(parts)))


class Workflow:
    def __init__(self, name, slug, path):
        self.name, self.slug, self.path = name, slug, path
        self.nodes, self.connections = [], {}

    def add(self, name, type_, version, params, pos, **extra):
        node = {
            "id": sid(self.name, name),
            "name": name,
            "type": type_,
            "typeVersion": version,
            "position": list(pos),
            "parameters": params,
        }
        node.update(extra)
        self.nodes.append(node)
        return name

    def link(self, a, b):
        main = self.connections.setdefault(a, {"main": [[]]})["main"]
        main[0].append({"node": b, "type": "main", "index": 0})

    def chain(self, *names):
        for a, b in zip(names, names[1:]):
            self.link(a, b)

    def to_dict(self):
        return {
            "name": self.name,
            "nodes": self.nodes,
            "connections": self.connections,
            "settings": {"executionOrder": "v1"},
        }


# ---------- node builders ----------

def webhook(wf, method="POST", respond_node=True, pos=(0, 300)):
    params = {
        "httpMethod": method,
        "path": wf.path,
        "responseMode": "responseNode" if respond_node else "onReceived",
        "options": {"allowedOrigins": "*"},
    }
    return wf.add("Webhook", "n8n-nodes-base.webhook", 2, params, pos, webhookId=sid(wf.name, "webhook"))


def code(wf, name, body, pos):
    return wf.add(name, "n8n-nodes-base.code", 2, {"jsCode": js(body)}, pos)


def gate(wf, pos, name="Only if ok"):
    return wf.add(name, "n8n-nodes-base.code", 2,
                  {"jsCode": "return $input.all().filter(i => i.json.ok);"}, pos)


def respond(wf, pos, name="Respond", expr="$json.response"):
    params = {"respondWith": "json", "responseBody": "={{ JSON.stringify(%s) }}" % expr, "options": {}}
    return wf.add(name, "n8n-nodes-base.respondToWebhook", 1.1, params, pos)


def _sheet_ref(tab):
    return (
        {"__rl": True, "value": CFG.get("sheet_id", ""), "mode": "id"},
        {"__rl": True, "value": tab, "mode": "name"},
    )


def _sheets_creds():
    cid = CFG.get("google_sheets_credential_id")
    return {"credentials": {"googleSheetsOAuth2Api": {"id": cid, "name": "Google Sheets account"}}} if cid else {}


def sheet_read(wf, name, tab, pos, once=False):
    doc, sheet = _sheet_ref(tab)
    params = {"authentication": "oAuth2", "operation": "read", "documentId": doc, "sheetName": sheet, "options": {}}
    extra = {"alwaysOutputData": True, **_sheets_creds()}
    if once:
        extra["executeOnce"] = True
    return wf.add(name, "n8n-nodes-base.googleSheets", 4.5, params, pos, **extra)


def sheet_append(wf, name, tab, cols, pos):
    doc, sheet = _sheet_ref(tab)
    params = {
        "authentication": "oAuth2",
        "operation": "append",
        "documentId": doc,
        "sheetName": sheet,
        "columns": {
            "mappingMode": "defineBelow",
            "value": {c: "={{ $json.row.%s }}" % c for c in cols},
            "matchingColumns": [],
            "schema": [
                {"id": c, "displayName": c, "required": False, "defaultMatch": False,
                 "display": True, "type": "string", "canBeUsedToMatch": True}
                for c in cols
            ],
        },
        "options": {},
    }
    return wf.add(name, "n8n-nodes-base.googleSheets", 4.5, params, pos, **_sheets_creds())


def row_gate(wf, pos, name="Only if ok"):
    """Pass only ok items, emitting just their `row` (for auto-mapped Sheets writes)."""
    return wf.add(name, "n8n-nodes-base.code", 2,
                  {"jsCode": "return $input.all().filter(i => i.json.ok).map(i => ({ json: i.json.row }));"}, pos)


def sheet_update(wf, name, tab, pos):
    """Update the row whose row_number matches; keys in the item become columns (new ones are added)."""
    doc, sheet = _sheet_ref(tab)
    params = {
        "authentication": "oAuth2", "operation": "update", "documentId": doc, "sheetName": sheet,
        "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": ["row_number"], "schema": []},
        "options": {"handlingExtraData": "insertInNewColumn"},
    }
    return wf.add(name, "n8n-nodes-base.googleSheets", 4.5, params, pos, **_sheets_creds())


def sheet_delete_row(wf, name, tab, pos):
    doc, sheet = _sheet_ref(tab)
    params = {"authentication": "oAuth2", "operation": "delete", "documentId": doc, "sheetName": sheet,
              "toDelete": "rows", "startIndex": "={{ $json.row_number }}", "numberToDelete": 1}
    return wf.add(name, "n8n-nodes-base.googleSheets", 4.5, params, pos, **_sheets_creds())


def _gmail_creds():
    cid = CFG.get("gmail_credential_id")
    return {"credentials": {"gmailOAuth2": {"id": cid, "name": "Gmail account"}}} if cid else {}


def send_sms(wf, name, pos, expr="$json.sms"):
    params = {
        "method": "POST",
        "url": "https://rest.nexmo.com/sms/json",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify(%s) }}" % expr,
        "options": {},
    }
    return wf.add(name, "n8n-nodes-base.httpRequest", 4.2, params, pos)


# ---------- workflows ----------

def wf_vonage_answer():
    wf = Workflow("Brick - Vonage answer", "vonage-answer", "brick/vonage/answer")
    w = webhook(wf, method="GET", pos=(0, 300))
    c = code(wf, "Build NCCO", r'''
const q = $('Webhook').first().json.query || {};
const caller = normPhone(q.from);
let ncco;
if (!caller || caller.length < 8) {
  ncco = [{ action: 'talk', language: 'en-GB',
            text: "Sorry, I can't see your number. Please call again without hiding it." }];
} else {
  ncco = [{ action: 'connect', endpoint: [{
    type: 'sip',
    uri: `sip:+${CFG.vonage_number}@sip.rtc.elevenlabs.io:5061;transport=tls`,
    headers: { 'CALLER-ID': '+' + caller, 'CALL-ID': String(q.uuid || '') },
  }] }];
}
return [{ json: { response: ncco, caller } }];
''', (240, 300))
    r = respond(wf, (480, 300))
    wf.chain(w, c, r)
    return wf


def wf_vonage_event():
    wf = Workflow("Brick - Vonage events", "vonage-event", "brick/vonage/event")
    webhook(wf, method="POST", respond_node=False, pos=(0, 300))
    return wf


def wf_init():
    wf = Workflow("Brick - Call init", "init", "brick/init")
    w = webhook(wf, pos=(0, 300))
    u = sheet_read(wf, "Read users", "users", (240, 300))
    ct = sheet_read(wf, "Read contacts", "contacts", (480, 300), once=True)
    c = code(wf, "Build variables", r'''
const body = $('Webhook').first().json.body || {};
const raw = JSON.stringify(body);
// Prefer our own X-CALLER-ID SIP header (set in the NCCO); over SIP, caller_id can be the Vonage number itself.
const m = raw.match(/"x-caller-id"\s*:\s*"([^"]+)"/i);
let callerRaw = m ? m[1] : (body.caller_id || body.callerId || body.from || body.caller || '');
if (normPhone(callerRaw) === CFG.vonage_number) callerRaw = '';
const caller = normPhone(callerRaw);
const user = rowsOf('Read users').find(u => normPhone(u.phone) === caller);
const contacts = rowsOf('Read contacts').filter(c => normPhone(c.owner_phone) === caller);
const name = user ? String(user.name) : '';
const now = new Date();
const response = {
  type: 'conversation_initiation_client_data',
  dynamic_variables: {
    caller_phone: caller ? '+' + caller : 'unknown',
    user_name: name || 'there',
    is_new_user: !user,
    contact_names: contacts.map(c => c.name).join(', ') || 'none saved yet',
    now: `${londonTime(now)} UK time (ISO ${now.toISOString()})`,
  },
  conversation_config_override: { agent: { first_message: user
    ? `Hi ${name}, it's ${CFG.assistant_name}. What can I do for you?`
    : `Hi, I'm ${CFG.assistant_name}, an AI phone assistant. This call is handled by AI. What's your first name?` } },
};
// debug_body shows exactly what ElevenLabs sent, check it in the execution log
return [{ json: { response, debug_body: body } }];
''', (720, 300))
    r = respond(wf, (960, 300))
    wf.chain(w, u, ct, c, r)
    return wf


def wf_send_email():
    wf = Workflow("Brick - Tool send_email", "send-email", "brick/tools/send-email")
    w = webhook(wf, pos=(0, 300))
    ct = sheet_read(wf, "Read contacts", "contacts", (240, 300))
    us = sheet_read(wf, "Read users", "users", (360, 300), once=True)
    c = code(wf, "Prepare", r'''
checkSecret();
const b = $('Webhook').first().json.body || {};
const owner = normPhone(b.caller_phone);
let ok = false, email = null, response;
const prefs = prefsOf(userOf(owner));
if (!prefs.email_connected) {
  response = { status: 'not_connected', message: "Email isn't set up for this caller yet." };
} else if (!b.body) {
  response = { status: 'invalid', message: 'The email has no body.' };
} else {
  const m = findContacts(rowsOf('Read contacts'), owner, b.contact_name);
  if (m.length === 0) response = { status: 'not_found', message: `No contact called ${b.contact_name}.` };
  else if (m.length > 1) response = { status: 'ambiguous', options: m.slice(0, 3).map(x => x.name) };
  else if (!m[0].email) response = { status: 'no_email', message: `${m[0].name} has no email address saved.` };
  else {
    ok = true;
    const sig = prefs.email_signature ? `\n\n${prefs.email_signature}` : '';
    email = { to: m[0].email, subject: b.subject || 'Message', body: String(b.body) + sig };
    response = { status: 'sent', to: m[0].name };
  }
}
return [{ json: { ok, email, response } }];
''', (480, 300))
    r = respond(wf, (720, 150))
    g = gate(wf, (720, 450))
    gm = wf.add("Send email", "n8n-nodes-base.gmail", 2.1, {
        "sendTo": "={{ $json.email.to }}",
        "subject": "={{ $json.email.subject }}",
        "emailType": "text",
        "message": "={{ $json.email.body }}",
        "options": {"appendAttribution": False},
    }, (960, 450), **_gmail_creds())
    wf.chain(w, ct, us, c)
    wf.link(c, r)
    wf.link(c, g)
    wf.link(g, gm)
    return wf


def wf_set_reminder():
    wf = Workflow("Brick - Tool set_reminder", "set-reminder", "brick/tools/set-reminder")
    w = webhook(wf, pos=(0, 300))
    c = code(wf, "Prepare", r'''
checkSecret();
const b = $('Webhook').first().json.body || {};
const owner = normPhone(b.caller_phone);
const t = new Date(b.remind_at);
let ok = false, row = null, sms = null, response;
if (!b.text) response = { status: 'invalid', message: 'The reminder has no text.' };
else if (isNaN(t.getTime())) response = { status: 'invalid_time', message: 'Could not read the time. Send remind_at as ISO 8601.' };
else if (t.getTime() < Date.now() - 60000) response = { status: 'invalid_time', message: 'That time is in the past.' };
else {
  ok = true;
  row = { id: 'r' + Date.now(), owner_phone: '+' + owner, text: String(b.text), remind_at: t.toISOString(),
          status: 'pending', created_at: new Date().toISOString() };
  sms = smsPayload(owner, toGsm(`Reminder: ${b.text}`)).payload;
  response = { status: 'set', when: londonTime(t) };
}
return [{ json: { ok, row, sms, remind_at: row ? row.remind_at : null, response } }];
''', (240, 300))
    r = respond(wf, (480, 150))
    g = gate(wf, (480, 450))
    a = sheet_append(wf, "Save reminder", "reminders",
                     ["id", "owner_phone", "text", "remind_at", "status", "created_at"], (720, 450))
    wt = wf.add("Wait until due", "n8n-nodes-base.wait", 1.1, {
        "resume": "specificTime",
        "dateTime": "={{ $('Prepare').first().json.remind_at }}",
    }, (960, 450), webhookId=sid(wf.name, "wait"))
    s = send_sms(wf, "Text the reminder", (1200, 450), expr="$('Prepare').first().json.sms")
    wf.link(w, c)
    wf.link(c, r)
    wf.link(c, g)
    wf.chain(g, a, wt, s)
    return wf


def wf_send_text():
    wf = Workflow("Brick - Tool send_text", "send-text", "brick/tools/send-text")
    w = webhook(wf, pos=(0, 300))
    ct = sheet_read(wf, "Read contacts", "contacts", (240, 300))
    us = sheet_read(wf, "Read users", "users", (360, 300), once=True)
    c = code(wf, "Prepare", r'''
checkSecret();
const b = $('Webhook').first().json.body || {};
const owner = normPhone(b.caller_phone);
let ok = false, sms = null, response = null, target = null, targetName = null;
if (b.phone) { target = normPhone(b.phone); targetName = '+' + target; }
else {
  const m = findContacts(rowsOf('Read contacts'), owner, b.contact_name);
  if (m.length === 0) response = { status: 'not_found', message: `No contact called ${b.contact_name}. Ask the caller to type the number on the keypad.` };
  else if (m.length > 1) response = { status: 'ambiguous', options: m.slice(0, 3).map(x => x.name) };
  else { target = normPhone(m[0].phone); targetName = m[0].name; }
}
if (!response) {
  if (!b.message) response = { status: 'invalid', message: 'The text has no message.' };
  else if (!target) response = { status: 'invalid', message: 'That contact has no phone number saved.' };
  else if (!prefsOf(userOf(owner)).allow_international && !(target.startsWith('447') && target.length === 12))
    response = { status: 'blocked', message: 'Only UK mobile numbers are allowed right now.' };
  else {
    const sender = b.user_name && b.user_name !== 'there' ? b.user_name : 'A Brick user';
    const s = smsPayload(target, toGsm(`${sender}: ${b.message}`));
    ok = true; sms = s.payload;
    response = { status: 'sent', to: targetName, parts: s.parts };
  }
}
return [{ json: { ok, sms, response } }];
''', (480, 300))
    r = respond(wf, (720, 150))
    g = gate(wf, (720, 450))
    s = send_sms(wf, "Send SMS", (960, 450))
    wf.chain(w, ct, us, c)
    wf.link(c, r)
    wf.link(c, g)
    wf.link(g, s)
    return wf


def wf_register_user():
    wf = Workflow("Brick - Register user", "register-user", "brick/register")
    w = webhook(wf, pos=(0, 300))
    u = sheet_read(wf, "Read users", "users", (240, 300))
    c = code(wf, "Prepare", r'''
const b = $('Webhook').first().json.body || {};
const phone = actorPhone(b.caller_phone || b.phone);
const name = String(b.name || '').trim();
let ok = false, row = null, response;
if (phone === null) response = UNAUTHORISED;
else if (!phone || phone.length < 10) response = { status: 'invalid', message: 'Missing or invalid phone number.' };
else if (!name) response = { status: 'invalid', message: 'Missing name.' };
else if (rowsOf('Read users').some(u => normPhone(u.phone) === phone))
  response = { status: 'exists', message: 'That number is already registered.' };
else {
  ok = true;
  row = { phone: '+' + phone, name, created_at: new Date().toISOString() };
  response = { status: 'registered', name };
}
return [{ json: { ok, row, response } }];
''', (480, 300))
    r = respond(wf, (720, 150))
    g = gate(wf, (720, 450))
    a = sheet_append(wf, "Save user", "users", ["phone", "name", "created_at"], (960, 450))
    wf.chain(w, u, c)
    wf.link(c, r)
    wf.link(c, g)
    wf.link(g, a)
    return wf


def wf_add_contact():
    wf = Workflow("Brick - Add contact", "add-contact", "brick/contacts")
    w = webhook(wf, pos=(0, 300))
    ct = sheet_read(wf, "Read contacts", "contacts", (240, 300))
    c = code(wf, "Prepare", r'''
const b = $('Webhook').first().json.body || {};
const owner = actorPhone(b.caller_phone || b.owner_phone);
const name = String(b.name || '').trim();
const phone = b.phone ? normPhone(b.phone) : '';
const email = String(b.email || '').trim();
let ok = false, row = null, response;
if (owner === null) response = UNAUTHORISED;
else if (!owner) response = { status: 'invalid', message: 'Missing owner phone.' };
else if (!name) response = { status: 'invalid', message: 'Missing contact name.' };
else if (!phone && !email) response = { status: 'invalid', message: 'Need a phone number or an email.' };
else if (phone && phone.length < 10) response = { status: 'invalid', message: 'That phone number looks too short.' };
else if (rowsOf('Read contacts').some(r => normPhone(r.owner_phone) === owner && norm(r.name) === norm(name)))
  response = { status: 'exists', message: `There is already a contact called ${name}.` };
else {
  ok = true;
  row = { owner_phone: '+' + owner, name, aliases: String(b.aliases || ''), phone: phone ? '+' + phone : '', email };
  // spoken form: digits separated so the agent reads them one by one
  response = { status: 'saved', name, phone_spoken: phone ? ('0' + phone.slice(2)).split('').join(' ') : '' };
}
return [{ json: { ok, row, response } }];
''', (480, 300))
    r = respond(wf, (720, 150))
    g = gate(wf, (720, 450))
    a = sheet_append(wf, "Save contact", "contacts", ["owner_phone", "name", "aliases", "phone", "email"], (960, 450))
    wf.chain(w, ct, c)
    wf.link(c, r)
    wf.link(c, g)
    wf.link(g, a)
    return wf


def wf_dashboard():
    wf = Workflow("Brick - Dashboard data", "dashboard", "brick/dashboard")
    w = webhook(wf, method="GET", pos=(0, 300))
    u = sheet_read(wf, "Read users", "users", (240, 300))
    ct = sheet_read(wf, "Read contacts", "contacts", (480, 300), once=True)
    rm = sheet_read(wf, "Read reminders", "reminders", (720, 300), once=True)
    c = code(wf, "Build response", r'''
const q = $('Webhook').first().json.query || {};
const phone = actorPhone(q.phone);
if (phone === null) return [{ json: { response: UNAUTHORISED } }];
const user = userOf(phone);
const contacts = rowsOf('Read contacts').filter(c => normPhone(c.owner_phone) === phone)
  .map(c => ({ id: c.row_number, name: c.name, aliases: c.aliases || '', phone: c.phone ? '+' + normPhone(c.phone) : '', email: c.email || '' }));
const reminders = rowsOf('Read reminders').filter(r => normPhone(r.owner_phone) === phone)
  .map(r => ({ id: r.id, text: r.text, remind_at: r.remind_at,
               status: new Date(r.remind_at).getTime() <= Date.now() ? 'sent' : 'pending' }))
  .sort((a, b) => String(b.remind_at).localeCompare(String(a.remind_at)));
const response = { status: 'ok', phone: '+' + phone, service_number: CFG.vonage_number ? '+' + CFG.vonage_number : '',
  user: user ? { phone: '+' + normPhone(user.phone), name: user.name, ...prefsOf(user) } : null,
  contacts: user ? contacts : [], reminders: user ? reminders : [] };
return [{ json: { response } }];
''', (960, 300))
    r = respond(wf, (1200, 300))
    wf.chain(w, u, ct, rm, c, r)
    return wf


def wf_read_emails():
    wf = Workflow("Brick - Tool read_emails", "read-emails", "brick/tools/read-emails")
    w = webhook(wf, pos=(0, 300))
    us = sheet_read(wf, "Read users", "users", (120, 300))
    chk = code(wf, "Check caller", r'''
checkSecret();
const b = $('Webhook').first().json.body || {};
const owner = normPhone(b.caller_phone);
const ok = prefsOf(userOf(owner)).email_connected;
return [{ json: { ok, response: { status: 'not_connected', message: "Email isn't set up for this caller yet." } } }];
''', (240, 300))
    rno = respond(wf, (480, 150), name="Respond not connected")
    g = gate(wf, (480, 450))
    gm = wf.add("Get unread emails", "n8n-nodes-base.gmail", 2.1, {
        "operation": "getAll",
        "limit": 5,
        "simple": True,
        "filters": {"readStatus": "unread"},
        "options": {},
    }, (720, 450), alwaysOutputData=True, **_gmail_creds())
    s = code(wf, "Summarise", r'''
const items = $input.all().map(i => i.json).filter(j => j && Object.keys(j).length > 0);
const emails = items.map(j => ({
  from: String(j.From || j.from || '').replace(/<.*?>/g, '').trim(),
  subject: j.Subject || j.subject || '(no subject)',
  snippet: String(j.snippet || '').slice(0, 160),
}));
return [{ json: { response: { status: 'ok', count: emails.length, emails } } }];
''', (960, 450))
    r = respond(wf, (1200, 450))
    wf.chain(w, us, chk)
    # Not-connected callers get an answer; connected callers continue to Gmail.
    no = wf.add("Only if not ok", "n8n-nodes-base.code", 2,
                {"jsCode": "return $input.all().filter(i => !i.json.ok);"}, (480, 0))
    wf.link(chk, no)
    wf.link(no, rno)
    wf.link(chk, g)
    wf.chain(g, gm, s, r)
    return wf

def wf_auth_request_code():
    wf = Workflow("Brick - Login request code", "login-request", "brick/auth/request-code")
    w = webhook(wf, pos=(0, 300))
    c = code(wf, "Prepare", r'''
const b = $('Webhook').first().json.body || {};
const phone = normPhone(b.phone);
let ok = false, sms = null, response;
if (!(phone.startsWith('447') && phone.length === 12)) response = { status: 'invalid', message: 'Enter a UK mobile number, like 07700 900123.' };
else {
  const exp = Date.now() + 10 * 60 * 1000;
  sms = smsPayload(phone, `Your ${CFG.assistant_name} login code is ${loginCode(phone, exp)}. It expires in 10 minutes.`).payload;
  ok = true;
  response = { status: 'sent', phone: '+' + phone, exp };
}
return [{ json: { ok, sms, response } }];
''', (240, 300))
    r = respond(wf, (480, 150))
    g = gate(wf, (480, 450))
    s = send_sms(wf, "Text the code", (720, 450))
    wf.link(w, c); wf.link(c, r); wf.link(c, g); wf.link(g, s)
    return wf


def wf_auth_verify():
    wf = Workflow("Brick - Login verify", "login-verify", "brick/auth/verify")
    w = webhook(wf, pos=(0, 300))
    u = sheet_read(wf, "Read users", "users", (240, 300))
    c = code(wf, "Check code", r'''
const b = $('Webhook').first().json.body || {};
const phone = normPhone(b.phone);
const exp = Number(b.exp);
let response;
// exp is capped so nobody can mint a long-lived code window to brute-force
if (!(exp > Date.now()) || exp - Date.now() > 10 * 60 * 1000 + 5000) response = { status: 'expired', message: 'That code has expired. Ask for a new one.' };
else if (!safeEq(digits(b.code), loginCode(phone, exp))) response = { status: 'wrong_code', message: "That code isn't right." };
else response = { status: 'ok', token: makeToken(phone), registered: !!userOf(phone) };
return [{ json: { response } }];
''', (480, 300))
    r = respond(wf, (720, 300))
    wf.chain(w, u, c, r)
    return wf


def wf_update_me():
    wf = Workflow("Brick - Update profile", "update-profile", "brick/me")
    w = webhook(wf, pos=(0, 300))
    u = sheet_read(wf, "Read users", "users", (240, 300))
    c = code(wf, "Prepare", r'''
const b = $('Webhook').first().json.body || {};
const phone = actorPhone(b.phone);
const user = phone ? userOf(phone) : null;
let ok = false, row = null, response;
if (phone === null) response = UNAUTHORISED;
else if (!user) response = { status: 'not_found', message: 'No account for that number yet.' };
else {
  row = { row_number: user.row_number };
  if (b.name !== undefined) {
    const name = String(b.name).trim();
    if (!name) response = { status: 'invalid', message: 'Name cannot be empty.' };
    row.name = name;
  }
  if (b.email_signature !== undefined) row.email_signature = String(b.email_signature).slice(0, 200);
  if (b.allow_international !== undefined) row.allow_international = truthy(b.allow_international) ? 'TRUE' : 'FALSE';
  // Only one Gmail is connected for the demo, so only the operator (tool secret) can grant it.
  if (b.email_connected !== undefined && isAdmin()) row.email_connected = truthy(b.email_connected) ? 'TRUE' : 'FALSE';
  if (!response) {
    ok = true;
    response = { status: 'saved', user: { phone: '+' + phone, name: row.name ?? user.name, ...prefsOf({ ...user, ...row }) } };
  }
}
return [{ json: { ok, row, response } }];
''', (480, 300))
    r = respond(wf, (720, 150))
    g = row_gate(wf, (720, 450))
    up = sheet_update(wf, "Save profile", "users", (960, 450))
    wf.chain(w, u, c); wf.link(c, r); wf.link(c, g); wf.link(g, up)
    return wf


# Shared check for editing a contact row: it must exist, belong to the caller, and still have the expected name
# (row numbers shift when rows are deleted, so the name guards against editing the wrong row).
CONTACT_ROW_CHECK = r'''
const b = $('Webhook').first().json.body || {};
const owner = actorPhone(b.owner_phone || b.caller_phone);
const all = rowsOf('Read contacts');
const target = owner ? all.find(r => Number(r.row_number) === Number(b.id)) : null;
let response = null;
if (owner === null) response = UNAUTHORISED;
else if (!target || normPhone(target.owner_phone) !== owner || norm(target.name) !== norm(b.match_name))
  response = { status: 'not_found', message: 'That contact has changed. Refresh and try again.' };
'''


def wf_update_contact():
    wf = Workflow("Brick - Update contact", "update-contact", "brick/contacts/update")
    w = webhook(wf, pos=(0, 300))
    ct = sheet_read(wf, "Read contacts", "contacts", (240, 300))
    c = code(wf, "Prepare", CONTACT_ROW_CHECK + r'''
let ok = false, row = null;
if (!response) {
  const name = String(b.name ?? target.name).trim();
  const phone = b.phone !== undefined ? (b.phone ? normPhone(b.phone) : '') : normPhone(target.phone);
  const email = String(b.email ?? target.email ?? '').trim();
  if (!name) response = { status: 'invalid', message: 'Missing contact name.' };
  else if (!phone && !email) response = { status: 'invalid', message: 'Need a phone number or an email.' };
  else if (phone && phone.length < 10) response = { status: 'invalid', message: 'That phone number looks too short.' };
  else if (all.some(r => r !== target && normPhone(r.owner_phone) === owner && norm(r.name) === norm(name)))
    response = { status: 'exists', message: `There is already a contact called ${name}.` };
  else {
    ok = true;
    row = { row_number: target.row_number, name, aliases: String(b.aliases ?? target.aliases ?? ''), phone: phone ? '+' + phone : '', email };
    response = { status: 'saved', name };
  }
}
return [{ json: { ok, row, response } }];
''', (480, 300))
    r = respond(wf, (720, 150))
    g = row_gate(wf, (720, 450))
    up = sheet_update(wf, "Save contact", "contacts", (960, 450))
    wf.chain(w, ct, c); wf.link(c, r); wf.link(c, g); wf.link(g, up)
    return wf


def wf_delete_contact():
    wf = Workflow("Brick - Delete contact", "delete-contact", "brick/contacts/delete")
    w = webhook(wf, pos=(0, 300))
    ct = sheet_read(wf, "Read contacts", "contacts", (240, 300))
    c = code(wf, "Prepare", CONTACT_ROW_CHECK + r'''
const ok = !response;
if (ok) response = { status: 'deleted', name: target.name };
return [{ json: { ok, row: ok ? { row_number: target.row_number } : null, response } }];
''', (480, 300))
    r = respond(wf, (720, 150))
    g = row_gate(wf, (720, 450))
    d = sheet_delete_row(wf, "Delete row", "contacts", (960, 450))
    wf.chain(w, ct, c); wf.link(c, r); wf.link(c, g); wf.link(g, d)
    return wf


def wf_app():
    """Serves the dashboard page itself, so it's online whenever n8n is."""
    wf = Workflow("Brick - Dashboard app", "app", "brick/app")
    w = webhook(wf, method="GET", pos=(0, 300))
    with open(os.path.join(HERE, "dashboard", "index.html")) as fh:
        html = fh.read().replace("__API_BASE__", CFG["n8n_url"] + "/webhook").replace("__ASSISTANT__", CFG.get("assistant_name", "Brick"))
    wf.add("Respond", "n8n-nodes-base.respondToWebhook", 1.1, {
        "respondWith": "text", "responseBody": html,
        "options": {"responseHeaders": {"entries": [{"name": "Content-Type", "value": "text/html; charset=utf-8"}]}},
    }, (240, 300))
    wf.link(w, "Respond")
    return wf


WORKFLOWS = [
    wf_vonage_answer, wf_vonage_event, wf_init,
    wf_send_email, wf_set_reminder, wf_send_text,
    wf_register_user, wf_add_contact, wf_dashboard, wf_read_emails,
    wf_auth_request_code, wf_auth_verify, wf_update_me, wf_update_contact, wf_delete_contact, wf_app,
]


# ---------- n8n API ----------

def api(method, path, body=None):
    url = CFG["n8n_url"] + "/api/v1" + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "X-N8N-API-KEY": CFG.get("n8n_api_key", ""),
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode()
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:400]}")


def push(built):
    existing = {}
    cursor = None
    while True:
        q = "/workflows?limit=250" + (f"&cursor={cursor}" if cursor else "")
        page = api("GET", q)
        for w in page.get("data", []):
            existing[w["name"]] = w["id"]
        cursor = page.get("nextCursor")
        if not cursor:
            break

    for wf in built:
        body = wf.to_dict()
        try:
            if wf.name in existing:
                wid = existing[wf.name]
                api("PUT", f"/workflows/{wid}", body)
                action = "updated"
            else:
                wid = api("POST", "/workflows", body)["id"]
                action = "created"
        except RuntimeError as e:
            print(f"  FAILED  {wf.name}: {e}")
            continue
        try:
            api("POST", f"/workflows/{wid}/activate")
            status = "active"
        except RuntimeError as e:
            status = f"NOT active (open it in n8n, fix credentials, toggle Active). {e}"
        print(f"  {action:7} {wf.name}: {status}")


def main():
    out = os.path.join(HERE, "workflows")
    os.makedirs(out, exist_ok=True)
    built = [f() for f in WORKFLOWS]
    for i, wf in enumerate(built, 1):
        with open(os.path.join(out, f"{i:02d}-{wf.slug}.json"), "w") as fh:
            json.dump(wf.to_dict(), fh, indent=2)
    print(f"Wrote {len(built)} workflows to workflows/")

    if "--push" in sys.argv:
        if not CFG["n8n_url"] or not CFG.get("n8n_api_key"):
            sys.exit("Set n8n_url and n8n_api_key in config.json to push.")
        print("Pushing to n8n...")
        push(built)

    base = CFG["n8n_url"] or "https://YOUR-INSTANCE.app.n8n.cloud"
    print("\nProduction webhook URLs:")
    for wf in built:
        method = next(n["parameters"]["httpMethod"] for n in wf.nodes if n["name"] == "Webhook")
        print(f"  {method:4} {base}/webhook/{wf.path}   ({wf.name})")


if __name__ == "__main__":
    main()
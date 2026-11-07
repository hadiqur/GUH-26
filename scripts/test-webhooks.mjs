// Calls the production n8n webhooks and prints a PASS / FAIL / SKIP table.
//
//   node scripts/test-webhooks.mjs          safe checks: nothing is sent
//   node scripts/test-webhooks.mjs --live   also sends one real text and sets one
//                                           reminder (2 minutes out) to TEST_RECIPIENT_PHONE
//
// Reads .env from the repo root (see .env.example). Exits 1 if any check fails.
// A webhook that isn't built or active yet (n8n answers 404) is SKIP, not FAIL.

import { existsSync, readFileSync } from 'node:fs';
import { createInterface } from 'node:readline/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

// All webhook paths, relative to N8N_WEBHOOK_BASE.
const PATHS = {
  vonageAnswer: 'vonage-answer',
  init: 'init',
  registerUser: 'register_user',
  sendEmail: 'send_email',
  sendText: 'send_text',
  setReminder: 'set_reminder',
};
const TOOLS = ['registerUser', 'sendEmail', 'sendText', 'setReminder'];
const UNKNOWN_CALLER = '+447700900999'; // drama number, never seeded
const NOBODY = 'Zebedee Nobody';

if (process.env.NODE_TEST_CONTEXT) {
  // `node --test` finds this file by its name (test-*). It needs live webhooks, so skip it there.
  const { test } = await import('node:test');
  test('webhook checks: run node scripts/test-webhooks.mjs', { skip: 'needs live n8n webhooks' }, () => {});
} else {
  await main();
}

async function main() {
// --- .env (tiny parser: KEY=value, # comments, optional quotes) --------------

function loadEnv(file) {
  if (!existsSync(file)) return;
  for (const line of readFileSync(file, 'utf8').split(/\r?\n/)) {
    const m = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/.exec(line);
    if (!m) continue;
    let value = m[2].trim();
    if (/^(["']).*\1$/.test(value)) value = value.slice(1, -1);
    else value = value.replace(/\s+#.*$/, '');
    if (process.env[m[1]] === undefined) process.env[m[1]] = value;
  }
}

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
loadEnv(path.join(root, '.env'));

const BASE = (process.env.N8N_WEBHOOK_BASE || '').replace(/\/+$/, '');
const SECRET = process.env.TOOL_SECRET || '';
const VONAGE_NUMBER = process.env.VONAGE_NUMBER || '';
const DEMO = process.env.DEMO_USER_PHONE || '+447700900123';
const RECIPIENT = process.env.TEST_RECIPIENT_PHONE || '';
const LIVE = process.argv.includes('--live');

if (!BASE) {
  console.error('N8N_WEBHOOK_BASE is not set. Copy .env.example to .env and fill it in.');
  process.exit(2);
}

// --- HTTP ---------------------------------------------------------------------

async function call(name, { method = 'POST', query, body, secret = SECRET } = {}) {
  const url = new URL(`${BASE}/${PATHS[name]}`);
  for (const [k, v] of Object.entries(query || {})) url.searchParams.set(k, v);
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (secret !== null) headers['X-Tool-Secret'] = secret;
  try {
    const res = await fetch(url, {
      method, headers, body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(20000),
    });
    const text = await res.text();
    let json = null;
    try { json = JSON.parse(text); } catch { /* not JSON */ }
    return { status: res.status, json, text };
  } catch (err) {
    return { status: 0, json: null, text: String(err.message || err) };
  }
}

// --- checks -------------------------------------------------------------------

const results = [];
const pass = (detail = '') => ({ result: 'PASS', detail });
const fail = (detail) => ({ result: 'FAIL', detail });
const skip = (detail) => ({ result: 'SKIP', detail });
const short = (res) => `HTTP ${res.status} ${(res.text || '').replace(/\s+/g, ' ').slice(0, 90)}`;

async function check(name, fn) {
  let out;
  try { out = await fn(); } catch (err) { out = fail(`error: ${err.message}`); }
  results.push({ name, ...out });
}

/** SKIP when the webhook isn't registered yet, FAIL on network errors. */
function unavailable(res) {
  if (res.status === 404) return skip('webhook not built or not active (404)');
  if (res.status === 0) return fail(`network error: ${res.text}`);
  return null;
}

const digits = (s) => String(s).replace(/\D/g, '');
const expectedUri = VONAGE_NUMBER ? `sip:+${digits(VONAGE_NUMBER)}@sip.rtc.elevenlabs.io:5061;transport=tls` : null;

await check('vonage-answer: normal call connects over SIP', async () => {
  const res = await call('vonageAnswer', {
    method: 'GET', secret: null,
    query: { from: digits(DEMO), to: digits(VONAGE_NUMBER || '447700900000'), uuid: 'webhook-test-uuid' },
  });
  const u = unavailable(res); if (u) return u;
  const ncco = res.json;
  if (!Array.isArray(ncco) || ncco.length !== 1 || ncco[0].action !== 'connect') return fail(`want [connect], got ${short(res)}`);
  const ep = (ncco[0].endpoint || [])[0] || {};
  if (ep.type !== 'sip') return fail(`endpoint type ${ep.type}`);
  if (expectedUri ? ep.uri !== expectedUri : !/^sip:\+\d+@sip\.rtc\.elevenlabs\.io:5061;transport=tls$/.test(ep.uri || '')) {
    return fail(`uri ${ep.uri}`);
  }
  if ((ep.headers || {})['CALLER-ID'] !== DEMO) return fail(`CALLER-ID ${(ep.headers || {})['CALLER-ID']}`);
  return pass(expectedUri ? ep.uri : `${ep.uri} (VONAGE_NUMBER not set, pattern only)`);
});

await check('vonage-answer: hidden caller gets talk, no connect', async () => {
  const res = await call('vonageAnswer', { method: 'GET', secret: null, query: { from: '', to: digits(VONAGE_NUMBER || '447700900000'), uuid: 'webhook-test-hidden' } });
  const u = unavailable(res); if (u) return u;
  const ncco = Array.isArray(res.json) ? res.json : [];
  if (!ncco.some((a) => a.action === 'talk')) return fail(`no talk action: ${short(res)}`);
  if (ncco.some((a) => a.action === 'connect')) return fail('has a connect action');
  return pass();
});

await check('init: known caller', async () => {
  const res = await call('init', { body: { caller_id: DEMO, agent_id: 'webhook-test', called_number: VONAGE_NUMBER, call_sid: 'webhook-test' } });
  const u = unavailable(res); if (u) return u;
  const dv = (res.json || {}).dynamic_variables || {};
  if ((res.json || {}).type !== 'conversation_initiation_client_data') return fail(`wrong type: ${short(res)}`);
  if (!dv.user_name) return fail('user_name is empty');
  if (((dv.contact_names || '').match(/Sarah/g) || []).length < 2) return fail(`contact_names: "${dv.contact_names}"`);
  if (!dv.now) return fail('now is missing');
  return pass(`user_name ${dv.user_name}, contacts: ${dv.contact_names}`);
});

await check(`init: unknown caller ${UNKNOWN_CALLER} is new`, async () => {
  const res = await call('init', { body: { caller_id: UNKNOWN_CALLER, agent_id: 'webhook-test', called_number: VONAGE_NUMBER, call_sid: 'webhook-test' } });
  const u = unavailable(res); if (u) return u;
  const dv = (res.json || {}).dynamic_variables || {};
  return dv.is_new_user === true ? pass() : fail(`is_new_user = ${JSON.stringify(dv.is_new_user)}`);
});

// Bodies chosen so nothing gets sent even if a webhook wrongly accepts them.
const harmless = {
  caller_phone: UNKNOWN_CALLER, contact_name: NOBODY, name: '', message: 'secret check',
  subject: 'secret check', body: 'secret check', text: 'secret check', remind_at: '2000-01-01T00:00:00Z',
};
for (const tool of TOOLS) {
  await check(`${PATHS[tool]}: rejects missing and wrong X-Tool-Secret`, async () => {
    for (const [label, secret] of [['missing', null], ['wrong', 'wrong-secret-for-testing']]) {
      const res = await call(tool, { body: harmless, secret });
      const u = unavailable(res); if (u) return u;
      if (res.status < 400 || res.status >= 500) return fail(`${label} secret accepted: ${short(res)}`);
    }
    return pass('4xx for both');
  });
}

await check('send_text: "Sarah" is ambiguous', async () => {
  const res = await call('sendText', { body: { caller_phone: DEMO, contact_name: 'Sarah', message: 'Webhook test: this must not be sent.' } });
  const u = unavailable(res); if (u) return u;
  const j = res.json || {};
  const options = Array.isArray(j.options) ? j.options : [];
  if (j.status !== 'ambiguous' || options.length < 2 || !options.every((o) => /sarah/i.test(o))) return fail(short(res));
  return pass(options.join(', '));
});

for (const tool of ['sendText', 'sendEmail']) {
  await check(`${PATHS[tool]}: unknown name is not_found`, async () => {
    const res = await call(tool, { body: { caller_phone: DEMO, contact_name: NOBODY, message: 'Webhook test.', subject: 'Webhook test', body: 'Webhook test.' } });
    const u = unavailable(res); if (u) return u;
    return (res.json || {}).status === 'not_found' ? pass() : fail(short(res));
  });
}

// --- live checks (send real messages) ---------------------------------------

if (LIVE) {
  if (!RECIPIENT) {
    results.push({ name: 'live checks', ...fail('TEST_RECIPIENT_PHONE is not set') });
  } else {
    const rl = createInterface({ input: process.stdin, output: process.stdout });
    const answer = await rl.question(`--live sends a real text and sets a real reminder to ${RECIPIENT}. Type yes to continue: `);
    rl.close();
    if (answer.trim().toLowerCase() !== 'yes') {
      results.push({ name: 'live checks', ...skip('not confirmed') });
    } else {
      await check('LIVE send_text to TEST_RECIPIENT_PHONE', async () => {
        const res = await call('sendText', { body: { caller_phone: DEMO, contact_name: RECIPIENT, message: 'Brick webhook test. Please ignore.' } });
        const u = unavailable(res); if (u) return u;
        return (res.json || {}).status === 'sent' ? pass(`parts ${(res.json || {}).parts}`) : fail(short(res));
      });
      await check('LIVE set_reminder 2 minutes out', async () => {
        const remindAt = new Date(Date.now() + 2 * 60 * 1000).toISOString();
        const res = await call('setReminder', { body: { caller_phone: RECIPIENT, text: 'Brick webhook test reminder', remind_at: remindAt } });
        const u = unavailable(res); if (u) return u;
        return (res.json || {}).status === 'set' ? pass(`when: ${(res.json || {}).when}, watch for the text`) : fail(short(res));
      });
    }
  }
}

// --- report -------------------------------------------------------------------

const width = Math.max(...results.map((r) => r.name.length));
console.log(`\nn8n webhooks at ${BASE}\n`);
console.log(`${'check'.padEnd(width)}  result  detail`);
console.log(`${'-'.repeat(width)}  ------  ------`);
for (const r of results) console.log(`${r.name.padEnd(width)}  ${r.result.padEnd(6)}  ${r.detail || ''}`);
const count = (k) => results.filter((r) => r.result === k).length;
console.log(`\n${count('PASS')} passed, ${count('FAIL')} failed, ${count('SKIP')} skipped`);
// exitCode, not process.exit(): exiting while fetch sockets close crashes Node on Windows.
process.exitCode = count('FAIL') ? 1 : 0;
}

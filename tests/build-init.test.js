const test = require('node:test');
const assert = require('node:assert/strict');
const { loadSnippets } = require('./helpers');

const { buildInit, formatLondonNow } = loadSnippets('normalise-phone.js', 'build-init.js');

const ADAM = '+447700900123';
const PRIYA = '+447700900002';
const users = [
  { phone: ADAM, name: 'Adam', created_at: '2026-11-07T12:00:00Z' },
  { phone: '447700900002', name: 'Priya', created_at: '2026-11-07T12:00:00Z' }, // "+" lost in the Sheet
];
const contacts = [
  { owner_phone: ADAM, name: 'Mum', aliases: 'Mom, Mam, Mother', phone: '+447700900101', email: 'mum@example.com' },
  { owner_phone: ADAM, name: 'Dad', aliases: 'Father, Pops', phone: '+447700900102', email: 'dad@example.com' },
  { owner_phone: ADAM, name: 'Sarah Khan', aliases: 'Sarah', phone: '+447700900103', email: 'sarah.khan@example.com' },
  { owner_phone: ADAM, name: 'Sarah Lee', aliases: 'Sarah', phone: '+447700900104', email: 'sarah.lee@example.com' },
  { owner_phone: PRIYA, name: 'Ben', aliases: 'Benny', phone: '+447700900201', email: 'ben@example.com' },
];
// 14:30 in London on 7 Nov 2026 (GMT, so the same as UTC).
const NOW = new Date('2026-11-07T14:30:00Z');

test('known caller gets name, own contacts and London time', () => {
  assert.deepEqual(buildInit({ callerPhone: '447700900123', users, contacts, now: NOW }), {
    type: 'conversation_initiation_client_data',
    dynamic_variables: {
      caller_phone: ADAM,
      user_name: 'Adam',
      is_new_user: false,
      contact_names: 'Mum, Dad, Sarah Khan, Sarah Lee',
      now: 'Saturday 7 November 2026, 14:30, Europe/London',
    },
  });
});

test("Priya only sees her own contacts, and Adam never sees Ben", () => {
  const priya = buildInit({ callerPhone: PRIYA, users, contacts, now: NOW }).dynamic_variables;
  assert.equal(priya.user_name, 'Priya');
  assert.equal(priya.contact_names, 'Ben');
  const adam = buildInit({ callerPhone: ADAM, users, contacts, now: NOW }).dynamic_variables;
  assert.doesNotMatch(adam.contact_names, /Ben/);
});

test('unknown number is a new user with no name and no contacts', () => {
  const res = buildInit({ callerPhone: '+447700900999', users, contacts, now: NOW });
  assert.equal(res.dynamic_variables.is_new_user, true);
  assert.equal(res.dynamic_variables.user_name, '');
  assert.equal(res.dynamic_variables.contact_names, '');
  assert.equal(res.dynamic_variables.caller_phone, '+447700900999');
  assert.match(res.conversation_config_override.agent.first_message, /AI assistant/);
});

test('known users get no first-message override', () => {
  assert.equal(buildInit({ callerPhone: ADAM, users, contacts, now: NOW }).conversation_config_override, undefined);
});

test('now is London time, including summer time', () => {
  assert.equal(formatLondonNow(new Date('2026-07-04T19:05:00Z')), 'Saturday 4 July 2026, 20:05, Europe/London');
  assert.equal(formatLondonNow(new Date('2026-11-07T00:00:00Z')), 'Saturday 7 November 2026, 00:00, Europe/London');
});

// The seed CSVs must match the plan's columns, contain only safe placeholder
// data, and work with the snippets for the demo.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { loadSnippets, readCsv } = require('./helpers');

const { buildInit } = loadSnippets('normalise-phone.js', 'build-init.js');
const { findContact } = loadSnippets('normalise-phone.js', 'find-contact.js');

const header = (name) => fs.readFileSync(path.join(__dirname, '..', 'sheet', name), 'utf8').split(/\r?\n/)[0];
const users = readCsv('users.csv');
const contacts = readCsv('contacts.csv');
const ADAM = '+447700900123';

test('columns match the plan exactly', () => {
  assert.equal(header('users.csv'), 'phone,name,created_at');
  assert.equal(header('contacts.csv'), 'owner_phone,name,aliases,phone,email');
  assert.equal(header('reminders.csv'), 'id,owner_phone,text,remind_at,status,created_at');
  assert.deepEqual(readCsv('reminders.csv'), []);
});

test('only Ofcom drama numbers and example.com emails', () => {
  for (const phone of [...users.map((u) => u.phone), ...contacts.flatMap((c) => [c.owner_phone, c.phone])]) {
    assert.match(phone, /^\+447700900\d{3}$/, phone);
  }
  for (const c of contacts) assert.match(c.email, /^[a-z.]+@example\.com$/, c.email);
});

test('every contact owner is a seeded user', () => {
  const owners = new Set(users.map((u) => u.phone));
  for (const c of contacts) assert.ok(owners.has(c.owner_phone), c.name);
});

test('the demo works with the seed: Adam sees both Sarahs, "Sarah" is ambiguous', () => {
  const vars = buildInit({ callerPhone: ADAM, users, contacts, now: new Date() }).dynamic_variables;
  assert.equal(vars.user_name, 'Adam');
  assert.equal(vars.contact_names, 'Mum, Dad, Sarah Khan, Sarah Lee, Alex');
  assert.deepEqual(findContact(contacts, ADAM, 'Sarah'), { status: 'ambiguous', options: ['Sarah Khan', 'Sarah Lee'] });
  assert.equal(findContact(contacts, ADAM, 'Mam').contact.email, 'mum@example.com');
  assert.equal(buildInit({ callerPhone: '+447700900999', users, contacts }).dynamic_variables.is_new_user, true);
});

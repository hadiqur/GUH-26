const test = require('node:test');
const assert = require('node:assert/strict');
const { loadSnippets } = require('./helpers');

const { findContact, normaliseName, levenshtein } = loadSnippets('normalise-phone.js', 'find-contact.js');

const ADAM = '+447700900123';
const PRIYA = '+447700900002';
const contacts = [
  { owner_phone: ADAM, name: 'Mum', aliases: 'Mom, Mam, Mother', phone: '+447700900101', email: 'mum@example.com' },
  { owner_phone: ADAM, name: 'Dad', aliases: 'Father, Pops', phone: '+447700900102', email: 'dad@example.com' },
  { owner_phone: ADAM, name: 'Sarah Khan', aliases: 'Sarah', phone: '+447700900103', email: 'sarah.khan@example.com' },
  { owner_phone: ADAM, name: 'Sarah Lee', aliases: 'Sarah', phone: '447700900104', email: 'sarah.lee@example.com' },
  { owner_phone: ADAM, name: 'Alex', aliases: '', phone: '+447700900105', email: 'alex@example.com' },
  { owner_phone: PRIYA, name: 'Ben', aliases: 'Benny', phone: '+447700900201', email: 'ben@example.com' },
];
const name = (r) => r.contact && r.contact.name;

test('exact name and alias matches, ignoring case and punctuation', () => {
  assert.equal(name(findContact(contacts, ADAM, 'Mum')), 'Mum');
  assert.equal(name(findContact(contacts, ADAM, 'MUM!')), 'Mum');
  assert.equal(name(findContact(contacts, ADAM, 'mom')), 'Mum');
  assert.equal(findContact(contacts, ADAM, 'mom').match, 'alias');
  assert.equal(name(findContact(contacts, ADAM, 'pops')), 'Dad');
  assert.equal(name(findContact(contacts, ADAM, '  sarah   KHAN ')), 'Sarah Khan');
});

test('"Sarah" is ambiguous between the two Sarahs', () => {
  assert.deepEqual(findContact(contacts, ADAM, 'Sarah'), { status: 'ambiguous', options: ['Sarah Khan', 'Sarah Lee'] });
});

test('found contact phone is normalised to E.164', () => {
  assert.equal(findContact(contacts, ADAM, 'Sarah Lee').contact.phone, '+447700900104');
});

test('a full-name match beats an alias-only match', () => {
  const rows = [
    { owner_phone: ADAM, name: 'Sarah', aliases: '', phone: '+447700900110' },
    { owner_phone: ADAM, name: 'Sarah Khan', aliases: 'Sarah', phone: '+447700900103' },
  ];
  const res = findContact(rows, ADAM, 'sarah');
  assert.equal(res.status, 'found');
  assert.equal(res.contact.phone, '+447700900110');
  assert.equal(res.match, 'name');
});

test('only the owner\'s rows are considered', () => {
  assert.deepEqual(findContact(contacts, ADAM, 'Ben'), { status: 'not_found' });
  assert.equal(name(findContact(contacts, '447700900002', 'benny')), 'Ben');
  assert.deepEqual(findContact(contacts, PRIYA, 'Mum'), { status: 'not_found' });
});

test('accents are ignored', () => {
  const rows = [{ owner_phone: ADAM, name: 'Siobhán Nguyễn', aliases: 'Shiv', phone: '+447700900120' }];
  assert.equal(findContact(rows, ADAM, 'siobhan nguyen').status, 'found');
});

test('misheard names fall back to fuzzy matching', () => {
  assert.equal(name(findContact(contacts, ADAM, 'Alx')), 'Alex'); // distance 1, short name
  assert.equal(findContact(contacts, ADAM, 'Alx').match, 'fuzzy');
  assert.equal(name(findContact(contacts, ADAM, 'Sara Khan')), 'Sarah Khan'); // distance 1
  assert.equal(name(findContact(contacts, ADAM, 'Sarah Kahn')), 'Sarah Khan'); // distance 2, long name
  assert.deepEqual(findContact(contacts, ADAM, 'Sara Kahn'), { status: 'not_found' }); // distance 3
  assert.deepEqual(findContact(contacts, ADAM, 'Sara'), { status: 'ambiguous', options: ['Sarah Khan', 'Sarah Lee'] });
  assert.deepEqual(findContact(contacts, ADAM, 'Axel'), { status: 'not_found' }); // distance 2, short name
  assert.deepEqual(findContact(contacts, ADAM, 'Zebedee Nobody'), { status: 'not_found' });
});

test('a phone number is returned as found with no name', () => {
  assert.deepEqual(findContact(contacts, ADAM, '07700 900555'),
    { status: 'found', contact: { name: null, phone: '+447700900555' }, match: 'phone' });
  assert.deepEqual(findContact(contacts, ADAM, '0770 090'), { status: 'not_found' });
});

test('empty input', () => {
  assert.deepEqual(findContact(contacts, ADAM, ''), { status: 'not_found' });
  assert.deepEqual(findContact(contacts, '', 'Mum'), { status: 'not_found' });
  assert.deepEqual(findContact([], ADAM, 'Mum'), { status: 'not_found' });
});

test('helpers', () => {
  assert.equal(normaliseName("  O'Brien-Smith "), 'o brien smith');
  assert.equal(levenshtein('kitten', 'sitting'), 3);
  assert.equal(levenshtein('', 'abc'), 3);
});

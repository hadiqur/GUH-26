const test = require('node:test');
const assert = require('node:assert/strict');
const { loadSnippets } = require('./helpers');

const { checkRemindAt, humanWhen } = loadSnippets('reminder.js');

const NOW = new Date('2026-11-07T14:30:00Z'); // Saturday, GMT
const SUMMER = new Date('2026-07-04T10:00:00Z'); // Saturday, BST

test('valid future times', () => {
  for (const iso of ['2026-11-07T20:00:00+00:00', '2026-11-07T20:00:00Z', '2026-11-07T20:00:00.000Z',
    '2026-11-07T20:00', '2026-11-07 20:00:00', '2026-11-07T21:00:00+01:00', '2026-11-07T20:00:00+0000']) {
    const r = checkRemindAt(iso, NOW);
    assert.equal(r.ok, true, iso);
    assert.equal(r.iso, '2026-11-07T20:00:00.000Z', iso);
    assert.ok(r.date instanceof Date);
  }
});

test('times without an offset are London time, including BST', () => {
  assert.equal(checkRemindAt('2026-07-04T20:00:00', SUMMER).iso, '2026-07-04T19:00:00.000Z');
  assert.equal(checkRemindAt('2026-11-07T20:00:00', NOW).iso, '2026-11-07T20:00:00.000Z');
});

test('past times never reach the Wait node', () => {
  assert.deepEqual(checkRemindAt('2026-11-07T14:00:00Z', NOW), { ok: false, reason: 'in_past' });
  assert.deepEqual(checkRemindAt('2026-11-07T14:30:00Z', NOW), { ok: false, reason: 'in_past' });
  assert.deepEqual(checkRemindAt('2025-11-07T20:00:00Z', NOW), { ok: false, reason: 'in_past' });
});

test('more than 7 days out is too far', () => {
  assert.equal(checkRemindAt('2026-11-14T14:30:00Z', NOW).ok, true); // exactly 7 days
  assert.deepEqual(checkRemindAt('2026-11-14T14:31:00Z', NOW), { ok: false, reason: 'too_far' });
});

test('invalid input', () => {
  for (const iso of [undefined, null, '', '8pm', 'tomorrow at 8', '2026-13-01T10:00:00Z',
    '2026-02-30T10:00:00Z', '2026-11-07T25:00:00Z', '2026-11-07T20:61:00Z', '07/11/2026 20:00']) {
    assert.deepEqual(checkRemindAt(iso, NOW), { ok: false, reason: 'invalid' }, String(iso));
  }
});

test('humanWhen phrases in London time', () => {
  assert.equal(humanWhen('2026-11-07T20:00:00Z', NOW), '8pm today');
  assert.equal(humanWhen('2026-11-07T20:30:00Z', NOW), '8:30pm today');
  assert.equal(humanWhen('2026-11-08T09:00:00Z', NOW), '9am tomorrow');
  assert.equal(humanWhen('2026-11-08T12:00:00Z', NOW), 'noon tomorrow');
  assert.equal(humanWhen('2026-11-08T00:00:00Z', NOW), 'midnight tomorrow');
  assert.equal(humanWhen('2026-11-09T09:05:00Z', NOW), '9:05am on Monday');
  assert.equal(humanWhen('2026-11-14T09:00:00Z', NOW), '9am on Saturday 14 November');
  assert.equal(humanWhen('2026-07-04T19:00:00Z', SUMMER), '8pm today'); // BST
  assert.equal(humanWhen(new Date('2026-11-07T15:00:00Z'), NOW), '3pm today');
  assert.equal(humanWhen('nonsense', NOW), '');
});

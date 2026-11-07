// Ported from the archived tests/test_phone.py (tag archive/dial-a-text).
const test = require('node:test');
const assert = require('node:assert/strict');
const { loadSnippets } = require('./helpers');

const { toE164, isUkMobile } = loadSnippets('normalise-phone.js');
const E164 = '+447700900123';

test('toE164 accepts the common formats', () => {
  for (const raw of [
    '07700 900123',
    '07700900123',
    '+44 7700 900123',
    '+447700900123',
    '447700900123', // Vonage: digits, no plus
    '0044 7700 900123',
    '07700-900-123',
    '(07700) 900123',
    ' +44 (7700) 900-123 ',
    '+44 (0)7700 900123',
  ]) {
    assert.equal(toE164(raw), E164, raw);
  }
});

test('toE164 returns null for garbage', () => {
  for (const raw of [null, undefined, '', '   ', 'hello', '07700 9001', '12345', '+44',
    '0770090012345678', '+44 7700 abc123', '++447700900123']) {
    assert.equal(toE164(raw), null, String(raw));
  }
});

test('toE164 returns null for withheld caller IDs', () => {
  for (const raw of ['', 'anonymous', 'Anonymous', 'UNKNOWN', 'withheld', 'Withheld', 'private']) {
    assert.equal(toE164(raw), null, raw);
  }
});

test('toE164 keeps real-format UK and valid non-UK numbers', () => {
  assert.equal(toE164('07911 123456'), '+447911123456');
  assert.equal(toE164('+1 202 555 0143'), '+12025550143');
  assert.equal(toE164(447700900123), E164); // a number, as a Sheet cell may give it
});

test('isUkMobile', () => {
  assert.equal(isUkMobile('+447700900123'), true); // Ofcom drama range
  assert.equal(isUkMobile('+447911123456'), true);
  assert.equal(isUkMobile('+442079460000'), false); // London landline
  assert.equal(isUkMobile('+12025550143'), false);
  assert.equal(isUkMobile(null), false);
  assert.equal(isUkMobile(''), false);
});

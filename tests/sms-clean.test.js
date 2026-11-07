const test = require('node:test');
const assert = require('node:assert/strict');
const { loadSnippets } = require('./helpers');

const { cleanSms, smsParts, formatText } = loadSnippets('sms-clean.js');

const BIRTHDAY =
  "Happy birthday Mum! 🎂🎉 Hope you have a wonderful day. I've booked the table at Luigi's " +
  "for 7pm, Dad knows. Love you lots ❤️ see you tonight";

test('smsParts: GSM-7 boundaries', () => {
  assert.deepEqual(smsParts(''), { parts: 1, encoding: 'GSM-7' });
  assert.deepEqual(smsParts('Hi Mum'), { parts: 1, encoding: 'GSM-7' });
  assert.deepEqual(smsParts('a'.repeat(160)), { parts: 1, encoding: 'GSM-7' });
  assert.deepEqual(smsParts('a'.repeat(161)), { parts: 2, encoding: 'GSM-7' });
  assert.deepEqual(smsParts('a'.repeat(306)), { parts: 2, encoding: 'GSM-7' });
  assert.deepEqual(smsParts('a'.repeat(307)), { parts: 3, encoding: 'GSM-7' });
  assert.deepEqual(smsParts('£5 for Ñandú? ¿Sí! Ø@'), { parts: 1, encoding: 'Unicode' }); // ú, í are not GSM
  assert.deepEqual(smsParts('£5, Ñ, é, ü, Ø @ ¿'), { parts: 1, encoding: 'GSM-7' });
});

test('smsParts: extension characters cost two units', () => {
  assert.deepEqual(smsParts('€'.repeat(80)), { parts: 1, encoding: 'GSM-7' });
  assert.deepEqual(smsParts('€'.repeat(81)), { parts: 2, encoding: 'GSM-7' });
  assert.deepEqual(smsParts('{}[]~|^\\'), { parts: 1, encoding: 'GSM-7' });
});

test('smsParts: Unicode boundaries and emoji as two UTF-16 units', () => {
  assert.deepEqual(smsParts('ł'.repeat(70)), { parts: 1, encoding: 'Unicode' });
  assert.deepEqual(smsParts('ł'.repeat(71)), { parts: 2, encoding: 'Unicode' });
  assert.deepEqual(smsParts('ł'.repeat(134)), { parts: 2, encoding: 'Unicode' });
  assert.deepEqual(smsParts('ł'.repeat(135)), { parts: 3, encoding: 'Unicode' });
  assert.deepEqual(smsParts('😊'.repeat(35)), { parts: 1, encoding: 'Unicode' });
  assert.deepEqual(smsParts('😊'.repeat(36)), { parts: 2, encoding: 'Unicode' });
  // Same answer as the old Python sms_parts gave for this seed message.
  assert.deepEqual(smsParts(BIRTHDAY), { parts: 3, encoding: 'Unicode' });
});

test('cleanSms swaps typographic characters for plain ones', () => {
  assert.equal(cleanSms('It’s “fine” – really… ok — ‘yes’'), 'It\'s "fine" - really... ok - \'yes\'');
  assert.equal(cleanSms('see you soon'), 'see you soon');
});

test('cleanSms removes emoji, including joined and flag sequences', () => {
  assert.equal(cleanSms('Thanks 😊!'), 'Thanks!');
  assert.equal(cleanSms('Love you ❤️ x'), 'Love you x');
  assert.equal(cleanSms('Family 👨‍👩‍👧 trip 🇬🇧 👍🏽'), 'Family trip');
  assert.equal(cleanSms(null), '');
});

test('cleaning drops the birthday text from 3 Unicode parts to 1 GSM-7 part', () => {
  const clean = cleanSms(BIRTHDAY);
  assert.match(clean, /^Happy birthday Mum! Hope you have/);
  assert.deepEqual(smsParts(clean), { parts: 1, encoding: 'GSM-7' });
});

test('formatText prefixes the sender name', () => {
  assert.equal(formatText('Adam', 'I’ll be late, save me dinner 🍝'), "Adam: I'll be late, save me dinner");
  assert.equal(formatText('', 'Hello'), 'Hello');
});

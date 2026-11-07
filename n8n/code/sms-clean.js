// sms-clean.js: cleanSms(text), smsParts(text), formatText(userName, message)
//
// Used by: workflow `send_text` (Code node "Format text", after the contact
// lookup) and `set_reminder` (Code node before the Vonage SMS node).
//
// One emoji or curly quote switches a whole SMS from GSM-7 (160 characters a
// part) to Unicode (70 a part). cleanSms swaps those for plain characters.
// smsParts is a faithful port of the archived Python sms_parts (tag
// archive/dial-a-text): GSM 03.38 basic set plus the extension table (which
// costs 2 units each), otherwise UTF-16 code units.
//
// Paste everything above the export guard into a Code node, then add e.g.:
//   return $input.all().map((item) => {
//     const text = formatText(item.json.user_name, item.json.message);
//     return { json: { ...item.json, text, ...smsParts(text) } };
//   });

const GSM7_BASIC = new Set(
  '@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !"#¤%&\'()*+,-./0123456789:;<=>?' +
  '¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà'
);
const GSM7_EXTENSION = new Set('^{}\\[~]|€\f');

const SMS_REPLACEMENTS = [
  [/[‘’‚‛′]/g, "'"], // curly single quotes, prime
  [/[“”„‟″]/g, '"'], // curly double quotes
  [/[‐-―−]/g, '-'], // hyphens, en and em dashes, minus
  [/…/g, '...'], // ellipsis
  [/[  -   　]/g, ' '], // non-breaking and other spaces
];
// Emoji, plus the invisible pieces emoji are built from.
const EMOJI_PATTERN = /[\p{Extended_Pictographic}\u{1F1E6}-\u{1F1FF}\u{1F3FB}-\u{1F3FF}​-‍⃣︎️﻿]/gu;

function cleanSms(text) {
  let s = String(text ?? '');
  for (const [pattern, plain] of SMS_REPLACEMENTS) s = s.replace(pattern, plain);
  s = s.replace(EMOJI_PATTERN, '');
  return s.replace(/[ \t]{2,}/g, ' ').replace(/ +([,.!?])/g, '$1').trim();
}

function smsParts(text) {
  const s = String(text ?? '');
  let units = 0;
  let gsm = true;
  for (const ch of s) {
    if (GSM7_EXTENSION.has(ch)) units += 2;
    else if (GSM7_BASIC.has(ch)) units += 1;
    else { gsm = false; break; }
  }
  if (gsm) return { parts: units <= 160 ? 1 : Math.ceil(units / 153), encoding: 'GSM-7' };
  const utf16 = s.length; // JS string length is UTF-16 code units
  return { parts: utf16 <= 70 ? 1 : Math.ceil(utf16 / 67), encoding: 'Unicode' };
}

function formatText(userName, message) {
  const name = cleanSms(userName);
  const body = cleanSms(message);
  return name ? `${name}: ${body}` : body;
}

if (typeof module !== 'undefined') module.exports = { cleanSms, smsParts, formatText };

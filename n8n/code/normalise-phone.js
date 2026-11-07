// normalise-phone.js: toE164(raw), isUkMobile(e164)
//
// Used by: workflow `vonage-answer` (Code node "Build NCCO"), and pasted above
// build-init.js / find-contact.js in `init`, `send_text` and `send_email`.
//
// Hand-written, lighter replacement for libphonenumber, which n8n cloud can't
// load. Known differences from libphonenumber:
//   - No per-country validation: any "+" plus 8-15 digits is accepted
//     (libphonenumber would reject e.g. "+12345678").
//   - Digits with no leading 0 or + are always international, so "7700900123"
//     becomes "+7700900123", not a UK number.
//   - National format is UK only: a leading 0 needs exactly 10 more digits.
//   - isUkMobile accepts every +447 number with 9 more digits, including 070
//     personal numbers and 076 pagers, which libphonenumber doesn't call mobile.
//   - Ofcom drama numbers (07700 900000-900999) are valid here; libphonenumber
//     says they're invalid.
//
// Paste everything above the export guard into a Code node, then add e.g.:
//   return $input.all().map((item) => ({
//     json: { ...item.json, caller_phone: toE164(item.json.query.from) },
//   }));

const WITHHELD_VALUES = ['', 'anonymous', 'unknown', 'withheld', 'private', 'restricted'];
const E164_PATTERN = /^\+[1-9]\d{7,14}$/;
const UK_MOBILE_PATTERN = /^\+447\d{9}$/;

function toE164(raw) {
  if (raw === null || raw === undefined) return null;
  let s = String(raw).trim();
  if (WITHHELD_VALUES.includes(s.toLowerCase())) return null;
  s = s.replace(/[\s\-.()[\]]/g, '');
  if (s.startsWith('00')) s = '+' + s.slice(2); // 0044... -> +44...
  else if (/^0\d{10}$/.test(s)) s = '+44' + s.slice(1); // 07700900123 -> +447700900123
  else if (/^[1-9]\d*$/.test(s)) s = '+' + s; // Vonage sends 447700900123
  if (s.startsWith('+440')) s = '+44' + s.slice(4); // "+44 (0)7700..." style
  return E164_PATTERN.test(s) ? s : null;
}

function isUkMobile(e164) {
  return typeof e164 === 'string' && UK_MOBILE_PATTERN.test(e164);
}

if (typeof module !== 'undefined') module.exports = { toE164, isUkMobile };

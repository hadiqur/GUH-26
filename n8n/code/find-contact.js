// find-contact.js: findContact(contacts, ownerPhone, query)
//   -> { status: "found", contact, match } | { status: "ambiguous", options: [names] } | { status: "not_found" }
//
// Used by: workflows `send_text` and `send_email`, Code node "Find contact",
// after a Google Sheets "Get row(s)" node named "Contacts". Follow it with an
// IF/Switch on {{ $json.status }}; return the ambiguous/not_found result to
// the agent as-is.
//
// Paste normalise-phone.js first, then everything above the export guard
// below, into the same Code node. Then add:
//   const body = $('Webhook').first().json.body;
//   return [{ json: { ...body, ...findContact($('Contacts').all().map((i) => i.json), body.caller_phone, body.contact_name) } }];
//
// Matching: only the caller's own rows; case, accents and punctuation ignored;
// a full-name match beats an alias match; then a small Levenshtein fallback for
// misheard names (distance <= 1 for names up to 5 letters, <= 2 above). A query
// that looks like a phone number is returned as found with name null.

function normaliseName(s) {
  return String(s ?? '')
    .normalize('NFD').replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim();
}

function aliasesOf(contact) {
  const raw = contact.aliases;
  const list = Array.isArray(raw) ? raw : String(raw ?? '').split(',');
  return list.map(normaliseName).filter(Boolean);
}

function levenshtein(a, b) {
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    prev = cur;
  }
  return prev[b.length];
}

function looksLikePhone(query) {
  const s = String(query ?? '');
  return /^[\s\d+()\-.]+$/.test(s) && s.replace(/\D/g, '').length >= 7;
}

function findContact(contacts, ownerPhone, query) {
  if (looksLikePhone(query)) {
    const phone = toE164(query);
    return phone ? { status: 'found', contact: { name: null, phone }, match: 'phone' } : { status: 'not_found' };
  }
  const owner = toE164(ownerPhone);
  const q = normaliseName(query);
  if (!owner || !q) return { status: 'not_found' };

  const mine = (contacts || [])
    .filter((c) => toE164(c.owner_phone) === owner)
    .map((c) => ({ ...c, phone: toE164(c.phone) || c.phone }));
  const result = (list, match) => list.length === 1
    ? { status: 'found', contact: list[0], match }
    : { status: 'ambiguous', options: list.map((c) => c.name) };

  const byName = mine.filter((c) => normaliseName(c.name) === q);
  if (byName.length) return result(byName, 'name');

  const byAlias = mine.filter((c) => aliasesOf(c).includes(q));
  if (byAlias.length) return result(byAlias, 'alias');

  // Misheard names: closest name or alias within the allowed distance.
  let best = Infinity;
  let winners = [];
  for (const c of mine) {
    let d = Infinity;
    for (const term of [normaliseName(c.name), ...aliasesOf(c)]) {
      const limit = term.replace(/ /g, '').length <= 5 ? 1 : 2;
      const dist = levenshtein(q, term);
      if (dist <= limit) d = Math.min(d, dist);
    }
    if (d < best) { best = d; winners = [c]; } else if (d === best && d !== Infinity) winners.push(c);
  }
  return winners.length ? result(winners, 'fuzzy') : { status: 'not_found' };
}

if (typeof module !== 'undefined') module.exports = { findContact, normaliseName, levenshtein };

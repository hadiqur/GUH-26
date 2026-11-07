// reminder.js: checkRemindAt(iso, now), humanWhen(iso, now)
//
// Used by: workflow `set_reminder`, Code node "Check time", right after the
// Webhook node and BEFORE Respond to Webhook and the Wait node. A past time
// must never reach the Wait node (it would fire instantly), and the Wait node
// only takes us 7 days out.
//
// Paste everything above the export guard into a Code node, then add:
//   const body = $input.first().json.body; // caller_phone, text, remind_at
//   const check = checkRemindAt(body.remind_at, new Date());
//   return [{ json: { ...body, ...check, when: check.ok ? humanWhen(check.date, new Date()) : null } }];
// Then an IF node on {{ $json.ok }}: true -> append row, Respond {"status":"set","when":...},
// Wait (At specified time = {{ $json.iso }}), SMS. False -> Respond {"status":"invalid_time","reason":...}.
//
// Times without an offset ("2026-11-07T20:00:00") are read as Europe/London.

const MAX_REMINDER_MS = 7 * 24 * 60 * 60 * 1000;
const ISO_PATTERN = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d{1,3})?)?\s*(Z|[+-]\d{2}:?\d{2})?$/i;

function londonParts(date) {
  return Object.fromEntries(
    new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Europe/London', year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', weekday: 'long', hourCycle: 'h23',
    }).formatToParts(date).map((p) => [p.type, p.value])
  );
}

function londonOffsetMs(date) {
  const p = londonParts(date);
  return Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second) - Math.floor(date.getTime() / 1000) * 1000;
}

function parseRemindAt(iso) {
  if (iso instanceof Date) return isNaN(iso) ? null : iso;
  const m = ISO_PATTERN.exec(String(iso ?? '').trim());
  if (!m) return null;
  const [, y, mo, d, h, mi, s = '0', zone] = m;
  const [Y, M, D, H, MI, S] = [y, mo, d, h, mi, s].map(Number);
  const dayCheck = new Date(Date.UTC(Y, M - 1, D));
  if (M < 1 || M > 12 || dayCheck.getUTCDate() !== D || H > 23 || MI > 59 || S > 59) return null;
  const wallClock = Date.UTC(Y, M - 1, D, H, MI, S);
  if (zone) {
    if (/^z$/i.test(zone)) return new Date(wallClock);
    const sign = zone[0] === '-' ? -1 : 1;
    const digits = zone.slice(1).replace(':', '');
    return new Date(wallClock - sign * (Number(digits.slice(0, 2)) * 60 + Number(digits.slice(2))) * 60000);
  }
  // No offset: treat as London wall-clock time (GMT or BST).
  let date = new Date(wallClock - londonOffsetMs(new Date(wallClock)));
  date = new Date(wallClock - londonOffsetMs(date));
  return date;
}

function checkRemindAt(iso, now = new Date()) {
  const date = parseRemindAt(iso);
  if (!date) return { ok: false, reason: 'invalid' };
  const ahead = date.getTime() - now.getTime();
  if (ahead <= 0) return { ok: false, reason: 'in_past' };
  if (ahead > MAX_REMINDER_MS) return { ok: false, reason: 'too_far' };
  return { ok: true, date, iso: date.toISOString() };
}

function humanWhen(iso, now = new Date()) {
  const date = parseRemindAt(iso);
  if (!date) return '';
  const p = londonParts(date);
  const n = londonParts(now);
  const hour = +p.hour;
  const minute = +p.minute;
  let time;
  if (hour === 12 && minute === 0) time = 'noon';
  else if (hour === 0 && minute === 0) time = 'midnight';
  else time = `${hour % 12 || 12}${minute ? ':' + p.minute : ''}${hour < 12 ? 'am' : 'pm'}`;

  const days = Math.round((Date.UTC(+p.year, +p.month - 1, +p.day) - Date.UTC(+n.year, +n.month - 1, +n.day)) / 86400000);
  if (days === 0) return `${time} today`;
  if (days === 1) return `${time} tomorrow`;
  if (days > 1 && days < 7) return `${time} on ${p.weekday}`;
  const month = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/London', month: 'long' }).format(date);
  return `${time} on ${p.weekday} ${+p.day} ${month}`;
}

if (typeof module !== 'undefined') module.exports = { checkRemindAt, humanWhen };

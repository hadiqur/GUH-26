// build-init.js: buildInit({ callerPhone, users, contacts, now })
//
// Used by: workflow `init` (ElevenLabs "conversation initiation" webhook),
// Code node "Build init response", after two Google Sheets "Get row(s)" nodes
// named "Users" and "Contacts". Respond to Webhook: Respond With JSON,
// Response Body {{ $json }}.
//
// Paste normalise-phone.js first, then everything above the export guard
// below, into the same Code node. Then add:
//   const body = $('Webhook').first().json.body; // check the caller field name in your first run
//   return [{ json: buildInit({ callerPhone: body.caller_id, users: $('Users').all().map((i) => i.json),
//     contacts: $('Contacts').all().map((i) => i.json), now: new Date() }) }];
//
// Phone numbers from the Sheet go through toE164 too: Sheets often drops the
// leading "+" and stores 447700900123 as a number.

const NEW_USER_FIRST_MESSAGE =
  "Hi, it's Brick, an AI assistant. I don't think we've met. What's your first name?";

function formatLondonNow(date) {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Europe/London',
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).formatToParts(date).map((p) => [p.type, p.value])
  );
  return `${parts.weekday} ${parts.day} ${parts.month} ${parts.year}, ${parts.hour}:${parts.minute}, Europe/London`;
}

function buildInit({ callerPhone, users = [], contacts = [], now = new Date() } = {}) {
  const caller = toE164(callerPhone);
  const user = caller ? users.find((u) => toE164(u.phone) === caller) : undefined;
  const mine = caller ? contacts.filter((c) => toE164(c.owner_phone) === caller) : [];
  const isNew = !user;

  const response = {
    type: 'conversation_initiation_client_data',
    dynamic_variables: {
      caller_phone: caller || '',
      user_name: user ? String(user.name || '').trim() : '',
      is_new_user: isNew,
      contact_names: mine.map((c) => String(c.name).trim()).filter(Boolean).join(', '),
      now: formatLondonNow(now),
    },
  };
  // Needs "allow first-message override" in the agent's Security tab.
  if (isNew) response.conversation_config_override = { agent: { first_message: NEW_USER_FIRST_MESSAGE } };
  return response;
}

if (typeof module !== 'undefined') module.exports = { buildInit, formatLondonNow };

// build-ncco.js: buildNcco({ from, uuid, vonageNumber, transport })
//
// Used by: workflow `vonage-answer`, Code node "Build NCCO", between the
// Webhook (GET) node and Respond to Webhook (Respond With: JSON,
// Response Body: {{ $json.ncco }}).
//
// Paste normalise-phone.js first, then everything above the export guard
// below, into the same Code node ("Run Once for All Items"). Then add:
//   const q = $input.first().json.query; // Vonage: from, to, uuid
//   return [{ json: { ncco: buildNcco({ from: q.from, uuid: q.uuid, vonageNumber: q.to }) } }];
//
// Vonage silently ignores malformed NCCO, so the shape is tested exactly.
// Vonage passes custom SIP headers on as X- headers: ElevenLabs sees X-CALLER-ID.

const NO_NUMBER_MESSAGE = "Sorry, I can't see your number. Please call again without hiding it.";

function buildNcco({ from, uuid, vonageNumber, transport = 'tls' } = {}) {
  const caller = toE164(from);
  if (!caller) return [{ action: 'talk', text: NO_NUMBER_MESSAGE }];

  const digits = String(vonageNumber ?? '').replace(/\D/g, '');
  const uri = transport === 'udp'
    // UNTESTED fallback from the plan: try this if TLS on 5061 fails.
    ? `sip:+${digits}@sip.rtc.elevenlabs.io:5060;transport=udp`
    : `sip:+${digits}@sip.rtc.elevenlabs.io:5061;transport=tls`;

  return [{
    action: 'connect',
    endpoint: [{
      type: 'sip',
      uri,
      headers: { 'CALLER-ID': caller, 'CALL-ID': String(uuid ?? '') },
    }],
  }];
}

if (typeof module !== 'undefined') module.exports = { buildNcco };

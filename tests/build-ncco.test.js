const test = require('node:test');
const assert = require('node:assert/strict');
const { loadSnippets } = require('./helpers');

// Pasted together in the same Code node.
const { buildNcco } = loadSnippets('normalise-phone.js', 'build-ncco.js');

const NO_NUMBER = [{ action: 'talk', text: "Sorry, I can't see your number. Please call again without hiding it." }];

test('normal call: exactly one connect action with a TLS SIP endpoint', () => {
  const ncco = buildNcco({ from: '447700900123', uuid: 'abc-123', vonageNumber: '447700900000' });
  assert.deepEqual(ncco, [{
    action: 'connect',
    endpoint: [{
      type: 'sip',
      uri: 'sip:+447700900000@sip.rtc.elevenlabs.io:5061;transport=tls',
      headers: { 'CALLER-ID': '+447700900123', 'CALL-ID': 'abc-123' },
    }],
  }]);
});

test('Vonage number may come with or without a plus', () => {
  const [a] = buildNcco({ from: '447700900123', uuid: 'u', vonageNumber: '+44 7700 900000' });
  assert.equal(a.endpoint[0].uri, 'sip:+447700900000@sip.rtc.elevenlabs.io:5061;transport=tls');
});

test('udp transport uses port 5060', () => {
  const [a] = buildNcco({ from: '447700900123', uuid: 'u', vonageNumber: '447700900000', transport: 'udp' });
  assert.equal(a.endpoint[0].uri, 'sip:+447700900000@sip.rtc.elevenlabs.io:5060;transport=udp');
});

test('hidden or missing caller gets the talk action and no connect', () => {
  for (const from of [undefined, null, '', 'anonymous', 'Unknown', 'withheld', 'garbage']) {
    assert.deepEqual(buildNcco({ from, uuid: 'u', vonageNumber: '447700900000' }), NO_NUMBER, String(from));
  }
  assert.deepEqual(buildNcco(), NO_NUMBER);
});

test('the result is plain JSON (what Respond to Webhook sends)', () => {
  const ncco = buildNcco({ from: '447700900123', uuid: 'u', vonageNumber: '447700900000' });
  assert.deepEqual(JSON.parse(JSON.stringify(ncco)), ncco);
});

const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const match = html.match(/function downloadOptionNeedsComputer\(selectId, value\) \{[\s\S]*?\n\}/);
assert(match, 'gating helper missing');
const gate = (phone, connected) => new Function('window', 'androidApiConnected', `${match[0]}; return downloadOptionNeedsComputer;`)(phone ? {AndroidMusic: {}} : {}, connected);

const offline = gate(true, false);
assert.equal(offline('downloadFormat', 'mp3'), false);
for (const format of ['m4a', 'flac', 'wav', 'ogg']) assert.equal(offline('downloadFormat', format), true, format);
assert.equal(offline('downloadBitrate', '192'), false);
for (const rate of ['128', '256', '320']) assert.equal(offline('downloadBitrate', rate), true, rate);
assert.equal(offline('enginePriority', 'spotdl'), true);
assert.equal(offline('enginePriority', 'ytdlp'), false);

const paired = gate(true, true), web = gate(false, false);
for (const fn of [paired, web]) {
  assert.equal(fn('downloadFormat', 'flac'), false);
  assert.equal(fn('downloadBitrate', '320'), false);
  assert.equal(fn('enginePriority', 'spotdl'), false);
}
console.log('download settings gating passed');

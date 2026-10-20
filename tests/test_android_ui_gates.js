const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync(require('node:path').join(__dirname, '..', 'android', 'app', 'src', 'main', 'assets', 'index.html'), 'utf8');
const match = html.match(/function updateAndroidApiGates\(\) \{[\s\S]*?\n\}/);
assert.ok(match, 'Android API gate function exists');

function runGates(connected) {
  const controls = {
    convert: [{disabled: true}, {disabled: true}, {disabled: true}],
    tagSearchBtn: {disabled: true},
    customEngine: {disabled: true},
    enginePriority: {disabled: true, value: 'spotdl'},
    viewLrcBtn: {disabled: true},
    downloadBtn: {disabled: true, textContent: ''},
  };
  const document = {
    querySelectorAll(selector) {
      if (selector === '#lookup input, #lookup button') return [];
      if (selector === '#convert input, #convert select, #convert button') return controls.convert;
      throw new Error(`Unexpected selector: ${selector}`);
    },
  };
  const context = {
    window: {AndroidMusic: {}}, document, androidApiConnected: connected,
    $: id => controls[id], updateAndroidDownloadButtonLabel() {},
  };
  vm.runInNewContext(`${match[0]}; updateAndroidApiGates();`, context);
  return controls;
}

const offline = runGates(false);
assert.ok(offline.convert.every(control => !control.disabled), 'native conversion remains available offline');
assert.equal(offline.tagSearchBtn.disabled, true, 'online metadata search stays gated');
assert.equal(offline.customEngine.disabled, true, 'remote SpotDL option stays gated');
assert.equal(offline.enginePriority.value, 'ytdlp', 'offline download falls back to yt-dlp');

const connected = runGates(true);
assert.ok(connected.convert.every(control => !control.disabled), 'conversion remains available when connected');
assert.equal(connected.tagSearchBtn.disabled, false, 'online metadata search opens when connected');
assert.equal(connected.customEngine.disabled, false, 'SpotDL opens when connected');

// Equalizer for the music player (Web Audio, 5 bands, presets saved in settings).
// Loaded after the main page script: it uses $() from there and is used by nothing else.
// On Android the player's audio comes from a CORS https route (see AGENTS.md §3.4),
// otherwise Web Audio would silence it.

const EQ_BANDS = [[60, '60 Hz'], [250, '250 Hz'], [1000, '1 kHz'], [4000, '4 kHz'], [12000, '12 kHz']];
const EQ_PRESETS = {flat: [0, 0, 0, 0, 0], bass: [6, 4, 0, -1, 0], vocal: [-2, -1, 3, 3, 0], treble: [-1, 0, 0, 4, 6], soft: [2, 1, 0, -2, -4]};
let eqState = {enabled: false, preset: 'flat', gains: [0, 0, 0, 0, 0]};
try {
  const saved = JSON.parse(localStorage.getItem('musicdesk-eq') || 'null');
  if (saved && Array.isArray(saved.gains) && saved.gains.length === 5) {
    eqState = {enabled: !!saved.enabled, preset: String(saved.preset || 'custom'), gains: saved.gains.map(v => Math.max(-12, Math.min(12, Number(v) || 0)))};
  }
} catch (_) {}
let eqContext = null, eqFilters = [];
function eqEffectiveGains() { return eqState.enabled ? eqState.gains : [0, 0, 0, 0, 0]; }
function applyEq() {
  eqFilters.forEach((filter, index) => { filter.gain.value = eqEffectiveGains()[index]; });
}
function ensureEqGraph() {
  if (eqContext) return true;
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return false;
  try {
    eqContext = new Ctx();
    const source = eqContext.createMediaElementSource($('localAudioPlayer'));
    let node = source;
    eqFilters = EQ_BANDS.map(([freq], index) => {
      const filter = eqContext.createBiquadFilter();
      filter.type = index === 0 ? 'lowshelf' : index === EQ_BANDS.length - 1 ? 'highshelf' : 'peaking';
      filter.frequency.value = freq; filter.Q.value = 1; filter.gain.value = 0;
      node.connect(filter); node = filter; return filter;
    });
    node.connect(eqContext.destination);
    return true;
  } catch (_) { eqContext = null; eqFilters = []; return false; }
}
function saveEq() { try { localStorage.setItem('musicdesk-eq', JSON.stringify(eqState)); } catch (_) {} }
function renderEq() {
  $('eqEnabled').checked = eqState.enabled;
  $('eqPreset').value = eqState.preset in EQ_PRESETS || eqState.preset === 'custom' ? eqState.preset : 'custom';
  $('eqBands').classList.toggle('off', !eqState.enabled);
  EQ_BANDS.forEach((_, index) => {
    $(`eqBand${index}`).value = eqState.gains[index];
    $(`eqBand${index}`).disabled = !eqState.enabled;
    $(`eqOut${index}`).textContent = `${eqState.gains[index] > 0 ? '+' : ''}${eqState.gains[index]} dB`;
  });
}
function updateEq() {
  if (eqState.enabled && !ensureEqGraph()) { eqState.enabled = false; $('eqNote').textContent = '当前环境不支持均衡器。'; }
  applyEq(); saveEq(); renderEq();
}
EQ_BANDS.forEach(([, label], index) => {
  const row = document.createElement('div'); row.className = 'eq-band';
  row.innerHTML = `<span>${label}</span><input id="eqBand${index}" type="range" min="-12" max="12" step="1" value="0" aria-label="${label}"><output id="eqOut${index}">0 dB</output>`;
  $('eqBands').append(row);
  $(`eqBand${index}`).addEventListener('input', () => { eqState.gains[index] = Number($(`eqBand${index}`).value); eqState.preset = 'custom'; updateEq(); });
});
$('eqEnabled').addEventListener('change', () => { eqState.enabled = $('eqEnabled').checked; updateEq(); if (eqContext && eqContext.state === 'suspended' && !$('localAudioPlayer').paused) eqContext.resume().catch(() => {}); });
$('eqPreset').addEventListener('change', () => {
  const preset = $('eqPreset').value; eqState.preset = preset;
  if (EQ_PRESETS[preset]) eqState.gains = EQ_PRESETS[preset].slice();
  updateEq();
});
$('localAudioPlayer').addEventListener('play', () => { if (eqContext && eqContext.state === 'suspended') eqContext.resume().catch(() => {}); });
// On Android the player's tracks come from ANDROID_MEDIA_PREFIX with CORS, so Web Audio can process them there too.
const eqSupported = Boolean(window.AudioContext || window.webkitAudioContext);
if (!eqSupported) { $('eqCard').style.display = 'none'; if (eqState.enabled) { eqState.enabled = false; saveEq(); } }
else { renderEq(); if (eqState.enabled) { if (ensureEqGraph()) applyEq(); else eqState.enabled = false; renderEq(); } }

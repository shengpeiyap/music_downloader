const {readPage} = require('./lib/page_source');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const vm = require('node:vm');

// Load i18n.js in a minimal DOM-less sandbox and exercise the text lookup through a fake document.
const source = fs.readFileSync(path.join(__dirname, '..', 'i18n.js'), 'utf8');
const html = readPage(path.join(__dirname, '..', 'index.html'));
const settings = html.slice(html.indexOf('<div id="tab-settings"'), html.indexOf('id="androidMiniPlayer"'));
const connectCard = settings.slice(settings.indexOf('id="androidApiConnectCard"'), settings.indexOf('<section class="card settings-card android-setting">'));
const sentences = [...connectCard.matchAll(/<p[^>]*>([^<]+)<\/p>/g)].map(match => match[1].trim()).filter(text => /[一-鿿]/.test(text) && text !== '尚未连接');

let exposed = null;
const sandbox = {
  window: {}, localStorage: { getItem: () => 'en', setItem() {} },
  document: { addEventListener() {}, documentElement: {}, getElementById: () => null, querySelector: () => null, querySelectorAll: () => [], body: {} },
  MutationObserver: class { observe() {} },
  console,
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(source.replace(/\n\}\)\(\);\s*$/, '\n  window.__lookup = lookup;\n})();'), sandbox);
const lookup = sandbox.__lookup;
assert.equal(typeof lookup, 'function', 'lookup not exposed for the test');

for (const sentence of sentences) {
  const english = lookup(sentence, 'en');
  assert.doesNotMatch(english, /[一-鿿]/, `untranslated settings sentence: ${sentence}`);
  assert.equal(lookup(english, 'zh'), sentence, `English does not map back to Chinese: ${sentence}`);
}
const dynamic = '已连接电脑服务：http://192.168.1.20:8765。解析、歌词、下载、转换和封装任务由电脑处理，结果回传到手机。';
assert.doesNotMatch(lookup(dynamic, 'en'), /[一-鿿]/);
assert.equal(lookup(lookup(dynamic, 'en'), 'zh'), dynamic);
console.log('connection copy translations passed (' + sentences.length + ' static sentences)');

// Editor summaries are built from numbers, so they round-trip through patterns rather than the dictionary.
assert.equal(lookup('已填 2 项', 'en'), '2 filled');
assert.equal(lookup('2 filled', 'zh'), '已填 2 项');
assert.equal(lookup('12 行', 'en'), '12 lines');
console.log('editor summary translations passed');

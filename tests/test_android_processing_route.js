const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'android', 'app', 'src', 'main', 'assets', 'index.html'), 'utf8');
const match = html.match(/function shouldProcessOnAndroid\(\) \{[^}]+\}/);
assert.ok(match, 'Android processing route helper exists');

function route(androidBridge, connected) {
  const context = {window: {AndroidMusic: androidBridge}, androidApiConnected: connected};
  return vm.runInNewContext(`${match[0]}; shouldProcessOnAndroid()`, context);
}

assert.equal(route({}, false), true, 'disconnected Android uses its independent local processing');
assert.equal(route({}, true), false, 'connected Android delegates supported tasks to the desktop API');
assert.equal(route(null, false), false, 'non-Android web clients do not use Android routing');
assert.match(html, /连接成功后，在线解析、歌词、下载、转换和封装任务会交给电脑处理/);

const delegatedBranches = (html.match(/shouldProcessOnAndroid\(\)/g) || []).length;
assert.ok(delegatedBranches >= 9, 'metadata, lyrics, download, convert, parse, and package flows use the shared routing rule');

console.log('Android local/desktop processing route checks passed');

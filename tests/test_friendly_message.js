const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const match = html.match(/function friendlyMessage\(value\) \{[\s\S]*?\n\}/);
assert(match, 'friendlyMessage helper missing');
const friendlyMessage = new Function(`${match[0]}; return friendlyMessage;`)();

assert.equal(friendlyMessage(new Error('ValueError: 公开歌词库中没有找到这首歌的歌词。')), '公开歌词库中没有找到这首歌的歌词。');
assert.equal(friendlyMessage('java.lang.IllegalStateException: 无法写入文件'), '无法写入文件');
assert.equal(friendlyMessage('com.chaquo.python.PyException: ValueError: 不支持的歌词格式。'.replace('com.chaquo.python.PyException: ', '')), '不支持的歌词格式。');
assert.equal(friendlyMessage(new TypeError('Failed to fetch')), '网络连接失败，请检查网络后重试。');
assert.equal(friendlyMessage('已保存'), '已保存');
assert.equal(friendlyMessage(null), '');
console.log('friendlyMessage checks passed');

// English mode must translate the status/error sentences the page builds at runtime,
// including those shown in areas the DOM translator skips (lyrics, track lists).
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const listeners = {};
const sandbox = {
  window: {},
  document: {
    addEventListener: (name, fn) => { listeners[name] = fn; },
    getElementById: () => null, querySelector: () => null, querySelectorAll: () => [],
    documentElement: {}, body: null,
  },
  localStorage: { getItem: () => 'en', setItem: () => {} },
  MutationObserver: class { observe() {} },
  Node: {}, NodeFilter: {},
};
new Function('window', 'document', 'localStorage', 'MutationObserver', 'Node', 'NodeFilter',
  fs.readFileSync(path.join(__dirname, '..', 'i18n.js'), 'utf8'))(
  sandbox.window, sandbox.document, sandbox.localStorage, sandbox.MutationObserver, sandbox.Node, sandbox.NodeFilter);
listeners.DOMContentLoaded();
const t = sandbox.window.translateUi;
assert.equal(typeof t, 'function');

const cjk = /[一-鿿]/;
const samples = [
  '暂无内嵌歌词', '正在检索并载入 LRC 歌词…', '公开歌词库中没有找到这首歌的歌词。', '可以在“编辑”里手动粘贴歌词。',
  '音频没有内嵌歌词，正在尝试从 LRCLIB 获取…', '未知标题', '未知歌手', '未知专辑', '（空歌词行）', '待标记',
  '暂无分类内容', '播放列表为空', '电脑连接', '手机配对', '已连接', '未连接', '已保存，未验证',
  '导出成功，已保存为 a.mp3', '播放列表（12 首）', '曲库已就绪，共 5 首歌曲。', '文件夹导入完成：曲库共 5 首',
  '已添加 3 首；可继续拖入音乐', '已选择：a.mp3', '本机封装完成，已保存为 a.mp3', '转换完成，已保存为 a.wav',
  '已标记 2 / 9 句。播放到每句开始处，按空格或点击“标记当前句”。',
  '本机下载完成，已保存音频：a.mp3；已嵌入同步 LRC 歌词',
  'YouTube 暂时要求验证身份（移动网络或共享网络上常见）。请换一个 Wi‑Fi 或稍后重试，也可以连接电脑后再下载。',
  '其他匹配结果', '其他匹配结果（3）',
  '目前仅支持 Windows 桌面端，并需要 Discord 桌面版正在运行。',
  '开启后可向 Discord 分享播放状态；歌曲名称和歌手可单独控制。可见范围由 Discord 隐私设置决定，MusicDesk 不会上传音频或本地文件路径。',
  '关闭后仍会显示 MusicDesk 正在播放，但不发送歌名和歌手。专辑封面目前只保存在本机，不会上传到 Discord。',
  '歌曲信息已隐藏',
  '分享歌曲名称与歌手',
  '已连接并正在分享播放状态', '已连接；歌曲已暂停', '无法连接 Discord；请确认 Discord 桌面版已开启',
  'Discord 连接中断；正在尝试重连', '请先输入有效的 Discord 应用程序 ID。',
  '手机本机下载会把歌词直接写进 MP3；独立 .lrc 需要连接电脑。', '解析本机音频标签失败。',
];
for (const sample of samples) {
  const out = t(sample);
  assert.ok(!cjk.test(out), `still Chinese: ${sample} -> ${out}`);
}
assert.equal(t('例如：3 或 3/12'), 'e.g. 3 or 3/12');
console.log('dynamic i18n checks passed');

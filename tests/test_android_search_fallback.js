const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'android', 'app', 'src', 'main', 'assets', 'index.html'), 'utf8');
const match = html.match(/async function searchAndroidKeywordWithFallback\(query\) \{[\s\S]*?\n\}/);
assert.ok(match, 'Android keyword fallback function exists');
const downloadSourceMatch = html.match(/function androidDownloadSource\(metadata\) \{[\s\S]*?\n\}/);
assert.ok(downloadSourceMatch, 'Android download reuses the selected search result URL');

async function runFallback(musicBrainz, ytDlp) {
  const context = {
    query: 'Yorushika - Woodpecker',
    lookupWithAndroidMusicBrainz: async query => musicBrainz(query),
    lookupWithAndroidYtDlp: async query => ytDlp(query),
  };
  return vm.runInNewContext(`${match[0]}; searchAndroidKeywordWithFallback(query)`, context);
}

(async () => {
  const sourceContext = {};
  const getDownloadSource = vm.runInNewContext(`${downloadSourceMatch[0]}; androidDownloadSource`, sourceContext);
  assert.equal(getDownloadSource({url: 'https://youtu.be/selected-result', provider: 'yt-dlp', keyword_search: true}), 'https://youtu.be/selected-result');
  assert.equal(getDownloadSource({title: 'Song', artist: 'Artist', provider: 'MusicBrainz'}), 'ytsearch1:Artist Song');

  let ytDlpCalls = 0;
  const fallback = await runFallback(
    async () => { throw new Error('没有匹配'); },
    async query => { ytDlpCalls++; assert.equal(query, 'ytsearch1:Yorushika - Woodpecker'); return {title: 'Woodpecker'}; }
  );
  assert.equal(fallback.provider, 'yt-dlp');
  assert.equal(fallback.metadata.title, 'Woodpecker');
  assert.equal(ytDlpCalls, 1);

  const primary = await runFallback(
    async () => ({title: 'Woodpecker'}),
    async () => { throw new Error('should not be called'); }
  );
  assert.equal(primary.provider, 'MusicBrainz');
  assert.equal(primary.metadata.title, 'Woodpecker');

  await assert.rejects(
    runFallback(async () => { throw new Error('MB miss'); }, async () => { throw new Error('yt miss'); }),
    /yt-dlp 备用搜索也失败/
  );
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});

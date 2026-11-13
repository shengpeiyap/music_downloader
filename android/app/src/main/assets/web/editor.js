// Local conversion, metadata editing, lyric tools, and custom packaging.
// Track/disc number, genre and composer live under "More info"; fill them from a file's tags.
function fillTagExtras(tags) {
  $('tagTrackNumber').value = tags.track_num || '';
  $('tagDiscNumber').value = tags.disc_num || '';
  $('tagGenre').value = tags.genre || '';
  $('tagComposer').value = tags.composer || '';
  updateEditorSummaries();
}

function updateEditorSummaries() {
  const lyrics = $('tagLyrics').value.trim();
  $('lyricsSummary').textContent = lyrics ? `${lyrics.split(/\n/).filter(Boolean).length} 行` : '未填写';
  const trimmed = $('customTrimStart') && (Number($('customTrimStart').value) > 0 || Number($('customTrimEnd').value) < Number($('customTrimEnd').max));
  $('trimSummary').textContent = trimmed ? `${$('customTrimStartLabel').textContent} – ${$('customTrimEndLabel').textContent}` : '不裁剪';
  const filled = ['tagAlbumArtist', 'tagTrackNumber', 'tagDiscNumber', 'tagGenre', 'tagComposer'].filter(id => $(id).value.trim()).length;
  $('moreInfoSummary').textContent = filled ? `已填 ${filled} 项` : '曲目号 · 流派 · 作曲';
}
['tagLyrics', 'customTrimStart', 'customTrimEnd', 'tagAlbumArtist', 'tagTrackNumber', 'tagDiscNumber', 'tagGenre', 'tagComposer']
  .forEach(id => { $(id).addEventListener('input', updateEditorSummaries); $(id).addEventListener('change', updateEditorSummaries); });
// Programmatic fills (online search, file load) do not fire input events, so refresh while the editor is open.
setInterval(() => { if ($('tab-custom').classList.contains('active')) updateEditorSummaries(); }, 1000);
$('convert').addEventListener('submit', async e => {
  e.preventDefault();
  const file = $('audio').files[0];
  const desktopAudio = selectedDesktopConvertAudio;
  if (!file && !desktopAudio) return;
  if (file && file.size > 150 * 1024 * 1024) { $('convertStatus').textContent = '文件不能超过 150 MB。'; return; }
  $('convertBtn').disabled = true;
  $('convertStatus').textContent = androidApiConnected ? '正在发送到电脑转换…' : '正在本机转换…';
  try {
    if (shouldProcessOnAndroid() && file) {
      const immediateError = AndroidMusic.convertAudio(file.name, $('format').value);
      if (immediateError) throw Error(immediateError);
      $('convertBtn').dataset.androidPending = '1';
      $('convertStatus').textContent = '正在 Android 设备本机转换…';
      return;
    }
    const body = new FormData();
    if (file) body.append('file', file);
    if (desktopAudio) body.append('local_audio_id', desktopAudio.url.split('/').pop());
    body.append('format', $('format').value);
    const r = await requestMusicDeskApi('/api/convert', {method: 'POST', body});
    if (!r.ok) { const d = await r.json(); throw Error(d.error || '转换失败'); }
    const filename = await saveApiResponse(r, 'converted.' + $('format').value);
    $('convertStatus').textContent = `转换完成，已保存为 ${filename}`;
  } catch(err) {
    $('convertStatus').textContent = friendlyMessage(err);
  } finally {
    if (!$('convertBtn').dataset.androidPending) $('convertBtn').disabled = false;
  }
});

window.onAndroidConvertComplete = (error, filename) => {
  delete $('convertBtn').dataset.androidPending;
  $('convertBtn').disabled = false;
  $('convertStatus').textContent = friendlyMessage(error) || `转换完成，已保存为 ${filename}`;
};

let selectedDesktopConvertAudio = null;
$('audio').addEventListener('click', event => {
  if (!window.pywebview || !window.pywebview.api) return;
  event.preventDefault();
  window.pywebview.api.select_audio_files().then(records => {
    const record = Array.isArray(records) ? records[0] : null;
    if (!record) return;
    selectedDesktopConvertAudio = record;
    $('audio').value = '';
    $('audioSelection').textContent = `已选择：${record.name}`;
  }).catch(error => { $('convertStatus').textContent = error.message || '选择音乐文件失败。'; });
});
$('audio').addEventListener('change', () => {
  selectedDesktopConvertAudio = null;
  $('audioSelection').textContent = '';
});

// ===== 自定义 Tab 标签编辑与封装逻辑 =====
let selectedDesktopCustomAudio = null;
let customPreviewObjectUrl = null;
let customLrcEntries = [];
let customSelectedLyricKey = '';
let customLyricTimingMode = false;
let customLyricTimingSource = '';
let customPlainTimingLines = [];
let customPlainTimingCursor = -1;
let customPlainTimingMarks = new Map();
let customPlainTimingHistory = [];

function formatEditorTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

async function resolveAndroidCover(metadata) {
  const usable = url => new Promise(resolve => {
    if (!url) return resolve(false);
    const image = new Image();
    image.onload = () => resolve(image.naturalWidth > 0);
    image.onerror = () => resolve(false);
    image.src = url;
  });
  if (await usable(metadata.cover)) return metadata.cover;
  try {
    const query = `ytsearch1:${metadata.artist || ''} ${metadata.title || ''}`.trim();
    const fallback = await lookupWithAndroidYtDlp(query);
    if (await usable(fallback.thumbnail)) {
      metadata.cover = fallback.thumbnail;
      metadata.cover_provider = 'yt-dlp';
      return fallback.thumbnail;
    }
  } catch (_) { /* Keep the default artwork when both sources miss. */ }
  metadata.cover = '';
  return '';
}

function formatLrcTimestamp(seconds) {
  const centiseconds = Math.max(0, Math.round(seconds * 100));
  const minutes = Math.floor(centiseconds / 6000);
  const remainder = centiseconds % 6000;
  return `${String(minutes).padStart(2, '0')}:${String(Math.floor(remainder / 100)).padStart(2, '0')}.${String(remainder % 100).padStart(2, '0')}`;
}

function updateCustomTrimLabels() {
  $('customTrimStartLabel').textContent = formatEditorTime(Number($('customTrimStart').value));
  $('customTrimEndLabel').textContent = formatEditorTime(Number($('customTrimEnd').value));
}

function setCustomAudioPreview(source, isFile = false) {
  const player = $('customAudioPreview');
  player.pause();
  customLyricTimingMode = false;
  customLyricTimingSource = '';
  customPlainTimingLines = [];
  customPlainTimingCursor = -1;
  customPlainTimingMarks = new Map();
  customPlainTimingHistory = [];
  if (customPreviewObjectUrl) URL.revokeObjectURL(customPreviewObjectUrl);
  customPreviewObjectUrl = isFile && source ? URL.createObjectURL(source) : null;
  player.removeAttribute('src');
  if (!source) {
    player.load();
    $('customAudioEditor').hidden = true;
    $('trimDetails').hidden = true;
    renderCustomLyricsPreview();
    return;
  }
  player.src = customPreviewObjectUrl || source;
  player.load();
  $('customAudioEditor').hidden = false;
  $('trimDetails').hidden = false;
  $('customTrimStart').value = '0';
  $('customTrimEnd').value = '0';
  updateCustomTrimLabels();
  renderCustomLyricsPreview();
}

function initializeCustomTrimRange() {
  const duration = $('customAudioPreview').duration;
  if (!Number.isFinite(duration) || duration <= 0) return;
  for (const input of [$('customTrimStart'), $('customTrimEnd')]) {
    input.min = '0';
    input.max = String(duration);
  }
  $('customTrimStart').value = '0';
  $('customTrimEnd').value = String(duration);
  updateCustomTrimLabels();
}

function parseCustomLrc(text) {
  const entries = [];
  const lines = text.split(/\n/);
  let offset = 0;
  lines.forEach((rawLine, lineIndex) => {
    if (!rawLine) return;
    const line = rawLine.replace(/\r$/, '');
    const timePattern = /\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]/g;
    const matches = [...line.matchAll(timePattern)];
    const lyricText = line.replace(timePattern, '').trim();
    matches.forEach((match, timestampIndex) => {
      const fraction = (match[3] || '0').padEnd(3, '0').slice(0, 3);
      entries.push({
        key: `${lineIndex}:${timestampIndex}`,
        lineIndex,
        timestampIndex,
        offset: offset + match.index,
        length: match[0].length,
        seconds: Number(match[1]) * 60 + Number(match[2]) + Number(fraction) / 1000,
        text: lyricText,
      });
    });
    offset += rawLine.length + 1;
  });
  return entries;
}

function updateCustomLyricsHighlight() {
  const currentTime = $('customAudioPreview').currentTime || 0;
  let activeIndex = -1;
  customLrcEntries.forEach((entry, index) => {
    if (entry.seconds <= currentTime && (activeIndex < 0 || entry.seconds >= customLrcEntries[activeIndex].seconds)) activeIndex = index;
  });
  $('customLyricsPreview').querySelectorAll('.custom-lyric-line').forEach((button, index) => {
    button.classList.toggle('active', index === activeIndex);
    button.classList.toggle('selected', customLrcEntries[index]?.key === customSelectedLyricKey);
  });
}

function renderCustomLyricsPreview() {
  refreshLyricsSourceNote();
  const container = $('customLyricsPreview');
  const lyrics = $('tagLyrics').value;
  customLrcEntries = parseCustomLrc(lyrics);
  container.replaceChildren();
  const isPlainLyrics = Boolean(lyrics.trim()) && !customLrcEntries.length;
  if (customLyricTimingMode && customPlainTimingLines.length) {
    const progress = document.createElement('p');
    progress.className = 'custom-lyrics-empty';
    progress.textContent = `已标记 ${customPlainTimingMarks.size} / ${customPlainTimingLines.length} 句。播放到每句开始处，按空格或点击“标记当前句”。`;
    container.append(progress);
    customPlainTimingLines.forEach((line, index) => {
      const row = document.createElement('button');
      row.type = 'button';
      row.className = `custom-lyric-line${index === customPlainTimingCursor ? ' selected' : ''}`;
      row.dataset.timingLine = String(index);
      const time = document.createElement('span');
      time.className = 'custom-lyric-time';
      const markedAt = customPlainTimingMarks.get(index);
      time.textContent = Number.isFinite(markedAt) ? formatEditorTime(markedAt) : ui('待标记');
      row.append(time, document.createTextNode(line.text));
      container.append(row);
    });
  } else if (!customLrcEntries.length) {
    const message = document.createElement('p');
    message.className = 'custom-lyrics-empty ui-text';
    message.textContent = lyrics.trim()
      ? '这段歌词没有时间戳。选择音频后，可以开启逐句打点模式。'
      : '选择音频并载入 LRC 歌词后，可试听并点选歌词校时。';
    container.append(message);
  } else {
    customLrcEntries.forEach((entry, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      const previous = customLrcEntries[index - 1];
      const isTranslation = Boolean(previous) && Math.abs(previous.seconds - entry.seconds) < 0.005 && entry.text;
      button.className = `custom-lyric-line${isTranslation ? ' is-translation' : ''}`;
      button.dataset.lyricIndex = String(index);
      const time = document.createElement('span');
      time.className = 'custom-lyric-time';
      time.textContent = formatEditorTime(entry.seconds);
      button.append(time, document.createTextNode(entry.text || ui('（空歌词行）')));
      container.append(button);
    });
  }
  const hasLrc = customLrcEntries.length > 0;
  const hasAudio = Boolean($('customAudioPreview').getAttribute('src'));
  $('customLyricsSetTime').hidden = !hasLrc;
  $('customLyricsSetTime').disabled = !hasLrc || !hasAudio || !customSelectedLyricKey;
  $('customLyricsEarlier').hidden = !hasLrc;
  $('customLyricsEarlier').disabled = !hasLrc;
  $('customLyricsLater').hidden = !hasLrc;
  $('customLyricsLater').disabled = !hasLrc;
  $('customLyricsTimingMode').hidden = !isPlainLyrics || !hasAudio;
  $('customLyricsTimingMode').textContent = customLyricTimingMode ? '退出逐句打点' : '为纯文本逐句添加时间戳';
  $('customLyricsMarkCurrent').hidden = !customLyricTimingMode;
  $('customLyricsMarkCurrent').disabled = !hasAudio || customPlainTimingCursor < 0;
  $('customLyricsUndoMark').hidden = !customLyricTimingMode;
  $('customLyricsUndoMark').disabled = !customPlainTimingHistory.length;
  $('customLyricsFinishTiming').hidden = !customLyricTimingMode;
  $('customLyricsFinishTiming').disabled = !customPlainTimingLines.length || customPlainTimingMarks.size !== customPlainTimingLines.length;
  $('customLyricsMarkCurrent').textContent = customPlainTimingCursor >= 0
    ? `标记第 ${customPlainTimingLines[customPlainTimingCursor].lineNumber} 行（空格）`
    : '所有歌词行已标记';
  $('customLyricsSetTime').textContent = customSelectedLyricKey
    ? '将选中歌词设为当前播放时间'
    : '先点选一行歌词，再设置播放时间';
  updateCustomLyricsHighlight();
}

function startPlainLyricTiming() {
  if (customLyricTimingMode) {
    customLyricTimingMode = false;
    renderCustomLyricsPreview();
    return;
  }
  customLyricTimingSource = $('tagLyrics').value;
  customPlainTimingLines = customLyricTimingSource.split(/\r?\n/)
    .map((text, lineIndex) => ({text, lineIndex, lineNumber: lineIndex + 1}))
    .filter(line => line.text.trim());
  if (!customPlainTimingLines.length || !$('customAudioPreview').getAttribute('src')) return;
  customPlainTimingMarks = new Map();
  customPlainTimingHistory = [];
  customPlainTimingCursor = 0;
  customLyricTimingMode = true;
  renderCustomLyricsPreview();
}

function markCurrentPlainLyric() {
  if (!customLyricTimingMode || customPlainTimingCursor < 0) return;
  const player = $('customAudioPreview');
  if (!player.getAttribute('src') || !Number.isFinite(player.currentTime)) return;
  const lineIndex = customPlainTimingCursor;
  customPlainTimingHistory.push({lineIndex, previous: customPlainTimingMarks.get(lineIndex)});
  customPlainTimingMarks.set(lineIndex, player.currentTime);
  customPlainTimingCursor = customPlainTimingLines.findIndex((_, index) => index > lineIndex && !customPlainTimingMarks.has(index));
  if (customPlainTimingCursor < 0) customPlainTimingCursor = customPlainTimingLines.findIndex((_, index) => !customPlainTimingMarks.has(index));
  renderCustomLyricsPreview();
}

function undoPlainLyricTimingMark() {
  const previous = customPlainTimingHistory.pop();
  if (!previous) return;
  if (Number.isFinite(previous.previous)) customPlainTimingMarks.set(previous.lineIndex, previous.previous);
  else customPlainTimingMarks.delete(previous.lineIndex);
  customPlainTimingCursor = previous.lineIndex;
  renderCustomLyricsPreview();
}

function finishPlainLyricTiming() {
  if (!customPlainTimingLines.length || customPlainTimingMarks.size !== customPlainTimingLines.length) return;
  const lines = customLyricTimingSource.split(/\r?\n/);
  customPlainTimingLines.forEach((line, index) => {
    lines[line.lineIndex] = `[${formatLrcTimestamp(customPlainTimingMarks.get(index))}]${line.text}`;
  });
  $('tagLyrics').value = lines.join('\n');
  customSelectedLyricKey = '';
  customLyricTimingMode = false;
  customLyricTimingSource = '';
  customPlainTimingLines = [];
  customPlainTimingCursor = -1;
  customPlainTimingMarks = new Map();
  customPlainTimingHistory = [];
  renderCustomLyricsPreview();
}

function shiftCustomLyrics(offsetSeconds) {
  const timestampPattern = /\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]/g;
  $('tagLyrics').value = $('tagLyrics').value.replace(timestampPattern, (raw, minutes, seconds, fraction = '0') => {
    const milliseconds = Number((fraction + '00').slice(0, 3));
    const shifted = Math.max(0, Number(minutes) * 60 + Number(seconds) + milliseconds / 1000 + offsetSeconds);
    return `[${formatLrcTimestamp(shifted)}]`;
  });
  renderCustomLyricsPreview();
}

$('tagLyrics').addEventListener('input', () => {
  customSelectedLyricKey = '';
  customLyricTimingMode = false;
  customLyricTimingSource = '';
  customPlainTimingLines = [];
  customPlainTimingCursor = -1;
  customPlainTimingMarks = new Map();
  customPlainTimingHistory = [];
  renderCustomLyricsPreview();
});
$('customLyricsTimingMode').addEventListener('click', startPlainLyricTiming);
$('customLyricsMarkCurrent').addEventListener('click', markCurrentPlainLyric);
$('customLyricsUndoMark').addEventListener('click', undoPlainLyricTimingMark);
$('customLyricsFinishTiming').addEventListener('click', finishPlainLyricTiming);
$('customLyricsPreview').addEventListener('click', event => {
  const button = event.target.closest('[data-timing-line]');
  if (!button || !customLyricTimingMode) return;
  const index = Number(button.dataset.timingLine);
  const markedAt = customPlainTimingMarks.get(index);
  if (Number.isFinite(markedAt)) {
    customPlainTimingCursor = index;
    $('customAudioPreview').currentTime = markedAt;
  } else {
    customPlainTimingCursor = index;
  }
  renderCustomLyricsPreview();
});
$('customLyricsPreview').addEventListener('click', event => {
  const button = event.target.closest('[data-lyric-index]');
  if (!button) return;
  const entry = customLrcEntries[Number(button.dataset.lyricIndex)];
  if (!entry) return;
  customSelectedLyricKey = entry.key;
  const player = $('customAudioPreview');
  if (player.getAttribute('src')) {
    player.currentTime = entry.seconds;
    player.play().catch(() => {});
  }
  renderCustomLyricsPreview();
});
$('customLyricsSetTime').addEventListener('click', () => {
  const entry = customLrcEntries.find(item => item.key === customSelectedLyricKey);
  const player = $('customAudioPreview');
  if (!entry || !Number.isFinite(player.currentTime)) return;
  const replacement = `[${formatLrcTimestamp(player.currentTime)}]`;
  // An original line and its translation share one timestamp, so they move together.
  const at = customLrcEntries.indexOf(entry);
  let first = at, last = at;
  while (first > 0 && Math.abs(customLrcEntries[first - 1].seconds - entry.seconds) < 0.005) first--;
  while (last + 1 < customLrcEntries.length && Math.abs(customLrcEntries[last + 1].seconds - entry.seconds) < 0.005) last++;
  let text = $('tagLyrics').value;
  for (let i = last; i >= first; i--) {
    const target = customLrcEntries[i];
    text = text.slice(0, target.offset) + replacement + text.slice(target.offset + target.length);
  }
  $('tagLyrics').value = text;
  customSelectedLyricKey = entry.key;
  renderCustomLyricsPreview();
});
$('customLyricsEarlier').addEventListener('click', () => shiftCustomLyrics(-0.5));
$('customLyricsLater').addEventListener('click', () => shiftCustomLyrics(0.5));
$('customAudioPreview').addEventListener('loadedmetadata', initializeCustomTrimRange);
$('customAudioPreview').addEventListener('timeupdate', () => {
  const player = $('customAudioPreview');
  const end = Number($('customTrimEnd').value);
  if (!player.paused && end > 0 && player.currentTime >= end) {
    player.pause();
    player.currentTime = Number($('customTrimStart').value) || 0;
  }
  updateCustomLyricsHighlight();
});
$('customAudioPreview').addEventListener('play', () => { $('customTrimPreviewBtn').textContent = '暂停试听'; });
$('customAudioPreview').addEventListener('pause', () => { $('customTrimPreviewBtn').textContent = '试听选中片段'; });
$('customTrimStart').addEventListener('input', () => {
  const duration = $('customAudioPreview').duration || 0;
  const start = Number($('customTrimStart').value);
  if (start >= Number($('customTrimEnd').value)) $('customTrimEnd').value = String(Math.min(duration, start + 0.1));
  updateCustomTrimLabels();
});
$('customTrimEnd').addEventListener('input', () => {
  const end = Number($('customTrimEnd').value);
  if (end <= Number($('customTrimStart').value)) $('customTrimStart').value = String(Math.max(0, end - 0.1));
  updateCustomTrimLabels();
});
$('customTrimStartHere').addEventListener('click', () => {
  $('customTrimStart').value = String(Math.min($('customAudioPreview').currentTime, Number($('customTrimEnd').value) - 0.1));
  $('customTrimStart').dispatchEvent(new Event('input'));
});
$('customTrimEndHere').addEventListener('click', () => {
  $('customTrimEnd').value = String(Math.max($('customAudioPreview').currentTime, Number($('customTrimStart').value) + 0.1));
  $('customTrimEnd').dispatchEvent(new Event('input'));
});
$('customTrimPreviewBtn').addEventListener('click', () => {
  const player = $('customAudioPreview');
  if (player.paused) {
    if (player.currentTime < Number($('customTrimStart').value) || player.currentTime >= Number($('customTrimEnd').value)) {
      player.currentTime = Number($('customTrimStart').value) || 0;
    }
    player.play().catch(error => { $('customStatus').textContent = error.message || '无法试听音频。'; });
  } else {
    player.pause();
  }
});

function getKeyboardAudioPlayer() {
  const custom = $('tab-custom').classList.contains('active') ? $('customAudioPreview') : null;
  if (custom?.getAttribute('src')) return custom;
  const online = $('tab-online').classList.contains('active') ? $('audioPlayer') : null;
  if (online?.src) return online;
  if ($('tab-local').classList.contains('active') && currentTrackIdx >= 0 && localTracks[currentTrackIdx]) return $('localAudioPlayer');
  return null;
}

function toggleKeyboardAudioPlayback(player) {
  if (player === $('localAudioPlayer')) {
    $('togglePlaybackBtn').click();
  } else if (player.paused) {
    player.play().catch(() => {});
  } else {
    player.pause();
  }
}

document.addEventListener('keydown', event => {
  if ($('helpDialog').open || event.repeat || event.ctrlKey || event.altKey || event.metaKey) return;
  const target = event.target;
  if (target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) return;

  const player = getKeyboardAudioPlayer();
  if (!player) return;
  if (event.code === 'Space' || event.key.toLowerCase() === 'k') {
    event.preventDefault();
    toggleKeyboardAudioPlayback(player);
  } else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
    event.preventDefault();
    const direction = event.key === 'ArrowRight' ? 1 : -1;
    const duration = Number.isFinite(player.duration) ? player.duration : Infinity;
    player.currentTime = Math.max(0, Math.min(duration, (Number(player.currentTime) || 0) + direction * 5));
  } else if (event.key.toLowerCase() === 'm' && customLyricTimingMode && $('tab-custom').classList.contains('active')) {
    event.preventDefault();
    markCurrentPlainLyric();
  } else if (event.key.toLowerCase() === 't' && $('tab-custom').classList.contains('active') && !$('customLyricsSetTime').disabled) {
    event.preventDefault();
    $('customLyricsSetTime').click();
  }
});

$('helpBtn').addEventListener('click', () => $('helpDialog').showModal());
$('closeHelpBtn').addEventListener('click', () => $('helpDialog').close());
$('helpDialog').addEventListener('click', event => {
  if (event.target === $('helpDialog')) $('helpDialog').close();
});

$('customAudioInput').addEventListener('click', event => {
  if (!window.pywebview || !window.pywebview.api) return;
  event.preventDefault();
  window.pywebview.api.select_audio_files().then(async records => {
    const record = Array.isArray(records) ? records[0] : null;
    if (!record) return;
    selectedDesktopCustomAudio = record;
    $('customAudioInput').value = '';
    $('customAudioSelection').textContent = `已选择：${record.name}`;
    setCustomAudioPreview(record.url);
    $('customEngineRow').style.display = 'none';
    $('customCoverPreview').dataset.embeddedCover = '';
    $('customStatus').textContent = '正在读取并解析音频标签元数据...';
    const response = await requestMusicDeskApi('/api/parse_local_tag', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({local_audio_id: record.url.split('/').pop()})
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.error || '解析元数据失败');
    $('tagTitle').value = data.title || '';
    $('tagArtist').value = data.artist || '';
    $('tagAlbum').value = data.album || '';
    $('tagAlbumArtist').value = data.albumartist || '';
    fillTagExtras(data);
    $('tagYear').value = data.year || '';
    $('tagLyrics').value = data.lyrics || '';
    showEmbeddedLyricsSource(data);
    customSelectedLyricKey = '';
    renderCustomLyricsPreview();
    $('tagSearch').value = data.artist && data.artist !== '未知艺人' ? `${data.artist} - ${data.title}` : data.title || '';
    $('customCoverPreview').dataset.embeddedCover = data.cover || '';
    $('customCoverPreview').src = data.cover || DEFAULT_COVER;
    $('customStatus').textContent = '已读取内部资料。您可以更改上述内容后点击导出。';
  }).catch(error => { $('customStatus').textContent = error.message || '选择或读取音乐文件失败。'; });
});
$('customAudioInput').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  selectedDesktopCustomAudio = null;
  $('customAudioSelection').textContent = '';
  $('customEngineRow').style.display = file ? 'none' : 'block';
  if (!file) {
    setCustomAudioPreview('');
    return;
  }
  if (shouldProcessOnAndroid()) {
    const ext = (file.name.match(/\.([^.]+)$/) || [])[1];
    if (ext && Array.from($('tagFormat').options).some(option => option.value.toLowerCase() === ext.toLowerCase())) {
      $('tagFormat').value = ext.toLowerCase();
    }
  }
  setCustomAudioPreview(file, true);
  $('customCoverPreview').dataset.embeddedCover = '';

  $('customStatus').textContent = androidApiConnected ? '正在发送音频到电脑读取标签…' : '正在读取并解析音频标签元数据...';
  if (shouldProcessOnAndroid()) {
    const immediateError = AndroidMusic.readLocalTags(file.name);
    if (immediateError) $('customStatus').textContent = immediateError;
    return;
  }
  const formData = new FormData();
  formData.append('file', file);

  try {
    const r = await requestMusicDeskApi('/api/parse_local_tag', {
      method: 'POST',
      body: formData
    });
    const d = await r.json();
    if (!r.ok) throw Error(d.error || '解析元数据失败');

    $('tagTitle').value = d.title || '';
    $('tagArtist').value = d.artist || '';
    $('tagAlbum').value = d.album || '';
    $('tagAlbumArtist').value = d.albumartist || '';
    fillTagExtras(d);
    $('tagYear').value = d.year || '';
    $('tagLyrics').value = d.lyrics || '';
    customSelectedLyricKey = '';
    renderCustomLyricsPreview();
    $('tagSearch').value = d.artist && d.artist !== '未知艺人' ? `${d.artist} - ${d.title}` : d.title || '';
    $('customCoverPreview').dataset.embeddedCover = d.cover || '';

    if (d.cover) {
      $('customCoverPreview').src = d.cover;
    } else {
      $('customCoverPreview').src = DEFAULT_COVER;
    }

    $('customStatus').textContent = '已读取内部资料。您可以更改上述内容后点击导出。';
  } catch (err) {
    $('customStatus').textContent = friendlyMessage(err);
  }
});

$('filenameAppendEnabled').addEventListener('change', (e) => {
  $('filenameAppend').disabled = !e.target.checked;
});

$('tagSearchBtn').addEventListener('click', async () => {
  const query = $('tagSearch').value.trim();
  if (!query) {
    $('customStatus').textContent = '请输入“作者 - 标题”或歌曲标题。';
    return;
  }

  $('tagSearchBtn').disabled = true;
  $('customStatus').textContent = '正在搜索公开曲目信息…';
  try {
    const r = await requestMusicDeskApi('/api/search_metadata', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({query})
    });
    const d = await r.json();
    if (!r.ok) throw Error(d.error || '搜索曲目信息失败');

    $('tagTitle').value = d.title || '';
    $('tagArtist').value = d.artist || '';
    $('tagAlbum').value = d.album || '';
    $('tagAlbumArtist').value = d.albumartist || d.artist || '';
    $('tagYear').value = d.year || '';
    let lyrics = d.lyrics || '';
    if (!lyrics && shouldProcessOnAndroid()) {
      try {
        const lyricResult = await lookupLyricsOnAndroid(d.title || '', d.artist || '');
        lyrics = lyricResult.lyrics || '';
      } catch (_) {}
    } else if (!lyrics && window.AndroidMusic && androidApiConnected) {
      try {
        const response = await requestMusicDeskApi('/api/lyrics_text', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({title: d.title || '', artist: d.artist || ''})
        });
        const lyricResult = await response.json();
        if (response.ok) lyrics = lyricResult.lyrics || '';
      } catch (_) {}
    }
    $('tagLyrics').value = lyrics;
    customSelectedLyricKey = '';
    renderCustomLyricsPreview();
    $('customCoverPreview').dataset.embeddedCover = d.cover || '';
    $('customCoverPreview').src = d.cover || DEFAULT_COVER;
    $('customStatus').textContent = '已根据关键词补全信息，请检查后导出。';
  } catch (err) {
    $('customStatus').textContent = friendlyMessage(err);
  } finally {
    $('tagSearchBtn').disabled = false;
  }
});

$('customCoverInput').addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (file) {
    const url = URL.createObjectURL(file);
    $('customCoverPreview').src = url;
    $('customCoverPreview').dataset.embeddedCover = '';
  }
});

$('customTagForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const audioFile = $('customAudioInput').files[0];
  const desktopAudio = selectedDesktopCustomAudio;
  if (!audioFile && !desktopAudio && !$('tagTitle').value.trim()) {
    $('customStatus').textContent = '请先选择音频，或搜索并填写曲名后直接封装。';
    return;
  }

  $('saveTagBtn').disabled = true;
  $('customStatus').textContent = androidApiConnected
    ? '正在发送到电脑封装并回传文件，请稍候…'
    : audioFile || desktopAudio ? '正在打包并写回标签元数据，请稍候...' : '正在搜索音源并封装标签，请稍候...';

  const formData = new FormData();
  if (audioFile) formData.append('audio_file', audioFile);
  if (desktopAudio) formData.append('local_audio_id', desktopAudio.url.split('/').pop());

  const coverFile = $('customCoverInput').files[0];
  if (coverFile) {
    formData.append('cover_file', coverFile);
  }

  formData.append('title', $('tagTitle').value);
  formData.append('artist', $('tagArtist').value);
  formData.append('album', $('tagAlbum').value);
  formData.append('albumartist', $('tagAlbumArtist').value);
  formData.append('year', $('tagYear').value);
  formData.append('lyrics', $('tagLyrics').value);
  formData.append('lyrics_format', $('tagLyricsFormat').value);
  formData.append('track_num', $('tagTrackNumber').value);
  formData.append('disc_num', $('tagDiscNumber').value);
  formData.append('genre', $('tagGenre').value);
  formData.append('composer', $('tagComposer').value);
  formData.append('format', $('tagFormat').value);
  formData.append('preferred_engine', $('customEngine').value);
  formData.append('filename_append_enabled', $('filenameAppendEnabled').checked ? '1' : '0');
  formData.append('filename_append', $('filenameAppend').value);
  formData.append('trim_start', desktopAudio || audioFile ? $('customTrimStart').value : '0');
  formData.append('trim_end', desktopAudio || audioFile ? $('customTrimEnd').value : '0');

  try {
    const embeddedCover = $('customCoverPreview').dataset.embeddedCover;
    if (shouldProcessOnAndroid() && audioFile) {
      const trimStart = Number($('customTrimStart').value || 0);
      const duration = $('customAudioPreview').duration || 0;
      const rangeEnd = Number($('customTrimEnd').value || 0);
      const trimEnd = duration > 0 && rangeEnd < duration - 0.1 ? rangeEnd : 0;
      const coverDataUrl = !coverFile && embeddedCover.startsWith('data:') ? embeddedCover : '';
      const metadata = {
        title: $('tagTitle').value.trim(), artist: $('tagArtist').value.trim(),
        album: $('tagAlbum').value.trim(), album_artist: $('tagAlbumArtist').value.trim(),
        release_year: $('tagYear').value.trim(), lyrics: $('tagLyrics').value,
        lyrics_format: $('tagLyricsFormat').value,
        track_num: $('tagTrackNumber').value.trim(), disc_num: $('tagDiscNumber').value.trim(),
        genre: $('tagGenre').value.trim(), composer: $('tagComposer').value.trim()
      };
      let outputName = `${metadata.artist ? metadata.artist + ' - ' : ''}${metadata.title || audioFile.name.replace(/\.[^.]+$/, '')}`;
      if ($('filenameAppendEnabled').checked && $('filenameAppend').value.trim()) outputName += ` ${$('filenameAppend').value.trim()}`;
      outputName += `.${$('tagFormat').value}`;
      const immediateError = AndroidMusic.packageAudio(
        audioFile.name, coverFile ? coverFile.name : '', coverDataUrl,
        JSON.stringify(metadata), outputName, $('tagFormat').value, trimStart, trimEnd
      );
      if (immediateError) throw Error(immediateError);
      $('saveTagBtn').dataset.androidPending = '1';
      $('customStatus').textContent = '正在本机写入音频标签…';
      return;
    }
    if (!coverFile && embeddedCover) {
      const coverBlob = await fetch(embeddedCover).then(response => response.blob());
      formData.append('cover_file', coverBlob, 'embedded-cover');
    }
    const r = await requestMusicDeskApi('/api/package_custom_tag', {
      method: 'POST',
      body: formData
    });

    if (!r.ok) {
      const d = await r.json();
      throw Error(d.error || '定制封装失败');
    }

    const filename = await saveApiResponse(r, 'custom_audio.mp3');
    $('customStatus').textContent = `导出成功，已保存为 ${filename}`;
  } catch (err) {
    $('customStatus').textContent = friendlyMessage(err);
  } finally {
    if (!$('saveTagBtn').dataset.androidPending) $('saveTagBtn').disabled = false;
  }
});

window.onAndroidCustomPackageComplete = (error, filename) => {
  delete $('saveTagBtn').dataset.androidPending;
  $('saveTagBtn').disabled = false;
  $('customStatus').textContent = friendlyMessage(error) || `本机封装完成，已保存为 ${filename}`;
};

// Tells the person which tag fields of the chosen file hold lyrics (e.g. "ID3 USLT + ID3 SYLT")
// and whether those lyrics carry LRC timestamps.
function showEmbeddedLyricsSource(data) {
  const fields = Array.isArray(data && data.lyrics_fields) ? data.lyrics_fields.map(String) : [];
  const lyrics = String(data && data.lyrics || '');
  let text = '';
  if (fields.length) {
    const timed = /^\s*\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\]/m.test(lyrics);
    text = `内嵌歌词：${fields.join(' + ')} · ${timed ? '带时间戳（同步 LRC）' : '纯文本（无时间戳）'}`;
  } else if (!lyrics.trim()) {
    text = '音频没有内嵌歌词';
  }
  setLyricsSourceNote(text);
}

// The note describes the file as read. Once the lyrics box no longer matches it, say that the
// file still holds the old lyrics until it is saved.
let lyricsSourceNote = {base: '', loaded: ''};
function setLyricsSourceNote(base) {
  lyricsSourceNote = {base, loaded: $('tagLyrics').value};
  refreshLyricsSourceNote();
}
function refreshLyricsSourceNote() {
  const {base, loaded} = lyricsSourceNote;
  const edited = $('tagLyrics').value !== loaded;
  let text = base;
  if (edited && base.startsWith('内嵌歌词：')) text = `${base}（已修改，保存后写入）`;
  else if (edited && base === '音频没有内嵌歌词' && $('tagLyrics').value.trim()) text = '音频原本没有内嵌歌词，保存后写入';
  $('tagLyricsSource').textContent = text;
}

window.onAndroidLocalTagsComplete = (error, tagsJson, artwork, audioName) => {
  if (error) { $('customStatus').textContent = friendlyMessage(error); return; }
  const selectedFile = $('customAudioInput').files[0];
  if (audioName && selectedFile && selectedFile.name !== audioName) return;
  try {
    const data = JSON.parse(tagsJson || '{}');
    $('tagTitle').value = data.title || '';
    $('tagArtist').value = data.artist || '';
    $('tagAlbum').value = data.album || '';
    $('tagAlbumArtist').value = data.albumartist || '';
    fillTagExtras(data);
    $('tagYear').value = (data.year || '').slice(0, 4);
    $('tagLyrics').value = data.lyrics || '';
    showEmbeddedLyricsSource(data);
    if (artwork) {
      $('customCoverPreview').src = artwork;
      $('customCoverPreview').dataset.embeddedCover = artwork;
    }
    customSelectedLyricKey = '';
    renderCustomLyricsPreview();
    $('tagSearch').value = data.artist && data.title ? `${data.artist} - ${data.title}` : data.title || '';
    $('customStatus').textContent = '已从所选音频读取标签。可以修改后本机封装。';
    if (!data.lyrics && data.title && data.title !== '未知曲目') {
      $('customStatus').textContent = '音频没有内嵌歌词，正在尝试从 LRCLIB 获取…';
      lookupLyricsOnAndroid(data.title, data.artist || '').then(result => {
        const currentFile = $('customAudioInput').files[0];
        if (audioName && (!currentFile || currentFile.name !== audioName)) return;
        const lyrics = result.lyrics || '';
        if (!lyrics) throw new Error('公开歌词库中没有找到这首歌的歌词。');
        $('tagLyrics').value = lyrics;
        setLyricsSourceNote('歌词来自 LRCLIB，保存后才会写入文件');
        renderCustomLyricsPreview();
        $('customStatus').textContent = result.synced_lyrics
          ? '已从 LRCLIB 载入同步 LRC；点击“保存并打包导出文件”即可内嵌。'
          : '已载入纯文本歌词（无时间戳）；点击“保存并打包导出文件”即可内嵌。';
      }).catch(lyricError => {
        const currentFile = $('customAudioInput').files[0];
        if (audioName && (!currentFile || currentFile.name !== audioName)) return;
        $('customStatus').textContent = `已读取音频标签，但未能补全歌词：${friendlyMessage(lyricError)}`;
      });
    }
  } catch (_) { $('customStatus').textContent = '解析本机音频标签失败。'; }
};

// ===== 本地离线播放器 Tab 逻辑 =====

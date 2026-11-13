// Local library, playback, queue, lyrics display, and platform restoration.
const DEFAULT_COVER = 'default_song_img.png';
document.addEventListener('error', event => {
  const image = event.target;
  if (image instanceof HTMLImageElement && !image.src.endsWith(DEFAULT_COVER)) image.src = DEFAULT_COVER;
}, true);
let currentMetadata = null;
let parsedLyrics = [];
let localTracks = []; // [{file, title, artist, album, cover, lrc}, ...]
let currentTrackIdx = -1;
let playbackQueue = [];
let playbackOrder = [];
let displayedTrackIndices = [];
let parsedLocalLyrics = [];
const PLAYBACK_MODES = ['sequential', 'repeat-one', 'repeat-all', 'shuffle'];
const PLAYBACK_MODE_LABELS = {sequential: '顺序播放', 'repeat-one': '单曲循环', 'repeat-all': '列表循环', shuffle: '随机播放'};
const PLAYBACK_MODE_ICONS = {
  sequential: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h2v3H4zM9 7.5h11M4 11h2v3H4zM9 12.5h11M4 16h2v3H4zM9 17.5h11"/></svg>',
  'repeat-one': '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 2l4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4m14-1v2a3 3 0 0 1-3 3H3"/><text x="12" y="15" text-anchor="middle" font-size="8" font-weight="700" fill="currentColor" stroke="none">1</text></svg>',
  'repeat-all': '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 2l4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4m14-1v2a3 3 0 0 1-3 3H3"/></svg>',
  shuffle: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 3h5v5m0-5-6 6M3 7h2c5 0 7 10 12 10h4m-5-4 5 4-5 4M3 17h2c1.7 0 3-1.5 4.2-3.2"/></svg>'
};
let playbackMode = 'sequential';
let libraryCategory = 'songs';
let libraryGroup = '';
let favoriteTrackKeys = new Set();
try { favoriteTrackKeys = new Set(JSON.parse(localStorage.getItem('musicdesk-favorites') || '[]')); } catch (_) {}
let queueCloseTimer = null;
let queueDragStartY = null;
let queueDragLastTime = 0;
let queueDragVelocity = 0;
let queueTouchStartY = null;
let queueTouchDragging = false;
let androidNoticeTimer = null;
let androidView = 'library';
let androidContentView = 'song';
let pendingSavedPlayback = null;
let restoringSavedPlayback = false;
let lastSavedPlaybackBucket = -1;
let lastMediaSessionUpdate = 0;
const browserFileSources = new WeakMap();
const FILE_HANDLE_DB = 'musicdesk-file-access';
try { pendingSavedPlayback = JSON.parse(localStorage.getItem('musicdesk-playback-state') || 'null'); } catch (_) {}

function openFileHandleDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(FILE_HANDLE_DB, 1);
    request.onupgradeneeded = () => request.result.createObjectStore('handles', {keyPath: 'key'});
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function saveFileHandle(key, handle) {
  const db = await openFileHandleDb();
  await new Promise((resolve, reject) => {
    const request = db.transaction('handles', 'readwrite').objectStore('handles').put({key, handle});
    request.onsuccess = resolve;
    request.onerror = () => reject(request.error);
  });
  db.close();
}

async function clearIndividualFileHandles() {
  const db = await openFileHandleDb();
  await new Promise((resolve, reject) => {
    const store = db.transaction('handles', 'readwrite').objectStore('handles');
    const request = store.getAllKeys();
    request.onsuccess = () => {
      request.result.filter(key => String(key).startsWith('file:')).forEach(key => store.delete(key));
      resolve();
    };
    request.onerror = () => reject(request.error);
  });
  db.close();
}

async function loadFileHandles() {
  const db = await openFileHandleDb();
  const records = await new Promise((resolve, reject) => {
    const request = db.transaction('handles', 'readonly').objectStore('handles').getAll();
    request.onsuccess = () => resolve(request.result || []);
    request.onerror = () => reject(request.error);
  });
  db.close();
  return records;
}

async function hasReadPermission(handle) {
  if (!handle || !handle.queryPermission) return false;
  try { return await handle.queryPermission({mode: 'read'}) === 'granted'; } catch (_) { return false; }
}

async function collectDirectoryAudio(handle, prefix = '') {
  const files = [];
  for await (const [name, entry] of handle.entries()) {
    const relativePath = prefix ? `${prefix}/${name}` : name;
    if (entry.kind === 'directory') files.push(...await collectDirectoryAudio(entry, relativePath));
    else if (AUDIO_EXTENSIONS.test(name)) {
      const file = await entry.getFile();
      browserFileSources.set(file, {key: `directory:${relativePath}`, handle: entry, folderPath: relativePath.split('/').slice(0, -1).join('/')});
      files.push(file);
    }
  }
  return files;
}

function persistAndroidPlayback(force = false) {
  if (restoringSavedPlayback) return;
  const player = $('localAudioPlayer');
  const track = localTracks[currentTrackIdx] || null;
  const seconds = track && Number.isFinite(player.currentTime) ? player.currentTime : 0;
  const bucket = Math.floor(seconds / 3);
  if (!force && bucket === lastSavedPlaybackBucket) return;
  lastSavedPlaybackBucket = bucket;
  const state = {
    uri: track ? localTrackKey(track) : '', position: seconds, wasPlaying: !!track && !player.paused,
    queue: playbackQueue.map(localTrackKey),
    desktopFiles: localTracks.map(item => item.desktopPath).filter(Boolean),
    view: androidView, contentView: androidContentView, category: libraryCategory,
    group: libraryGroup, search: $('searchLocal').value, mode: playbackMode
  };
  try { localStorage.setItem('musicdesk-playback-state', JSON.stringify(state)); } catch (_) {}
  if (window.pywebview && window.pywebview.api && window.pywebview.api.save_playback_state) {
    window.pywebview.api.save_playback_state(JSON.stringify(state)).catch(() => {});
  }
}

function tryRestoreSavedPlayback() {
  const state = pendingSavedPlayback;
  if (!state || restoringSavedPlayback) return;
  const idx = state.uri ? localTracks.findIndex(track => localTrackKey(track) === state.uri) : -1;
  const savedQueue = Array.isArray(state.queue) ? state.queue : [];
  const restoredQueue = savedQueue.map(key => localTracks.find(track => localTrackKey(track) === key)).filter(Boolean);
  restoringSavedPlayback = true;
  libraryCategory = ['songs', 'artists', 'albums', 'folders', 'favorites'].includes(state.category) ? state.category : 'songs';
  libraryGroup = state.group || '';
  $('searchLocal').value = state.search || '';
  playbackMode = PLAYBACK_MODES.includes(state.mode) ? state.mode : 'sequential';
  renderLocalPlaylist($('searchLocal').value);
  playbackQueue = Array.isArray(state.queue)
    ? restoredQueue
    : displayedTrackIndices.map(index => localTracks[index]).filter(Boolean);
  if (idx >= 0 && !playbackQueue.includes(localTracks[idx])) playbackQueue.unshift(localTracks[idx]);
  updatePlaybackOrder(idx >= 0 ? localTracks[idx] : playbackQueue[0]);
  pendingSavedPlayback = null;
  if (idx >= 0) {
    const saved = {uri: state.uri, position: Number(state.position) || 0, wasPlaying: !!state.wasPlaying};
    if (localTracks[idx].contentUri && window.AndroidMusic) window.pendingAudioResume = saved;
    else window.pendingLocalAudioResume = saved;
    playLocalTrack(idx, true);
  } else {
    renderQueue();
    syncPlayerControls();
  }
  setPlayerContentView(state.contentView === 'lyrics' ? 'lyrics' : 'song');
  if (window.AndroidMusic) showAndroidLocalTab(state.view === 'player' ? 'player' : 'library');
  restoringSavedPlayback = false;
  lastSavedPlaybackBucket = -1;
}

window.addEventListener('pagehide', () => persistAndroidPlayback(true));

// Tab 切换逻辑
function switchTab(tabName) {
  if (!['online', 'custom', 'local', 'settings'].includes(tabName)) tabName = 'online';
  document.querySelectorAll('.tab-btn').forEach(btn => {
    const on = btn.dataset.tab === tabName;
    btn.classList.toggle('active', on);
    if (on) btn.setAttribute('aria-current', 'page'); else btn.removeAttribute('aria-current');
  });
  document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
  $(`tab-${tabName}`).classList.add('active');
  if (tabName === 'settings' && window.AndroidMusic) refreshAndroidSettings();
  if (typeof updateMiniPlayerVisibility === 'function') updateMiniPlayerVisibility();
}

// LRC 工具
function parseLRC(lrcText) {
  if(!lrcText) return [];
  const lines = lrcText.split('\n');
  const result = [];
  lines.forEach(line => {
    const lineTags = [...line.matchAll(/\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]/g)];
    const content = line.slice(lineTags.length ? lineTags[lineTags.length - 1].index + lineTags[lineTags.length - 1][0].length : 0);
    const wordTags = [...content.matchAll(/<(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?>/g)];
    const toSeconds = match => Number(match[1]) * 60 + Number(match[2]) + Number((match[3] || '0').padEnd(3, '0').slice(0, 3)) / 1000;
    if (wordTags.length) wordTags.forEach((tag, index) => {
      const end = index + 1 < wordTags.length ? wordTags[index + 1].index : content.length;
      const text = content.slice(tag.index + tag[0].length, end).trim();
      if (text) result.push({time:toSeconds(tag), text});
    });
    else {
      const text = content.replace(/\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\]/g, '').trim();
      if (text) lineTags.forEach(tag => result.push({time:toSeconds(tag), text}));
    }
  });
  return result.sort((a, b) => a.time - b.time);
}

function renderPlainLyrics(container, lyricText, emptyMessage) {
  const lines = String(lyricText || '').replace(/^\uFEFF/, '').split(/\r?\n/);
  const visibleLines = lines.filter(line => line.trim());
  if (!visibleLines.length) {
    container.innerHTML = `<div class="ui-text" style="color:var(--muted);text-align:center;padding-top:50px">${escapeHTML(ui(emptyMessage))}</div>`;
    return;
  }
  container.innerHTML = visibleLines.map(line =>
    `<div class="plain-lyric-line">${escapeHTML(line)}</div>`
  ).join('');
}

// ===== 在线 Tab 逻辑 =====
let bilingualLyrics = true;
try { bilingualLyrics = localStorage.getItem('musicdesk-bilingual-lyrics') !== '0'; } catch (_) {}
let lastOnlineLrcText = '', lastLocalLrcText = '';
// Lines sharing one timestamp are original + translation. Keep the first as the lyric, the rest as translation.
function groupLyricTranslations(items) {
  const grouped = [];
  items.forEach(item => {
    const last = grouped[grouped.length - 1];
    if (last && Math.abs(last.time - item.time) < 0.005) last.tr.push(item.text);
    else grouped.push({time: item.time, text: item.text, tr: []});
  });
  return grouped;
}
function lyricLineHtml(item, id) {
  const tr = bilingualLyrics && item.tr.length ? `<span class="tr">${item.tr.map(escapeHTML).join('<br>')}</span>` : '';
  return `<div class="lrc-line" data-time="${item.time}" id="${id}">${escapeHTML(item.text)}${tr}</div>`;
}
function mergeTranslationIntoLyrics(lyrics, translation) {
  const translations = translation.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  const out = [];
  let used = 0, timed = 0;
  String(lyrics || '').split(/\r?\n/).forEach(line => {
    out.push(line);
    const tags = line.match(/^(?:\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\])+/);
    const body = tags ? line.slice(tags[0].length).trim() : '';
    if (!tags || !body || /^\[[a-z]+:/i.test(line)) return;
    timed++;
    if (used < translations.length) out.push(tags[0] + translations[used++]);
  });
  return {text: out.join('\n'), timed, translations: translations.length, used};
}
function renderLyricsView(lrcText) {
  lastOnlineLrcText = lrcText;
  parsedLyrics = groupLyricTranslations(parseLRC(lrcText));
  const container = $('lrcContainer');
  if (parsedLyrics.length === 0) {
    renderPlainLyrics(container, lrcText, '未检索到歌词');
    return;
  }
  container.innerHTML = parsedLyrics.map((item, idx) => lyricLineHtml(item, `lrc-${idx}`)).join('');

  container.querySelectorAll('.lrc-line').forEach((el) => {
    el.addEventListener('click', () => {
      const time = parseFloat(el.getAttribute('data-time'));
      const player = $('audioPlayer');
      if (player.src) { player.currentTime = time; player.play(); }
    });
  });
}

$('audioPlayer').addEventListener('timeupdate', () => {
  const currentTime = $('audioPlayer').currentTime;
  if (!parsedLyrics.length) return;
  let activeIndex = -1;
  for (let i = 0; i < parsedLyrics.length; i++) {
    if (currentTime >= parsedLyrics[i].time) activeIndex = i; else break;
  }
  if (activeIndex !== -1) {
    document.querySelectorAll('#lyricsViewer .lrc-line').forEach(el => el.classList.remove('active'));
    const activeEl = $(`lrc-${activeIndex}`);
    if (activeEl) {
      activeEl.classList.add('active');
      const viewer = $('lyricsViewer');
      viewer.scrollTop = activeEl.offsetTop - viewer.offsetTop - 80;
    }
  }
});

// ---- Playlist batch download (computer web page only) ----
const AUDIO_EXTENSIONS = /\.(mp3|m4a|flac|wav|ogg)$/i;
function setAddMenu(open) {
  $('addMusicMenu').hidden = !open;
  $('addMusicBtn').setAttribute('aria-expanded', String(open));
}
$('addMusicBtn').addEventListener('click', event => { event.stopPropagation(); setAddMenu($('addMusicMenu').hidden); });
$('addMusicMenu').addEventListener('click', () => setAddMenu(false));
document.addEventListener('click', event => { if (!event.target.closest('.add-menu')) setAddMenu(false); });
document.addEventListener('keydown', event => { if (event.key === 'Escape' && !$('addMusicMenu').hidden) { setAddMenu(false); $('addMusicBtn').focus(); } });
$('selectDirBtn').addEventListener('click', () => {
  if (window.AndroidMusic) AndroidMusic.pickFolder();
  else if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.select_music_folder().then(records => addDesktopAudioRecords(records, true))
      .catch(error => { $('playlistDropZone').textContent = error.message || '打开文件夹选择窗口失败。'; });
  }
  else if (window.showDirectoryPicker) chooseBrowserDirectory();
  else $('dirInput').click();
});
$('selectFilesBtn').addEventListener('click', () => {
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.select_audio_files().then(records => addDesktopAudioRecords(records, false))
      .catch(error => { $('playlistDropZone').textContent = error.message || '打开音乐文件选择窗口失败。'; });
  } else if (window.showOpenFilePicker) chooseBrowserAudioFiles();
  else $('audioFilesInput').click();
});
$('audioFilesInput').addEventListener('change', event => {
  addLocalAudioFiles(Array.from(event.target.files), false);
  event.target.value = '';
});

function setupDropZone(zone, onDrop) {
  ['dragenter', 'dragover'].forEach(type => zone.addEventListener(type, event => {
    event.preventDefault();
    zone.classList.add('drag-over');
  }));
  ['dragleave', 'drop'].forEach(type => zone.addEventListener(type, event => {
    event.preventDefault();
    zone.classList.remove('drag-over');
  }));
  zone.addEventListener('drop', async event => onDrop(await getDroppedFiles(event.dataTransfer)));
}

async function chooseBrowserDirectory() {
  try {
    const handle = await window.showDirectoryPicker({mode: 'read'});
    await clearIndividualFileHandles();
    await saveFileHandle('library-directory', handle);
    const files = await collectDirectoryAudio(handle);
    addLocalAudioFiles(files, true);
  } catch (error) {
    if (error && error.name !== 'AbortError') $('playlistDropZone').textContent = '无法读取所选文件夹，请检查浏览器文件访问权限。';
  }
}

async function chooseBrowserAudioFiles() {
  try {
    const handles = await window.showOpenFilePicker({
      multiple: true,
      types: [{description: '音乐文件', accept: {'audio/*': ['.mp3', '.m4a', '.flac', '.wav', '.ogg']}}]
    });
    const files = [];
    for (const handle of handles) {
      const file = await handle.getFile();
      const key = `file:${crypto.randomUUID()}`;
      browserFileSources.set(file, {key, handle, folderPath: '已选歌曲'});
      await saveFileHandle(key, handle);
      files.push(file);
    }
    addLocalAudioFiles(files, false);
  } catch (error) {
    if (error && error.name !== 'AbortError') $('playlistDropZone').textContent = '无法读取所选音乐文件，请重新授权后重试。';
  }
}

async function getDroppedFiles(dataTransfer) {
  const entries = Array.from(dataTransfer.items || [])
    .map(item => item.webkitGetAsEntry && item.webkitGetAsEntry()).filter(Boolean);
  if (!entries.length) return Array.from(dataTransfer.files || []);
  const files = [];
  async function walk(entry) {
    if (entry.isFile) {
      files.push(await new Promise(resolve => entry.file(resolve, () => resolve(null))));
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      let batch;
      do {
        batch = await new Promise(resolve => reader.readEntries(resolve, () => resolve([])));
        await Promise.all(batch.map(walk));
      } while (batch.length);
    }
  }
  await Promise.all(entries.map(walk));
  return files.filter(Boolean);
}

function setFileInputFiles(input, files) {
  const transfer = new DataTransfer();
  Array.from(files).forEach(file => transfer.items.add(file));
  input.files = transfer.files;
  input.dispatchEvent(new Event('change', {bubbles: true}));
}

setupDropZone($('customAudioDrop'), files => {
  const file = files.find(item => AUDIO_EXTENSIONS.test(item.name));
  if (!file) {
    $('customStatus').textContent = '请拖入 MP3、M4A、FLAC、WAV 或 OGG 音频文件。';
    return;
  }
  if (files.filter(item => AUDIO_EXTENSIONS.test(item.name)).length > 1) {
    $('customStatus').textContent = '封装区一次处理一个音频文件，已选取第一个文件。';
  }
  setFileInputFiles($('customAudioInput'), [file]);
});

setupDropZone($('playlistDropZone'), files => addLocalAudioFiles(files, false));

$('dirInput').addEventListener('change', (e) => {
  addLocalAudioFiles(Array.from(e.target.files), true);
  e.target.value = '';
});

function addLocalAudioFiles(inputFiles, replace) {
  const files = Array.from(inputFiles).filter(file => AUDIO_EXTENSIONS.test(file.name));
  if (!files.length) {
    $('playlistDropZone').textContent = '没有找到支持的音频；可拖入 MP3、M4A、FLAC、WAV 或 OGG';
    return;
  }
  if (replace) {
    $('localAudioPlayer').pause();
    localTracks.forEach(track => {
      if (track.objectUrl) URL.revokeObjectURL(track.objectUrl);
      if (track.contentUri && track.androidCachedUrl && window.AndroidMusic) AndroidMusic.releaseAudio(track.contentUri);
    });
    localTracks = [];
    playbackQueue = [];
    playbackOrder = [];
    currentTrackIdx = -1;
    $('localAudioPlayer').removeAttribute('src');
    $('localAudioPlayer').load();
    $('nowTitle').textContent = '未选择歌曲';
    $('nowArtist').textContent = '本地音乐离线播放器';
    $('nowCover').src = DEFAULT_COVER;
    parsedLocalLyrics = [];
    renderPlainLyrics($('localLrcContainer'), '', '歌词准备就绪');
  }
  const known = new Set(localTracks.map(localTrackKey));
  const added = files.filter(file => {
    const source = browserFileSources.get(file);
    const key = source && source.key || `${file.name}:${file.size}:${file.lastModified}`;
    if (known.has(key)) return false;
    known.add(key);
    return true;
  }).map(file => {
    const source = browserFileSources.get(file);
    const key = source && source.key || `${file.name}:${file.size}:${file.lastModified}`;
    const fallbackFolder = file.webkitRelativePath ? file.webkitRelativePath.split('/').slice(0, -1).join('/') : '已选歌曲';
    return {
      file, browserKey: source && source.key || '', fileHandle: source && source.handle || null,
      title: file.name.replace(/\.[^/.]+$/, ''), artist: ui('未知歌手'), album: ui('未知专辑'),
      folderPath: source && source.folderPath || fallbackFolder,
      favorite: favoriteTrackKeys.has(key), cover: null, lrc: '', objectUrl: null
    };
  });
  localTracks.push(...added);
  if (!added.length) {
    $('playlistDropZone').textContent = '这些歌曲已在播放列表中';
    return;
  }
  $('playlistDropZone').textContent = `已添加 ${added.length} 首；可继续拖入音乐`;
  renderLocalPlaylist($('searchLocal').value);
  if (!window.jsmediatags) {
    $('playlistDropZone').textContent = '歌曲已添加；标签解析库未加载，播放仍可用，但无法读取封面和内嵌歌词。';
    syncPlayerControls();
    persistNewLocalSelection();
    return;
  }
  added.forEach(track => readLocalTrackMetadata(track));
  syncPlayerControls();
  persistNewLocalSelection();
}

function persistNewLocalSelection() {
  const savedKey = pendingSavedPlayback && pendingSavedPlayback.uri;
  if (pendingSavedPlayback && savedKey && !localTracks.some(track => localTrackKey(track) === savedKey)) return;
  if (pendingSavedPlayback) tryRestoreSavedPlayback();
  persistAndroidPlayback(true);
}

function addDesktopAudioRecords(records, replace, restoring = false) {
  if (!Array.isArray(records) || !records.length) return;
  const items = Array.isArray(records) ? records.filter(record => record && record.path && record.url && AUDIO_EXTENSIONS.test(record.name || '')) : [];
  if (!items.length) {
    $('playlistDropZone').textContent = '没有选择受支持的音乐文件。';
    return;
  }
  if (replace) {
    $('localAudioPlayer').pause();
    localTracks.forEach(track => { if (track.objectUrl) URL.revokeObjectURL(track.objectUrl); });
    localTracks = [];
    playbackQueue = [];
    playbackOrder = [];
    currentTrackIdx = -1;
    $('localAudioPlayer').removeAttribute('src');
    $('localAudioPlayer').load();
    $('nowTitle').textContent = '未选择歌曲';
    $('nowArtist').textContent = '本地音乐离线播放器';
    $('nowCover').src = DEFAULT_COVER;
  }
  const known = new Set(localTracks.map(localTrackKey));
  const added = items.filter(item => !known.has(item.path)).map(item => ({
    file: {name: item.name, size: Number(item.size) || 0, lastModified: Number(item.lastModified) || 0},
    desktopPath: item.path, streamUrl: item.url, metadataUrl: item.url,
    title: item.name.replace(/\.[^/.]+$/, ''), artist: ui('未知歌手'), album: ui('未知专辑'),
    folderPath: item.folderPath || '已选歌曲', favorite: favoriteTrackKeys.has(item.path),
    cover: null, lrc: '', objectUrl: null
  }));
  localTracks.push(...added);
  if (!added.length) {
    $('playlistDropZone').textContent = '这些歌曲已在播放列表中';
    return;
  }
  $('playlistDropZone').textContent = `已添加 ${added.length} 首；关闭后会记住这次选择`;
  added.forEach(track => readLocalTrackMetadata(track));
  renderLocalPlaylist($('searchLocal').value);
  renderQueue();
  syncPlayerControls();
  if (!restoring) persistNewLocalSelection();
}

function localTrackKey(track) {
  if (track.contentUri) return track.contentUri;
  if (track.desktopPath) return track.desktopPath;
  if (track.browserKey) return track.browserKey;
  return `${track.file.name}:${track.file.size}:${track.file.lastModified}`;
}

function showAndroidLocalTab(tab) {
  const showLibrary = tab === 'library';
  androidView = showLibrary ? 'library' : 'player';
  $('playlistCard').style.display = showLibrary ? 'flex' : 'none';
  $('playerMainCard').style.display = showLibrary ? 'none' : 'flex';
  $('androidLibraryTab').classList.toggle('active', showLibrary);
  $('androidNowPlayingTab').classList.toggle('active', !showLibrary);
  updateMiniPlayerVisibility();
  persistAndroidPlayback(true);
}
$('androidLibraryTab').addEventListener('click', () => showAndroidLocalTab('library'));
$('androidNowPlayingTab').addEventListener('click', () => showAndroidLocalTab('player'));

window.onAndroidFolderPicked = (raw, isFinal = true, wasCapped = false) => {
  let records = [];
  try { records = JSON.parse(raw); } catch (_) {}
  const known = new Set(localTracks.map(localTrackKey));
  const added = records.filter(record => record && record.uri && !known.has(record.uri)).map(record => ({
    file: null, contentUri: record.uri, title: record.title || record.name || ui('未知标题'),
    artist: record.artist || ui('未知歌手'), album: record.album || ui('未知专辑'),
    cover: null, lrc: '', folderPath: record.folderPath || '已导入文件夹',
    favorite: favoriteTrackKeys.has(record.uri), objectUrl: null, androidCachedUrl: null
  }));
  localTracks.push(...added);
  $('playlistDropZone').textContent = added.length
    ? `正在导入歌曲：已加入 ${localTracks.length} 首`
    : '正在整理曲库…';
  if (isFinal) {
    $('playlistDropZone').textContent = added.length || localTracks.length
      ? `文件夹导入完成：曲库共 ${localTracks.length} 首${wasCapped ? '（达到单次导入上限）' : ''}`
      : '文件夹中没有新的支持格式音频';
    $('androidScopeNote').textContent = localTracks.length
      ? `曲库已就绪，共 ${localTracks.length} 首歌曲。${wasCapped ? '已达到单次导入上限。' : ''}`
      : '文件夹中没有新的支持格式音频，请选择包含音乐的文件夹。';
    showAndroidNotice(4500);
    if (window.AndroidMusic) refreshAndroidSettingsFolders();
  } else {
    $('androidScopeNote').textContent = `正在载入曲库…已处理 ${localTracks.length} 首`;
    $('androidScopeNote').style.display = 'block';
  }
  renderLocalPlaylist($('searchLocal').value);
  syncPlayerControls();
  if (isFinal) tryRestoreSavedPlayback();
};

// The Android app serves cached tracks from this https path with CORS headers. Requesting them
// as CORS lets Web Audio (the equalizer) process them; file:// media would be silenced.
const ANDROID_MEDIA_PREFIX = 'https://appassets.androidplatform.net/musicdesk-audio/';
function setPlayerSource(player, url) {
  if (String(url || '').startsWith(ANDROID_MEDIA_PREFIX)) player.crossOrigin = 'anonymous';
  else player.removeAttribute('crossorigin');
  player.src = url;
}

window.onAndroidAudioReady = (idx, contentUri, fileUri, error, artworkData) => {
  const track = localTracks[idx];
  if (!track || idx !== currentTrackIdx || track.contentUri !== contentUri) {
    if (window.AndroidMusic) AndroidMusic.releaseAudio(contentUri);
    return;
  }
  if (error || !fileUri) {
    $('androidScopeNote').textContent = error || '无法读取所选音频';
    $('androidScopeNote').style.display = 'block';
    return;
  }
  if (androidNoticeTimer) clearTimeout(androidNoticeTimer);
  $('androidScopeNote').style.display = 'none';
  track.androidCachedUrl = fileUri;
  if (artworkData) {
    track.cover = artworkData;
    $('nowCover').src = artworkData;
    updateMiniPlayer();
    renderLocalPlaylist($('searchLocal').value);
  }
  const player = $('localAudioPlayer');
  setPlayerSource(player, fileUri);
  const resume = window.pendingAudioResume && window.pendingAudioResume.uri === contentUri ? window.pendingAudioResume : null;
  if (resume) {
    player.addEventListener('loadedmetadata', function restorePosition() {
      player.removeEventListener('loadedmetadata', restorePosition);
      player.currentTime = Math.min(resume.position, Number.isFinite(player.duration) ? player.duration : resume.position);
      window.pendingAudioResume = null;
      if (resume.wasPlaying) {
        player.addEventListener('play', () => persistAndroidPlayback(true), {once: true});
        const request = player.play();
        if (request && request.catch) request.catch(() => syncPlayerControls());
      } else {
        persistAndroidPlayback(true);
      }
    }, {once: true});
  } else {
    const playRequest = player.play();
    if (playRequest && playRequest.catch) playRequest.catch(() => syncPlayerControls());
  }
};

function readLocalTrackMetadata(track) {
  jsmediatags.read(track.metadataUrl || track.file, {
    onSuccess: tag => {
      if (!localTracks.includes(track)) return;
      const tags = tag.tags;
      if (tags.title) track.title = tags.title;
      if (tags.artist) track.artist = tags.artist;
      if (tags.album) track.album = tags.album;
      if (tags.picture) {
        const {data, format} = tags.picture;
        let base64String = '';
        for (let i = 0; i < data.length; i++) base64String += String.fromCharCode(data[i]);
        track.cover = `data:${format};base64,${window.btoa(base64String)}`;
      }
      if (tags.lyrics && tags.lyrics.lyrics) track.lrc = tags.lyrics.lyrics;
      const idx = localTracks.indexOf(track);
      updatePlaylistTrackItem(idx);
      if (idx === currentTrackIdx) {
        $('nowTitle').textContent = track.title;
        $('nowArtist').textContent = `${track.artist} - ${track.album}`;
        $('nowCover').src = track.cover || DEFAULT_COVER;
        renderLocalLyrics(track.lrc);
        updateMiniPlayer();
      }
      renderLocalPlaylist($('searchLocal').value);
    }
  });
}

function renderLocalPlaylist(filterText = "") {
  const container = $('localTrackList');
  displayedTrackIndices = [];
  const categoryTitles = {songs: '所有歌曲', artists: '歌手', albums: '专辑', folders: '文件夹', favorites: '我的收藏'};
  $('playlistHeading').textContent = libraryGroup || categoryTitles[libraryCategory] || '所有歌曲';
  $('playlistHeading').title = ui(`${localTracks.length} 首歌曲`);
  $('libraryTrackCount').textContent = `${libraryCategory === 'favorites' ? localTracks.filter(track => track.favorite).length : localTracks.length} 首`;
  $('libraryFilterTabs').querySelectorAll('[data-category]').forEach(button =>
    button.classList.toggle('active', button.dataset.category === libraryCategory));
  $('libraryGroupBack').style.display = libraryGroup ? 'block' : 'none';
  const searched = window.sortLibraryTracks(localTracks.filter(t =>
    t.title.toLowerCase().includes(filterText.toLowerCase()) ||
    t.artist.toLowerCase().includes(filterText.toLowerCase()) ||
    (t.album || '').toLowerCase().includes(filterText.toLowerCase()) ||
    (t.folderPath || '').toLowerCase().includes(filterText.toLowerCase())
  ));
  const categoryFields = {artists: 'artist', albums: 'album', folders: 'folderPath'};
  if (categoryFields[libraryCategory] && !libraryGroup) {
    const field = categoryFields[libraryCategory];
    const groups = new Map();
    searched.forEach(track => {
      const name = track[field] || (field === 'folderPath' ? '已导入文件夹' : '未知');
      groups.set(name, (groups.get(name) || 0) + 1);
    });
    const entries = Array.from(groups.entries()).sort((a, b) => a[0].localeCompare(b[0]));
    container.innerHTML = entries.length ? entries.map(([name, count]) => `
      <button type="button" class="track-item library-group-item" data-library-group="${escapeHTML(name)}" style="text-align:left;color:var(--text);width:100%;margin:0;background:#0d110e;border:1px solid transparent">
        <div class="track-item-info"><strong>${escapeHTML(name)}</strong><small>${count} 首歌曲</small></div>
      </button>`).join('') : '<div style="color:var(--muted);text-align:center;padding:36px 8px">' + ui('暂无分类内容') + '</div>';
    return;
  }
  if (libraryGroup) {
    const field = categoryFields[libraryCategory];
    searched.splice(0, searched.length, ...searched.filter(track => (track[field] || '未知') === libraryGroup));
  }
  const filtered = (libraryCategory === 'favorites' ? searched.filter(track => track.favorite) : searched);
  displayedTrackIndices = filtered.map(track => localTracks.indexOf(track));

  if (filtered.length === 0) {
    container.innerHTML = `<div style="color:var(--muted);font-size:13px;text-align:center;padding:36px 8px">${localTracks.length ? '未找到匹配的本地音乐' : '暂无歌曲；拖入音乐文件即可添加'}</div>`;
    return;
  }

  container.innerHTML = filtered.map((track) => {
    const origIdx = localTracks.indexOf(track);
    const activeCls = origIdx === currentTrackIdx ? "active" : "";
    const coverSrc = track.cover || DEFAULT_COVER;
    return `
      <div class="track-item ${activeCls}" onclick="playLocalTrack(${origIdx})">
        <img id="track-img-${origIdx}" data-artwork-idx="${origIdx}" src="${escapeHTML(coverSrc)}" alt="封面">
        <div class="track-item-info">
          <strong id="track-title-${origIdx}">${escapeHTML(track.title)}</strong>
          <small id="track-artist-${origIdx}">${escapeHTML(track.artist)}</small>
        </div>
        <button type="button" class="track-more" aria-label="更多操作：${escapeHTML(track.title)}" aria-haspopup="dialog" onclick="event.stopPropagation();openTrackMenu(${origIdx})"><svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor" aria-hidden="true"><circle cx="12" cy="5" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="12" cy="19" r="1.7"/></svg></button>
      </div>
    `;
  }).join('');
  observeLibraryArtwork(container);
}

// Library rows only know title/artist from the folder scan. Ask the phone for each visible
// row's embedded artwork (small, disk-cached thumbnails) so covers survive an app restart.
let artworkObserver = null;
function requestTrackArtwork(track) {
  if (!window.AndroidMusic || !track || !track.contentUri || track.cover || track.artworkRequested) return;
  track.artworkRequested = true;
  AndroidMusic.loadArtwork(track.contentUri);
}
function setTrackCoverImages(idx, src) {
  document.querySelectorAll(`img[data-artwork-idx="${idx}"]`).forEach(img => { img.src = src; });
}
function observeLibraryArtwork(container) {
  if (!window.AndroidMusic || !('IntersectionObserver' in window)) return;
  if (!artworkObserver) {
    artworkObserver = new IntersectionObserver(entries => entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      artworkObserver.unobserve(entry.target);
      const idx = Number(entry.target.dataset.artworkIdx);
      requestTrackArtwork(localTracks[idx]);
    }), {rootMargin: '200px'});
  }
  container.querySelectorAll('img[data-artwork-idx]').forEach(img => artworkObserver.observe(img));
}
window.onAndroidLyrics = (contentUri, lyrics) => {
  const idx = localTracks.findIndex(track => track.contentUri === contentUri);
  if (idx < 0 || !lyrics) return;
  const track = localTracks[idx];
  track.lrc = lyrics;
  if (idx === currentTrackIdx) renderLocalLyrics(track.lrc);
};

window.onAndroidArtwork = (contentUri, data) => {
  const idx = localTracks.findIndex(track => track.contentUri === contentUri);
  if (idx < 0) return;
  const track = localTracks[idx];
  track.artworkRequested = true;
  if (!data || track.cover) return;
  track.cover = data;
  // Library rows and the play-queue sheet both show this track's cover.
  setTrackCoverImages(idx, data);
  if (idx === currentTrackIdx) { $('nowCover').src = data; updateMiniPlayer(); }
};

$('libraryFilterTabs').addEventListener('click', event => {
  const button = event.target.closest('[data-category]');
  if (!button) return;
  libraryCategory = button.dataset.category;
  libraryGroup = '';
  renderLocalPlaylist($('searchLocal').value);
  persistAndroidPlayback(true);
});
$('localTrackList').addEventListener('click', event => {
  const button = event.target.closest('[data-library-group]');
  if (!button) return;
  libraryGroup = button.dataset.libraryGroup;
  renderLocalPlaylist($('searchLocal').value);
  persistAndroidPlayback(true);
});
$('libraryGroupBack').addEventListener('click', () => {
  libraryGroup = '';
  renderLocalPlaylist($('searchLocal').value);
  persistAndroidPlayback(true);
});
$('playAllBtn').addEventListener('click', () => {
  if (!localTracks.length) return;
  openPlayAllChoice();
});

function updatePlaylistTrackItem(idx) {
  const t = localTracks[idx];
  const titleEl = $(`track-title-${idx}`);
  const artistEl = $(`track-artist-${idx}`);
  const imgEl = $(`track-img-${idx}`);

  if (titleEl) titleEl.textContent = t.title;
  if (artistEl) artistEl.textContent = t.artist;
  if (imgEl && t.cover) setTrackCoverImages(idx, t.cover);
}

$('searchLocal').addEventListener('input', (e) => { renderLocalPlaylist(e.target.value); persistAndroidPlayback(true); });

function playLocalTrack(idx, keepQueue = false) {
  if (idx < 0 || idx >= localTracks.length) return;
  if (!playbackQueue.includes(localTracks[idx])) {
    const visible = displayedTrackIndices.map(index => localTracks[index]).filter(Boolean);
    playbackQueue = visible.includes(localTracks[idx]) ? visible : [localTracks[idx]];
    updatePlaybackOrder(localTracks[idx]);
  } else if (!keepQueue && playbackMode === 'shuffle') {
    updatePlaybackOrder(localTracks[idx]);
  }
  const player = $('localAudioPlayer');
  const previousTrack = localTracks[currentTrackIdx];
  if (previousTrack && previousTrack.objectUrl) { URL.revokeObjectURL(previousTrack.objectUrl); previousTrack.objectUrl = null; }
  if (previousTrack && previousTrack.contentUri && previousTrack.androidCachedUrl && window.AndroidMusic) {
    AndroidMusic.releaseAudio(previousTrack.contentUri);
    previousTrack.androidCachedUrl = null;
  }
  player.pause();
  currentTrackIdx = idx;
  const track = localTracks[idx];

  $('nowTitle').textContent = track.title;
  $('nowArtist').textContent = `${track.artist} - ${track.album}`;
  $('nowCover').src = track.cover || DEFAULT_COVER;
  $('favoriteTrackBtn').textContent = track.favorite ? '♥' : '♡';
  $('favoriteTrackBtn').classList.toggle('active', !!track.favorite);
  $('favoriteTrackBtn').setAttribute('aria-label', ui(track.favorite ? '取消收藏' : '收藏歌曲'));
  updateMiniPlayer();

  requestTrackArtwork(track);
  if (track.contentUri && window.AndroidMusic) {
    $('androidScopeNote').textContent = '正在从文件夹读取音频…';
    $('androidScopeNote').style.display = 'block';
    AndroidMusic.loadAudio(track.contentUri, idx);
  } else {
    if (track.streamUrl) setPlayerSource(player, track.streamUrl);
    else {
      track.objectUrl = URL.createObjectURL(track.file);
      setPlayerSource(player, track.objectUrl);
    }
    const resume = window.pendingLocalAudioResume && window.pendingLocalAudioResume.uri === localTrackKey(track)
      ? window.pendingLocalAudioResume : null;
    if (resume) {
      player.addEventListener('loadedmetadata', function restoreLocalPosition() {
        player.removeEventListener('loadedmetadata', restoreLocalPosition);
        player.currentTime = Math.min(resume.position, Number.isFinite(player.duration) ? player.duration : resume.position);
        window.pendingLocalAudioResume = null;
        if (resume.wasPlaying) {
          const request = player.play();
          if (request && request.catch) request.catch(() => syncPlayerControls());
        } else syncPlayerControls();
      }, {once: true});
    } else {
      const playRequest = player.play();
      if (playRequest && playRequest.catch) playRequest.catch(() => syncPlayerControls());
    }
  }

  renderLocalPlaylist($('searchLocal').value);
  renderQueue();
  renderLocalLyrics(track.lrc);
  syncPlayerControls();
  if (document.body.classList.contains('android-app')) showAndroidLocalTab('player');
  persistAndroidPlayback(true);
}

function removeLocalTrack(idx) {
  if (idx < 0 || idx >= localTracks.length) return;
  const wasCurrent = idx === currentTrackIdx;
  const [removed] = localTracks.splice(idx, 1);
  playbackQueue = playbackQueue.filter(track => track !== removed);
  playbackOrder = playbackOrder.filter(track => track !== removed);
  if (removed.objectUrl) URL.revokeObjectURL(removed.objectUrl);
  if (removed.contentUri && removed.androidCachedUrl && window.AndroidMusic) AndroidMusic.releaseAudio(removed.contentUri);
  if (wasCurrent) {
    const player = $('localAudioPlayer');
    player.pause();
    player.removeAttribute('src');
    player.load();
    currentTrackIdx = -1;
    if (localTracks.length) playLocalTrack(Math.min(idx, localTracks.length - 1));
    else {
      $('nowTitle').textContent = '未选择歌曲';
      $('nowArtist').textContent = '本地音乐离线播放器';
      $('nowCover').src = DEFAULT_COVER;
      parsedLocalLyrics = [];
      renderPlainLyrics($('localLrcContainer'), '', '歌词准备就绪');
    }
  } else if (idx < currentTrackIdx) {
    currentTrackIdx--;
  }
  renderLocalPlaylist($('searchLocal').value);
  renderQueue();
  syncPlayerControls();
  updateMiniPlayer();
  persistAndroidPlayback(true);
}

function formatPlayerTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const value = Math.floor(seconds);
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
}

function syncPlayerControls() {
  const player = $('localAudioPlayer');
  const hasTrack = currentTrackIdx >= 0 && currentTrackIdx < localTracks.length;
  const queue = getPlaybackOrder();
  const position = queue.indexOf(localTracks[currentTrackIdx]);
  $('previousTrackBtn').disabled = !hasTrack || (playbackMode !== 'shuffle' && position <= 0 && player.currentTime <= 3);
  $('nextTrackBtn').disabled = !hasTrack || (playbackMode === 'sequential' && position >= queue.length - 1);
  $('togglePlaybackBtn').disabled = !hasTrack;
  $('togglePlaybackBtn').textContent = player.paused ? '▶' : 'Ⅱ';
  $('togglePlaybackBtn').setAttribute('aria-label', ui(player.paused ? '播放' : '暂停'));
  $('togglePlaybackBtn').title = ui(player.paused ? '播放' : '暂停');
  $('currentTimeLabel').textContent = formatPlayerTime(player.currentTime);
  $('durationLabel').textContent = formatPlayerTime(player.duration);
  const seek = $('playbackSeek');
  seek.disabled = !hasTrack || !Number.isFinite(player.duration) || player.duration <= 0;
  seek.max = Number.isFinite(player.duration) ? player.duration : 0;
  if (!seek.matches(':active')) seek.value = Number.isFinite(player.currentTime) ? player.currentTime : 0;
  $('playbackModeBtn').textContent = PLAYBACK_MODE_LABELS[playbackMode];
  $('playbackModeBtn').innerHTML = PLAYBACK_MODE_ICONS[playbackMode];
  $('playbackModeBtn').title = ui(`当前：${PLAYBACK_MODE_LABELS[playbackMode]}，点击切换`);
  $('playbackModeBtn').setAttribute('aria-label', ui(`当前：${PLAYBACK_MODE_LABELS[playbackMode]}，点击切换`));
  $('miniPlayBtn').textContent = player.paused ? '▶' : 'Ⅱ';
  $('miniPlayBtn').setAttribute('aria-label', ui(player.paused ? '播放' : '暂停'));
  syncAndroidMediaSession();
}

function syncAndroidMediaSession(force = false) {
  if (!window.AndroidMusic || typeof AndroidMusic.updatePlayback !== 'function') return;
  const now = Date.now();
  if (!force && now - lastMediaSessionUpdate < 900) return;
  lastMediaSessionUpdate = now;
  const track = localTracks[currentTrackIdx];
  if (!track) {
    AndroidMusic.stopPlayback();
    return;
  }
  const player = $('localAudioPlayer');
  AndroidMusic.updatePlayback(JSON.stringify({
    title: track.title || ui('未知标题'), artist: track.artist || ui('未知歌手'), album: track.album || '',
    playing: !player.paused, position: Number(player.currentTime) || 0,
    duration: Number.isFinite(player.duration) ? player.duration : 0,
    artwork: track.cover || '', mode: playbackMode
  }));
}

function updateMiniPlayerVisibility() {
  // The mini player follows you across Download / Settings, and steps aside while the full
  // Now Playing view is on screen, on the Edit page (where fields need the room) and
  // whenever the keyboard is up.
  const mini = $('androidMiniPlayer');
  if (!mini || !document.body.classList.contains('android-app')) return;
  const onLocal = $('tab-local').classList.contains('active');
  const onEdit = $('tab-custom').classList.contains('active');
  const visible = currentTrackIdx >= 0 && !(onLocal && androidView === 'player') && !onEdit && !document.body.classList.contains('typing');
  mini.style.display = visible ? 'flex' : 'none';
  document.body.classList.toggle('has-mini', visible && !onLocal);
}

// While a text field has focus the on-screen keyboard is up: give the field the whole screen.
function isTextField(node) {
  return node instanceof HTMLElement && (node.matches('textarea, select') || (node.matches('input') && !/^(checkbox|radio|range|button|file|submit)$/.test(node.type)));
}
document.addEventListener('focusin', event => {
  if (!isTextField(event.target)) return;
  document.body.classList.add('typing');
  updateMiniPlayerVisibility();
});
document.addEventListener('focusout', () => {
  setTimeout(() => {
    if (isTextField(document.activeElement)) return;
    document.body.classList.remove('typing');
    updateMiniPlayerVisibility();
  }, 50);
});

function updateMiniPlayer() {
  updateMiniPlayerVisibility();
  const track = localTracks[currentTrackIdx];
  if (!track) {
    $('miniTitle').textContent = '未选择歌曲';
    $('miniArtist').textContent = '本地音乐离线播放器';
    $('miniCover').src = DEFAULT_COVER;
    return;
  }
  $('miniTitle').textContent = track.title;
  $('miniArtist').textContent = track.artist;
  $('miniCover').src = track.cover || DEFAULT_COVER;
}

function nextLocalTrack() {
  const queue = getPlaybackOrder();
  const currentTrack = localTracks[currentTrackIdx];
  const position = queue.indexOf(currentTrack);
  if (!queue.length || position < 0) return;
  if (position + 1 < queue.length) {
    playLocalTrack(localTracks.indexOf(queue[position + 1]), true);
  } else if (playbackMode === 'repeat-all') {
    playLocalTrack(localTracks.indexOf(queue[0]), true);
  }
}

function previousLocalTrack() {
  const player = $('localAudioPlayer');
  if (player.currentTime > 3) { player.currentTime = 0; return; }
  const queue = getPlaybackOrder();
  const position = queue.indexOf(localTracks[currentTrackIdx]);
  if (position > 0) playLocalTrack(localTracks.indexOf(queue[position - 1]), true);
  else if (playbackMode === 'repeat-all' && queue.length) playLocalTrack(localTracks.indexOf(queue[queue.length - 1]), true);
}

function renderQueue() {
  const queue = playbackQueue.length ? playbackQueue : localTracks;
  $('queueTitle').textContent = `播放列表（${queue.length} 首）`;
  $('queueList').innerHTML = queue.map(track => {
    const idx = localTracks.indexOf(track);
    return `
    <div class="track-item ${idx === currentTrackIdx ? 'active' : ''}" onclick="playLocalTrack(${idx},true);closeQueue()">
      <img data-artwork-idx="${idx}" src="${escapeHTML(track.cover || DEFAULT_COVER)}" alt="">
      <div class="track-item-info"><strong>${escapeHTML(track.title)}</strong><small>${escapeHTML(track.artist)} - ${escapeHTML(track.album)}</small></div>
      <button type="button" class="track-more" aria-label="更多操作：${escapeHTML(track.title)}" aria-haspopup="dialog" onclick="event.stopPropagation();openTrackMenu(${idx})"><svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor" aria-hidden="true"><circle cx="12" cy="5" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="12" cy="19" r="1.7"/></svg></button>
    </div>`;
  }).join('') || '<div style="color:var(--muted);text-align:center;padding:30px">' + ui('播放列表为空') + '</div>';
  // Queue rows load embedded covers lazily, like library rows, as they scroll into view.
  observeLibraryArtwork($('queueList'));
}


let trackMenuIndex = -1, trackMenuOpener = null;
function openTrackMenu(index) {
  const track = localTracks[index];
  if (!track) return;
  trackMenuIndex = index;
  trackMenuOpener = document.activeElement;
  $('trackMenuTitle').textContent = track.title;
  $('trackMenuBackdrop').hidden = false;
  requestAnimationFrame(() => { $('trackMenuSheet').classList.add('open'); $('trackMenuCancel').focus(); });
  if (window.AndroidMusic) AndroidMusic.setQueueOpen(true);
}
function closeTrackMenu() {
  $('trackMenuSheet').classList.remove('open');
  $('trackMenuBackdrop').hidden = true;
  trackMenuIndex = -1;
  if (trackMenuOpener && trackMenuOpener.isConnected) trackMenuOpener.focus();
  trackMenuOpener = null;
  if (window.AndroidMusic) AndroidMusic.setQueueOpen(false);
}
$('trackMenuCancel').addEventListener('click', closeTrackMenu);
$('trackMenuBackdrop').addEventListener('click', event => { if (event.target === $('trackMenuBackdrop')) closeTrackMenu(); });
$('trackMenuRemove').addEventListener('click', () => { const index = trackMenuIndex; closeTrackMenu(); if (index >= 0) removeLocalTrack(index); });
document.addEventListener('keydown', event => { if (event.key === 'Escape' && !$('trackMenuBackdrop').hidden) closeTrackMenu(); });
function openPlayAllChoice() {
  $('playAllBackdrop').hidden = false;
  $('playAllSheet').style.transform = '';
  $('playAllSheet').style.transition = '';
  requestAnimationFrame(() => $('playAllSheet').classList.add('open'));
  if (window.AndroidMusic) AndroidMusic.setQueueOpen(true);
}

function closePlayAllChoice() {
  $('playAllSheet').classList.remove('open');
  $('playAllSheet').style.transform = '';
  $('playAllSheet').style.transition = '';
  $('playAllBackdrop').hidden = true;
  if (window.AndroidMusic) AndroidMusic.setQueueOpen(false);
}

function startPlayAll(order) {
  const indices = displayedTrackIndices.length ? displayedTrackIndices.slice() : localTracks.map((_, index) => index);
  if (!indices.length) return;
  const tracks = indices.map(index => localTracks[index]).filter(Boolean);
  playbackQueue = order === 'shuffle' ? shuffleTracks(tracks) : tracks;
  updatePlaybackOrder(playbackQueue[0]);
  closePlayAllChoice();
  syncPlayerControls();
  playLocalTrack(localTracks.indexOf(playbackQueue[0]), true);
}

function getPlaybackOrder() {
  const queue = playbackQueue.length ? playbackQueue : localTracks;
  if (playbackMode !== 'shuffle') return queue;
  playbackOrder = playbackOrder.filter(track => queue.includes(track));
  const missing = queue.filter(track => !playbackOrder.includes(track));
  playbackOrder.push(...missing);
  return playbackOrder;
}

function updatePlaybackOrder(firstTrack = null) {
  const queue = playbackQueue.length ? playbackQueue : localTracks;
  if (playbackMode !== 'shuffle') {
    playbackOrder = queue.slice();
    return;
  }
  const first = firstTrack && queue.includes(firstTrack) ? firstTrack : queue[0];
  const remaining = queue.filter(track => track !== first);
  shuffleTracks(remaining);
  playbackOrder = first ? [first, ...remaining] : remaining;
}

function shuffleTracks(tracks) {
  for (let i = tracks.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [tracks[i], tracks[j]] = [tracks[j], tracks[i]];
  }
  return tracks;
}

$('playAllSequentialBtn').addEventListener('click', () => startPlayAll('sequential'));
$('playAllShuffleBtn').addEventListener('click', () => startPlayAll('shuffle'));
$('closePlayAllBtn').addEventListener('click', closePlayAllChoice);
$('playAllBackdrop').addEventListener('click', event => { if (event.target === $('playAllBackdrop')) closePlayAllChoice(); });

function openQueue() {
  renderQueue();
  if (queueCloseTimer) clearTimeout(queueCloseTimer);
  $('queueBackdrop').hidden = false;
  $('queueSheet').style.transform = '';
  requestAnimationFrame(() => $('queueSheet').classList.add('open'));
  if (window.AndroidMusic) AndroidMusic.setQueueOpen(true);
}

function closeQueue() {
  if ($('queueBackdrop').hidden) {
    if (!$('trackMenuBackdrop').hidden) closeTrackMenu();
    else if (!$('guideBackdrop').hidden) closeGuide();
    else if (!$('playAllBackdrop').hidden) closePlayAllChoice();
    else if ($('downloadSettingsPanel').classList.contains('open')) closeDownloadSettings();
    return;
  }
  $('queueSheet').classList.remove('open');
  $('queueSheet').style.transform = '';
  $('queueSheet').style.transition = '';
  if (window.AndroidMusic) AndroidMusic.setQueueOpen(false);
  if (queueCloseTimer) clearTimeout(queueCloseTimer);
  queueCloseTimer = setTimeout(() => { $('queueBackdrop').hidden = true; }, 240);
}

function showAndroidNotice(hideAfterMs = 0) {
  const note = $('androidScopeNote');
  note.style.display = 'block';
  if (androidNoticeTimer) clearTimeout(androidNoticeTimer);
  if (hideAfterMs > 0) androidNoticeTimer = setTimeout(() => { note.style.display = 'none'; }, hideAfterMs);
}

const queueDragHandle = $('queueDragHandle');
queueDragHandle.addEventListener('pointerdown', event => {
  if (event.pointerType !== 'mouse') return;
  queueDragStartY = event.clientY;
  queueDragLastTime = performance.now();
  queueDragVelocity = 0;
  queueDragHandle.dataset.lastDelta = '0';
  try { queueDragHandle.setPointerCapture(event.pointerId); } catch (_) {}
});
queueDragHandle.addEventListener('pointermove', event => {
  if (queueDragStartY === null || event.pointerType !== 'mouse') return;
  const delta = event.clientY - queueDragStartY;
  const now = performance.now();
  queueDragVelocity = (event.clientY - (queueDragStartY + Number(queueDragHandle.dataset.lastDelta || 0))) / Math.max(1, now - queueDragLastTime);
  queueDragLastTime = now;
  queueDragHandle.dataset.lastDelta = String(delta);
  if (delta >= 0) $('queueSheet').style.transform = `translateY(${delta}px)`;
});
function finishQueueDrag() {
  if (queueDragStartY === null) return;
  const delta = Number(queueDragHandle.dataset.lastDelta || 0);
  queueDragHandle.dataset.lastDelta = '0';
  queueDragStartY = null;
  if (delta > 100 || (delta > 35 && queueDragVelocity > 0.55)) closeQueue();
  else {
    $('queueSheet').style.transform = '';
    $('queueSheet').style.maxHeight = '';
  }
}
queueDragHandle.addEventListener('pointerup', finishQueueDrag);
queueDragHandle.addEventListener('pointercancel', finishQueueDrag);

$('queueSheet').addEventListener('touchstart', event => {
  if (!$('queueList').contains(event.target) && !$('queueDragHandle').contains(event.target) && !event.target.closest('.queue-header')) return;
  queueTouchStartY = event.touches[0].clientY;
  queueTouchDragging = $('queueList').scrollTop === 0 || !$('queueList').contains(event.target);
}, {passive: true});
$('queueSheet').addEventListener('touchmove', event => {
  if (queueTouchStartY === null || !queueTouchDragging || $('queueList').scrollTop > 0) return;
  const delta = event.touches[0].clientY - queueTouchStartY;
  if (delta < 8) return;
  queueTouchDragging = true;
  event.preventDefault();
  $('queueSheet').style.transition = 'none';
  $('queueSheet').style.transform = `translateY(${delta}px)`;
}, {passive: false});
function finishQueueTouch() {
  if (queueTouchStartY === null) return;
  const sheet = $('queueSheet');
  const match = /translateY\((\d+(?:\.\d+)?)px\)/.exec(sheet.style.transform);
  const delta = match ? Number(match[1]) : 0;
  queueTouchStartY = null;
  if (!queueTouchDragging) return;
  queueTouchDragging = false;
  sheet.style.transition = '';
  if (delta > 90) closeQueue();
  else sheet.style.transform = '';
}
$('queueSheet').addEventListener('touchend', finishQueueTouch, {passive: true});
$('queueSheet').addEventListener('touchcancel', finishQueueTouch, {passive: true});

const playAllSheet = $('playAllSheet');
let playAllTouchStartY = null;
let playAllTouchDelta = 0;
playAllSheet.addEventListener('touchstart', event => {
  if (!event.target.closest('.queue-drag-handle, .queue-header')) return;
  playAllTouchStartY = event.touches[0].clientY;
  playAllTouchDelta = 0;
}, {passive: true});
playAllSheet.addEventListener('touchmove', event => {
  if (playAllTouchStartY === null) return;
  playAllTouchDelta = event.touches[0].clientY - playAllTouchStartY;
  if (playAllTouchDelta < 8) return;
  event.preventDefault();
  playAllSheet.style.transition = 'none';
  playAllSheet.style.transform = `translateY(${playAllTouchDelta}px)`;
}, {passive: false});
function finishPlayAllTouch() {
  if (playAllTouchStartY === null) return;
  playAllTouchStartY = null;
  playAllSheet.style.transition = '';
  if (playAllTouchDelta > 70) closePlayAllChoice();
  else playAllSheet.style.transform = '';
  playAllTouchDelta = 0;
}
playAllSheet.addEventListener('touchend', finishPlayAllTouch, {passive: true});
playAllSheet.addEventListener('touchcancel', finishPlayAllTouch, {passive: true});

function clearQueue() {
  $('localAudioPlayer').pause();
  localTracks.forEach(track => {
    if (track.objectUrl) URL.revokeObjectURL(track.objectUrl);
    if (track.contentUri && track.androidCachedUrl && window.AndroidMusic) AndroidMusic.releaseAudio(track.contentUri);
  });
  localTracks = [];
  playbackQueue = [];
  playbackOrder = [];
  currentTrackIdx = -1;
  $('localAudioPlayer').removeAttribute('src');
  $('localAudioPlayer').load();
  $('nowTitle').textContent = '未选择歌曲';
  $('nowArtist').textContent = '本地音乐离线播放器';
  $('nowCover').src = DEFAULT_COVER;
  renderLocalLyrics('');
  renderLocalPlaylist($('searchLocal').value);
  renderQueue();
  updateMiniPlayer();
  syncPlayerControls();
  closeQueue();
  persistAndroidPlayback(true);
}

$('playbackModeBtn').addEventListener('click', () => {
  playbackMode = PLAYBACK_MODES[(PLAYBACK_MODES.indexOf(playbackMode) + 1) % PLAYBACK_MODES.length];
  updatePlaybackOrder(localTracks[currentTrackIdx] || playbackQueue[0]);
  syncPlayerControls();
  persistAndroidPlayback(true);
});
$('playerSongViewBtn').addEventListener('click', () => setPlayerContentView('song'));
$('playerLyricsViewBtn').addEventListener('click', () => setPlayerContentView('lyrics'));
$('playerCollapseBtn').addEventListener('click', () => showAndroidLocalTab('library'));
function setPlayerContentView(view) {
  androidContentView = view === 'lyrics' ? 'lyrics' : 'song';
  const lyrics = view === 'lyrics';
  $('playerSongPanel').style.display = lyrics ? 'none' : 'flex';
  $('localLyricsViewer').style.display = lyrics ? 'block' : 'none';
  $('playerSongViewBtn').classList.toggle('active', !lyrics);
  $('playerLyricsViewBtn').classList.toggle('active', lyrics);
  persistAndroidPlayback(true);
}
$('favoriteTrackBtn').addEventListener('click', () => {
  const track = localTracks[currentTrackIdx];
  if (!track) return;
  track.favorite = !track.favorite;
  const key = localTrackKey(track);
  if (track.favorite) favoriteTrackKeys.add(key); else favoriteTrackKeys.delete(key);
  try { localStorage.setItem('musicdesk-favorites', JSON.stringify(Array.from(favoriteTrackKeys))); } catch (_) {}
  $('favoriteTrackBtn').textContent = track.favorite ? '♥' : '♡';
  $('favoriteTrackBtn').classList.toggle('active', track.favorite);
  renderLocalPlaylist($('searchLocal').value);
});
$('openQueueBtn').addEventListener('click', openQueue);
$('miniQueueBtn').addEventListener('click', openQueue);
$('miniPlayBtn').addEventListener('click', () => $('togglePlaybackBtn').click());
$('miniPlayerOpen').addEventListener('click', () => { switchTab('local'); showAndroidLocalTab('player'); });
$('clearQueueBtn').addEventListener('click', clearQueue);
$('closeQueueBtn').addEventListener('click', closeQueue);
$('queueBackdrop').addEventListener('click', event => { if (event.target === $('queueBackdrop')) closeQueue(); });

$('togglePlaybackBtn').addEventListener('click', () => {
  const player = $('localAudioPlayer');
  if (player.paused) {
    const playRequest = player.play();
    if (playRequest && playRequest.catch) playRequest.catch(() => syncPlayerControls());
  } else player.pause();
});
$('previousTrackBtn').addEventListener('click', () => {
  previousLocalTrack();
});
$('nextTrackBtn').addEventListener('click', () => {
  nextLocalTrack();
});
$('playbackSeek').addEventListener('input', event => {
  $('localAudioPlayer').currentTime = Number(event.target.value);
  syncPlayerControls();
});
['timeupdate', 'loadedmetadata', 'durationchange', 'play', 'pause', 'ended'].forEach(type =>
  $('localAudioPlayer').addEventListener(type, () => {
    syncPlayerControls();
    if (type !== 'timeupdate') syncAndroidMediaSession(true);
    if (type !== 'timeupdate' || Math.floor($('localAudioPlayer').currentTime / 3) !== lastSavedPlaybackBucket) persistAndroidPlayback(type !== 'timeupdate');
  })
);

window.onAndroidMediaCommand = (command, position) => {
  const player = $('localAudioPlayer');
  if (command === 'play') player.play().catch(() => syncPlayerControls());
  else if (command === 'pause') player.pause();
  else if (command === 'next') nextLocalTrack();
  else if (command === 'previous') previousLocalTrack();
  else if (command === 'seek_to' && Number.isFinite(position) && position >= 0) player.currentTime = position / 1000;
  else if (command === 'toggle_mode') {
    playbackMode = PLAYBACK_MODES[(PLAYBACK_MODES.indexOf(playbackMode) + 1) % PLAYBACK_MODES.length];
    updatePlaybackOrder();
    syncPlayerControls();
    persistAndroidPlayback(true);
    syncAndroidMediaSession(true);
  }
};

function renderLocalLyrics(lrcText) {
  lastLocalLrcText = lrcText;
  parsedLocalLyrics = groupLyricTranslations(parseLRC(lrcText));
  const container = $('localLrcContainer');
  if (parsedLocalLyrics.length === 0) {
    renderPlainLyrics(container, lrcText, '暂无内嵌歌词');
    return;
  }
  container.innerHTML = parsedLocalLyrics.map((item, idx) => lyricLineHtml(item, `local-lrc-${idx}`)).join('');

  container.querySelectorAll('.lrc-line').forEach((el) => {
    el.addEventListener('click', () => {
      const time = parseFloat(el.getAttribute('data-time'));
      const player = $('localAudioPlayer');
      if (player.src) { player.currentTime = time; player.play(); }
    });
  });
}

$('localAudioPlayer').addEventListener('timeupdate', () => {
  const currentTime = $('localAudioPlayer').currentTime;
  if (!parsedLocalLyrics.length) return;
  let activeIndex = -1;
  for (let i = 0; i < parsedLocalLyrics.length; i++) {
    if (currentTime >= parsedLocalLyrics[i].time) activeIndex = i; else break;
  }
  if (activeIndex !== -1) {
    document.querySelectorAll('#localLyricsViewer .lrc-line').forEach(el => el.classList.remove('active'));
    const activeEl = $(`local-lrc-${activeIndex}`);
    if (activeEl) {
      activeEl.classList.add('active');
      const viewer = $('localLyricsViewer');
      viewer.scrollTop = activeEl.offsetTop - viewer.offsetTop - 50;
    }
  }
});

// 自动顺序播放下一首
$('localAudioPlayer').addEventListener('ended', () => {
  if (playbackMode === 'repeat-one') {
    $('localAudioPlayer').currentTime = 0;
    $('localAudioPlayer').play().catch(() => syncPlayerControls());
  } else nextLocalTrack();
});

if (/MusicDeskAndroid/i.test(navigator.userAgent)) {
  const viewport = document.querySelector('meta[name="viewport"]');
  if (viewport) viewport.content = 'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover';
  document.body.classList.add('android-app');
  $('androidOnlineNote').style.display = 'block';
  $('androidCustomNote').style.display = 'block';
  $('androidApiConnectCard').style.display = 'block';
  refreshAndroidSettings();
  if (androidApiConfig) {
    $('apiServerUrl').value = androidApiConfig.url || '';
    $('apiPairingToken').value = androidApiConfig.token || '';
    testAndroidApiConnection(androidApiConfig, false);
  }
  updateApiConnectionMessage(false);
  $('selectDirBtn').style.display = 'inline-block';
  $('selectDirBtn').textContent = '选择文件夹';
  $('selectFilesBtn').style.display = 'inline-block';
  $('selectFilesBtn').textContent = '选择歌曲';
  $('playlistDropZone').style.display = 'none';
  $('androidScopeNote').style.display = 'none';
  $('libraryFilterTabs').style.display = 'flex';
  showAndroidLocalTab('library');
  switchTab('local');
  renderLocalPlaylist('');
  renderQueue();
  AndroidMusic.restoreFolders();
}

async function restoreDesktopLibrary() {
  const api = window.pywebview && window.pywebview.api;
  if (!api || !api.load_playback_state || !api.restore_audio_files) return;
  try {
    const state = await api.load_playback_state();
    if (state && typeof state === 'object' && Object.keys(state).length) {
      pendingSavedPlayback = state;
      try { localStorage.setItem('musicdesk-playback-state', JSON.stringify(state)); } catch (_) {}
    }
    const records = await api.restore_audio_files();
    if (records && records.length) {
      addDesktopAudioRecords(records, true, true);
      tryRestoreSavedPlayback();
    } else if (state && Array.isArray(state.desktopFiles) && state.desktopFiles.length) {
      $('playlistDropZone').textContent = '上次的音乐文件暂时无法访问，请重新选择文件夹或歌曲。';
    }
  } catch (_) {
    $('playlistDropZone').textContent = '无法恢复上次的曲库，请重新选择文件夹或歌曲。';
  }
}
if (window.pywebview && window.pywebview.api) restoreDesktopLibrary();
else window.addEventListener('pywebviewready', restoreDesktopLibrary, {once: true});

async function restoreBrowserLibrary() {
  if (window.AndroidMusic || (window.pywebview && window.pywebview.api) || !window.indexedDB) return;
  try {
    const handles = await loadFileHandles();
    const files = [];
    let needsPermission = false;
    const directory = handles.find(item => item.key === 'library-directory');
    if (directory) {
      if (await hasReadPermission(directory.handle)) files.push(...await collectDirectoryAudio(directory.handle));
      else needsPermission = true;
    }
    for (const item of handles.filter(record => record.key.startsWith('file:'))) {
      if (!(await hasReadPermission(item.handle))) { needsPermission = true; continue; }
      const file = await item.handle.getFile();
      browserFileSources.set(file, {key: item.key, handle: item.handle, folderPath: '已选歌曲'});
      files.push(file);
    }
    if (files.length) addLocalAudioFiles(files, true);
    else if (needsPermission || (pendingSavedPlayback && pendingSavedPlayback.uri)) {
      $('playlistDropZone').textContent = '浏览器需要重新授权访问上次的音乐文件；请点击“选择文件夹”或“选择歌曲”。';
    }
  } catch (_) {
    if (pendingSavedPlayback && pendingSavedPlayback.uri) {
      $('playlistDropZone').textContent = '无法恢复上次的音乐文件，请重新选择文件夹或歌曲。';
    }
  }
}
if (!window.AndroidMusic && !(window.pywebview && window.pywebview.api)) restoreBrowserLibrary();

// Initialize the playback mode control immediately on every platform so it
// renders the selected mode icon before the first user interaction.

initSettings();
syncPlayerControls();

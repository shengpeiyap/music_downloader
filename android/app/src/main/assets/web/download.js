// Online search, download settings, preview, candidates, and batch queue.
function androidLyricsStatusText(status) {
  if (status === 'synced') return '已嵌入同步 LRC 歌词';
  if (status === 'plain') return '已嵌入普通歌词（来源无时间戳）';
  return '未找到歌词，将不嵌入歌词';
}

function androidDownloadSource(metadata) {
  if (metadata && metadata.url && metadata.provider !== 'spotify') return metadata.url;
  return `ytsearch1:${metadata && metadata.artist || ''} ${metadata && metadata.title || ''}`.trim();
}

function getDownloadSettings() {
  return {format:$('downloadFormat').value, bitrate:$('downloadBitrate').value, download_lrc:sidecarLrcWanted()};
}
// A standalone .lrc needs the computer service. While the phone is unpaired the switch is
// forced off and locked, but the person's own choice is kept and restored once connected.
function sidecarLrcLocked() { return !!window.AndroidMusic && !androidApiConnected; }
function sidecarLrcWanted() {
  const box = $('downloadSidecarLrc');
  return sidecarLrcLocked() ? false : box.checked;
}
function syncSidecarLrcLock() {
  const box = $('downloadSidecarLrc');
  if (sidecarLrcLocked()) {
    if (!box.disabled) box.dataset.pref = String(box.checked);
    box.checked = false; box.disabled = true;
  } else if (box.disabled) {
    box.checked = box.dataset.pref === 'true'; box.disabled = false;
  }
  $('sidecarLrcNote').hidden = !sidecarLrcLocked();
}
function saveDownloadSettings() {
  const box = $('downloadSidecarLrc');
  const stored = {...getDownloadSettings(), download_lrc: box.disabled ? box.dataset.pref === 'true' : box.checked};
  try { localStorage.setItem('musicdesk-download-settings', JSON.stringify(stored)); } catch (_) {}
  $('downloadBitrate').disabled = ['flac', 'wav'].includes($('downloadFormat').value);
  updateOnlineDownloadLabel();
}
const CHIP_GROUPS = {
  enginePriority: {box: 'engineChips', label: option => option.textContent.replace(/（.*）/, '').trim()},
  downloadFormat: {box: 'formatChips', label: option => option.value === 'm4a' ? 'M4A' : option.textContent.trim()},
  downloadBitrate: {box: 'bitrateChips', label: option => option.value}
};
function downloadOptionNeedsComputer(selectId, value) {
  // Android without a paired computer can only fetch MP3 at the default bitrate with yt-dlp.
  if (!window.AndroidMusic || androidApiConnected) return false;
  if (selectId === 'downloadFormat') return value !== 'mp3';
  if (selectId === 'downloadBitrate') return value !== '192';
  if (selectId === 'enginePriority') return value === 'spotdl';
  return false;
}
function renderChipGroups() {
  syncSidecarLrcLock();
  for (const [selectId, config] of Object.entries(CHIP_GROUPS)) {
    const select = $(selectId), box = $(config.box);
    if (!select || !box) continue;
    box.replaceChildren(...Array.from(select.options).map(option => {
      const button = document.createElement('button');
      const on = select.value === option.value;
      const gated = downloadOptionNeedsComputer(selectId, option.value);
      const blocked = selectId === 'enginePriority' && select.disabled && option.value !== select.value;
      button.type = 'button';
      button.className = 'chip' + (on ? ' on' : '') + (gated ? ' needs-computer' : '');
      button.textContent = config.label(option);
      button.setAttribute('aria-pressed', String(on));
      if (gated) button.setAttribute('aria-label', ui(`${button.textContent}，需要连接电脑`));
      if (select.disabled && selectId === 'downloadBitrate') button.disabled = true;
      button.addEventListener('click', () => {
        if (blocked) { $('downloadComputerNote').hidden = false; $('downloadConnectLink').focus(); return; }
        select.value = option.value;
        select.dispatchEvent(new Event('change', {bubbles: true}));
      });
      return button;
    }));
  }
  const phoneLocal = !!window.AndroidMusic && !androidApiConnected;
  $('downloadComputerNote').hidden = !phoneLocal;
  $('downloadBitrateNote').textContent = $('downloadBitrate').disabled ? '无损格式不使用比特率' : '';
}
function downloadSettingsAreSheet() { return window.matchMedia('(max-width: 959px)').matches; }
function openDownloadSettings() {
  const panel = $('downloadSettingsPanel');
  panel.classList.add('open');
  $('downloadSettingsBackdrop').hidden = false;
  panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-modal', 'true');
  $('closeDownloadSettings').focus();
  if (window.AndroidMusic) AndroidMusic.setQueueOpen(true);
}
function closeDownloadSettings() {
  const panel = $('downloadSettingsPanel');
  const wasOpen = panel.classList.contains('open');
  panel.classList.remove('open');
  $('downloadSettingsBackdrop').hidden = true;
  panel.removeAttribute('role'); panel.removeAttribute('aria-modal');
  if (wasOpen) $('openDownloadSettings').focus();
  if (window.AndroidMusic) AndroidMusic.setQueueOpen(false);
}
// Swipe a sheet down from its handle/header to dismiss it (phone layouts only).
function enableSwipeDown(handles, sheet, close) {
  let startY = null, delta = 0, startTime = 0;
  const reset = () => { sheet.style.transition = ''; sheet.style.transform = ''; startY = null; delta = 0; };
  handles.forEach(handle => {
    handle.style.touchAction = 'none';
    handle.addEventListener('pointerdown', event => {
      if (event.target.closest('button')) return;
      startY = event.clientY; delta = 0; startTime = performance.now();
      sheet.style.transition = 'none';
      try { handle.setPointerCapture(event.pointerId); } catch (_) {}
    });
    handle.addEventListener('pointermove', event => {
      if (startY === null) return;
      delta = Math.max(0, event.clientY - startY);
      sheet.style.transform = `translateY(${delta}px)`;
    });
    const end = () => {
      if (startY === null) return;
      const fast = delta / Math.max(1, performance.now() - startTime) > 0.6;
      const dismiss = delta > 90 || (fast && delta > 30);
      reset();
      if (dismiss) close();
    };
    handle.addEventListener('pointerup', end);
    handle.addEventListener('pointercancel', reset);
  });
}
enableSwipeDown([document.querySelector('#downloadSettingsPanel .sheet-handle'), document.querySelector('#downloadSettingsPanel .sheet-head')], $('downloadSettingsPanel'), () => { if (downloadSettingsAreSheet()) closeDownloadSettings(); });
$('openDownloadSettings').addEventListener('click', openDownloadSettings);
$('closeDownloadSettings').addEventListener('click', closeDownloadSettings);
$('downloadSettingsBackdrop').addEventListener('click', closeDownloadSettings);
$('downloadConnectLink').addEventListener('click', () => { closeDownloadSettings(); switchTab('settings'); });
document.addEventListener('keydown', event => { if (event.key === 'Escape' && $('downloadSettingsPanel').classList.contains('open')) closeDownloadSettings(); });
window.matchMedia('(min-width: 960px)').addEventListener('change', event => { if (event.matches) closeDownloadSettings(); });
function updateDownloadSettingsSummary() {
  renderChipGroups();
  const el = $('downloadSettingsSummary');
  if (!el) return;
  const format = $('downloadFormat').value;
  const parts = [format.toUpperCase()];
  if (!['flac', 'wav'].includes(format)) parts.push(`${$('downloadBitrate').value} kbps`);
  if (sidecarLrcWanted()) parts.push('含 .lrc');
  el.textContent = parts.join(' · ');
}
function updateOnlineDownloadLabel() {
  updateDownloadSettingsSummary();
  if (window.AndroidMusic) { updateAndroidDownloadButtonLabel(); return; }
  const settings = getDownloadSettings();
  $('downloadBtn').textContent = `下载 ${settings.format.toUpperCase()}${settings.download_lrc ? ' + LRC' : ''}`;
}
function youtubeVideoId(metadata) {
  const raw = metadata && (metadata.preview_url || metadata.url);
  if (!raw) return '';
  try {
    const url = new URL(raw), host = url.hostname.toLowerCase(); let id = '';
    if (host === 'youtu.be') id = url.pathname.split('/').filter(Boolean)[0] || '';
    else if (['youtube.com','www.youtube.com','m.youtube.com','music.youtube.com'].includes(host)) {
      if (url.pathname === '/watch') id = url.searchParams.get('v') || '';
      else if (/^\/(embed|shorts)\//.test(url.pathname)) id = url.pathname.split('/')[2] || '';
    }
    return /^[A-Za-z0-9_-]{11}$/.test(id) ? id : '';
  } catch (_) { return ''; }
}
function updateYouTubePreview() {
  const id = youtubeVideoId(currentMetadata);
  $('youtubePreviewPanel').style.display = id ? 'block' : 'none';
  if (id) {
    $('youtubeOpenLink').href = `https://www.youtube.com/watch?v=${encodeURIComponent(id)}`;
    $('youtubeOpenLink').target = window.AndroidMusic ? '_self' : '_blank';
    $('youtubePreviewBtn').textContent = window.AndroidMusic ? '在浏览器试听' : 'YouTube 试听';
  }
  $('youtubePreviewFrame').replaceChildren(); $('youtubePreviewFrame').style.display = 'none';
}
try {
  const saved = JSON.parse(localStorage.getItem('musicdesk-download-settings') || '{}');
  if (['mp3','m4a','flac','wav','ogg'].includes(saved.format)) $('downloadFormat').value = saved.format;
  if (['128','192','256','320'].includes(String(saved.bitrate))) $('downloadBitrate').value = String(saved.bitrate);
  $('downloadSidecarLrc').checked = saved.download_lrc === true;
} catch (_) {}
['downloadFormat','downloadBitrate','downloadSidecarLrc'].forEach(id => $(id).addEventListener('change', saveDownloadSettings));
$('enginePriority').addEventListener('change', updateDownloadSettingsSummary);
$('downloadBitrate').disabled = ['flac', 'wav'].includes($('downloadFormat').value);
updateOnlineDownloadLabel();
$('youtubePreviewBtn').addEventListener('click', () => {
  const id = youtubeVideoId(currentMetadata); if (!id) return;
  if (window.AndroidMusic) { window.location.href = `https://www.youtube.com/watch?v=${encodeURIComponent(id)}`; return; }
  const frame = document.createElement('iframe'); frame.title = 'YouTube 歌曲试听'; frame.width = '100%'; frame.height = '220'; frame.style.border = '0';
  frame.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share'; frame.allowFullscreen = true; frame.referrerPolicy = 'strict-origin-when-cross-origin';
  frame.src = `https://www.youtube.com/embed/${encodeURIComponent(id)}?playsinline=1`;
  $('youtubePreviewFrame').replaceChildren(frame); $('youtubePreviewFrame').style.display = 'block';
});

const PLAYLIST_URL_RE = /^https:\/\/(?:music\.|www\.)?youtube\.com\/playlist\?(?:[^#]*&)?list=[A-Za-z0-9_-]{10,64}/i;
let batchEntries = [], batchJobId = '', batchTimer = null;
function resetBatchPanel() {
  clearTimeout(batchTimer); batchTimer = null; batchJobId = ''; batchEntries = [];
  $('batchPanel').style.display = 'none'; $('batchProgress').style.display = 'none'; $('batchStart').style.display = '';
  $('batchList').replaceChildren(); $('batchFailed').replaceChildren();
}
function formatBatchDuration(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  return s ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` : '';
}
function updateBatchSelection() {
  const picked = [...document.querySelectorAll('#batchList input:checked')].length;
  $('batchStart').textContent = `下载所选（${picked}）`;
  $('batchStart').disabled = picked === 0;
}
async function openBatchPanel(url) {
  const r = await requestMusicDeskApi('/api/playlist', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url})});
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || '读取播放列表失败。');
  resetBatchPanel();
  batchEntries = data.entries;
  $('batchTitle').textContent = data.title || '播放列表';
  $('batchCount').textContent = `共 ${data.entries.length} 首，一次只下载一首，最后打包成一个 ZIP`;
  const list = $('batchList');
  data.entries.forEach((entry, index) => {
    const row = document.createElement('label'); row.className = 'batch-row';
    const box = document.createElement('input'); box.type = 'checkbox'; box.checked = true; box.dataset.index = String(index);
    box.addEventListener('change', updateBatchSelection);
    const name = document.createElement('span'); name.textContent = entry.artist ? `${entry.artist} - ${entry.title}` : entry.title;
    const time = document.createElement('small'); time.textContent = formatBatchDuration(entry.duration);
    row.append(box, name, time); list.append(row);
  });
  updateBatchSelection();
  $('batchPanel').style.display = 'flex';
}
async function startBatchDownload() {
  const tracks = [...document.querySelectorAll('#batchList input:checked')].map(box => batchEntries[Number(box.dataset.index)]);
  if (!tracks.length) return;
  const settings = getDownloadSettings();
  $('batchStart').disabled = true;
  try {
    const r = await requestMusicDeskApi('/api/batch', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({tracks, ...settings})});
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || '无法开始批量下载。');
    batchJobId = data.job_id;
    $('batchStart').style.display = 'none'; $('batchProgress').style.display = 'flex';
    $('batchCancel').disabled = false; $('batchFailed').replaceChildren();
    pollBatch();
  } catch (error) {
    $('lookupStatus').textContent = error.message; $('batchStart').disabled = false;
  }
}
async function pollBatch() {
  if (!batchJobId) return;
  try {
    const r = await requestMusicDeskApi(`/api/batch/${batchJobId}`);
    const s = await r.json();
    if (!r.ok) throw new Error(s.error || '批量任务状态读取失败。');
    const pct = s.total ? Math.round(s.done / s.total * 100) : 0;
    $('batchBar').style.width = `${pct}%`;
    const failedList = $('batchFailed'); failedList.replaceChildren();
    s.failed.forEach(item => { const li = document.createElement('li'); li.textContent = `${item.artist ? item.artist + ' - ' : ''}${item.title}：${item.error}`; failedList.append(li); });
    if (s.state === 'running' || s.state === 'queued') {
      $('batchStatus').textContent = `正在处理 ${s.done + 1} / ${s.total}：${s.current || ''}`;
      batchTimer = setTimeout(pollBatch, 1500); return;
    }
    $('batchCancel').disabled = true;
    if (s.state === 'cancelled') { $('batchStatus').textContent = `已取消，已完成 ${s.succeeded} 首。`; }
    else if (s.ready) {
      $('batchStatus').textContent = `完成：成功 ${s.succeeded} 首，失败 ${s.failed.length} 首。正在保存压缩包…`;
      const zip = await requestMusicDeskApi(`/api/batch/${batchJobId}/zip`);
      if (!zip.ok) throw new Error('压缩包下载失败。');
      await saveApiResponse(zip, 'MusicDesk-批量下载.zip');
      $('batchStatus').textContent = `完成：成功 ${s.succeeded} 首，失败 ${s.failed.length} 首。压缩包已保存。`;
    } else { $('batchStatus').textContent = '没有成功下载任何曲目。'; }
    batchJobId = '';
    $('batchStart').style.display = ''; $('batchStart').disabled = false;
  } catch (error) {
    $('batchStatus').textContent = error.message; batchJobId = ''; $('batchStart').style.display = ''; $('batchStart').disabled = false;
  }
}
$('batchAll').addEventListener('click', () => { document.querySelectorAll('#batchList input').forEach(b => { b.checked = true; }); updateBatchSelection(); });
$('batchNone').addEventListener('click', () => { document.querySelectorAll('#batchList input').forEach(b => { b.checked = false; }); updateBatchSelection(); });
$('batchStart').addEventListener('click', startBatchDownload);
$('batchCancel').addEventListener('click', async () => {
  if (!batchJobId) return;
  $('batchCancel').disabled = true;
  try { await requestMusicDeskApi(`/api/batch/${batchJobId}/cancel`, {method: 'POST'}); } catch (_) {}
});

// ===== Other matches for a keyword search =====
let pendingCandidate = null;   // set while re-running a search for a chosen candidate
let lastCandidates = [];
let candidateSearchId = 0;
function formatDuration(seconds) {
  if (!seconds) return '';
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}
function renderCandidates(selectedId) {
  const panel = $('candidatesPanel'), list = $('candidatesList');
  list.replaceChildren();
  if (lastCandidates.length < 2) { panel.hidden = true; return; }
  lastCandidates.forEach(candidate => {
    const row = document.createElement('button');
    row.type = 'button'; row.className = 'cand-row'; row.setAttribute('role', 'listitem');
    row.setAttribute('aria-current', String(candidate.id === selectedId));
    const name = document.createElement('span');
    name.textContent = candidate.title + (candidate.disambiguation ? ` (${candidate.disambiguation})` : '');
    const detail = document.createElement('small');
    detail.textContent = [candidate.artist, candidate.album, candidate.year, formatDuration(candidate.duration)].filter(Boolean).join(' · ');
    row.append(name, detail);
    row.addEventListener('click', () => pickCandidate(candidate));
    list.appendChild(row);
  });
  $('candidatesSummary').textContent = `其他匹配结果（${lastCandidates.length}）`;
  panel.hidden = false;
}
function pickCandidate(candidate) {
  pendingCandidate = candidate;
  $('share').value = candidate.artist ? `${candidate.artist} - ${candidate.title}` : candidate.title;
  $('lookup').requestSubmit();
}
// Best effort: the main result is already on screen, so a failure here just hides the list.
async function loadCandidates(query) {
  const requestId = ++candidateSearchId;
  $('candidatesPanel').hidden = true;
  try {
    let candidates;
    if (shouldProcessOnAndroid()) candidates = await fetchCandidatesOnAndroid(query);
    else {
      const r = await requestMusicDeskApi('/api/search_candidates', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({query}),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || '');
      candidates = data.candidates || [];
    }
    if (requestId !== candidateSearchId) return;
    lastCandidates = candidates;
    const current = currentMetadata || {};
    const best = candidates.find(c => c.title === current.title && (!current.artist || c.artist === current.artist)) || null;
    renderCandidates(best ? best.id : '');
  } catch (_) {
    if (requestId === candidateSearchId) $('candidatesPanel').hidden = true;
  }
}

$('lookup').addEventListener('submit', async e => {   e.preventDefault();$('lookupBtn').disabled = true;
  const lookupValue = $('share').value.trim();
  if (PLAYLIST_URL_RE.test(lookupValue)) {
    $('result').style.display = 'none';
    if (window.AndroidMusic) { resetBatchPanel(); $('lookupStatus').textContent = '批量下载暂时只支持电脑网页端。'; $('lookupBtn').disabled = false; return; }
    $('lookupStatus').textContent = '正在读取播放列表…';
    try { await openBatchPanel(lookupValue); $('lookupStatus').textContent = ''; }
    catch (error) { $('lookupStatus').textContent = friendlyMessage ? friendlyMessage(error.message) : error.message; }
    $('lookupBtn').disabled = false; return;
  }
  resetBatchPanel();
  const isKeywordSearch = !/^https?:\/\//i.test(lookupValue);
  const chosen = pendingCandidate; pendingCandidate = null;
  if (!isKeywordSearch) { candidateSearchId++; $('candidatesPanel').hidden = true; }
  $('lookupStatus').textContent = '正在读取…';
  $('sourceStatus').textContent = '';$('result').style.display = 'none';
  $('lyricsViewer').style.display = 'none';$('playerBox').style.display = 'none';
  $('youtubePreviewPanel').style.display = 'none';$('youtubePreviewFrame').replaceChildren();$('youtubePreviewFrame').style.display = 'none';

  try {
    if (shouldProcessOnAndroid() && isKeywordSearch) {
      if (/^spotify:/i.test(lookupValue)) throw new Error('Spotify 曲目信息需要连接电脑服务；手机可直接搜索 MusicBrainz。');
      const searchResult = await searchAndroidKeywordWithFallback(lookupValue);
      const d = searchResult.metadata;
      const usedMusicBrainz = searchResult.provider === 'MusicBrainz';
      currentMetadata = {...d, provider: searchResult.provider, keyword_search: true};
      const cover = usedMusicBrainz ? await resolveAndroidCover(currentMetadata) : d.thumbnail || '';
      $('title').textContent = d.title;
      $('artist').textContent = d.artist;
      $('provider').textContent = usedMusicBrainz ? '手机直连 MusicBrainz' : '手机 yt-dlp 备用搜索';
      $('cover').src = cover || DEFAULT_COVER;
      $('result').style.display = 'flex';
      updateYouTubePreview();
      $('lookupStatus').textContent = usedMusicBrainz
        ? 'MusicBrainz 曲目信息已载入，可继续检索歌词或下载。'
        : 'MusicBrainz 没有匹配结果，已自动改用手机 yt-dlp 搜索。';
      finishKeywordSearch(lookupValue, chosen);
      return;
    }
    if (shouldProcessOnAndroid()) {
      if (/spotify\.com\//i.test(lookupValue)) throw new Error('Spotify 曲目信息需要连接电脑服务；手机可直接搜索 MusicBrainz。');
      const source = isKeywordSearch ? `ytsearch1:${lookupValue}` : lookupValue;
      const d = await lookupWithAndroidYtDlp(source);
      currentMetadata = {...d, provider: 'yt-dlp', keyword_search: isKeywordSearch};
      $('title').textContent = d.title;
      $('artist').textContent = d.artist;
      $('provider').textContent = isKeywordSearch ? '手机 yt-dlp 搜索' : '手机 yt-dlp';
      $('cover').src = d.thumbnail || DEFAULT_COVER;
      $('result').style.display = 'flex';
      updateYouTubePreview();
      $('lookupStatus').textContent = '已由手机 yt-dlp 读取曲目信息，可直接下载音频。';
      return;
    }
    const r = await requestMusicDeskApi(isKeywordSearch ? '/api/search_metadata' : '/api/metadata', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(isKeywordSearch ? {query: lookupValue, album: chosen ? chosen.album : ''} : {url: lookupValue})
    });
    const d = await r.json();
    if(!r.ok) throw Error(d.error || '读取失败');

    currentMetadata = isKeywordSearch ? {...d, provider: d.provider || 'MusicBrainz 关键词搜索', keyword_search: true} : d;
    $('title').textContent = d.title;
    $('artist').textContent = d.artist;
    $('provider').textContent = isKeywordSearch
      ? (d.provider === 'yt-dlp' ? 'yt-dlp 备用搜索' : 'MusicBrainz 关键词搜索')
      : (d.provider === 'spotify' ? 'Spotify' : 'YouTube Music / YouTube');
    $('cover').src = isKeywordSearch ? (d.cover || d.thumbnail || DEFAULT_COVER) : (d.thumbnail || DEFAULT_COVER);
    $('result').style.display = 'flex';
    updateYouTubePreview();
    if (isKeywordSearch) finishKeywordSearch(lookupValue, chosen);
    $('lookupStatus').textContent = isKeywordSearch
      ? (d.provider === 'yt-dlp' ? 'MusicBrainz 没有匹配结果，已自动改用 yt-dlp 搜索；下载将使用该结果链接。' : '搜索完成，可继续查看歌词或下载。')
      : '信息已读取。';
  } catch(err) {
    $('lookupStatus').textContent = friendlyMessage(err);
  } finally {
    $('lookupBtn').disabled = false;
  }
});

// After a keyword search: honour a picked candidate's album/year, and list the other matches.
function finishKeywordSearch(query, chosen) {
  if (chosen) {
    if (chosen.album) currentMetadata.album = chosen.album;
    if (chosen.year) currentMetadata.year = chosen.year;
    renderCandidates(chosen.id);
    return;
  }
  loadCandidates(query);
}

$('viewLrcBtn').addEventListener('click', async () => {
  if (!currentMetadata) return;
  const viewer = $('lyricsViewer');
  if (viewer.style.display === 'block') { viewer.style.display = 'none'; return; }
  viewer.style.display = 'block';
  $('lrcContainer').innerHTML = `<span class="ui-text">${escapeHTML(ui('正在检索并载入 LRC 歌词…'))}</span>`;
  try {
    if (shouldProcessOnAndroid()) {
      const result = await lookupLyricsOnAndroid(currentMetadata.title, currentMetadata.artist);
      renderLyricsView(result.lyrics || '');
      return;
    }
    const r = await requestMusicDeskApi('/api/lyrics_text', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      // Lyrics lookup only needs these fields. Keyword metadata may include a
      // base64-encoded cover, which can exceed the server's small JSON limit.
      body: JSON.stringify({title: currentMetadata.title, artist: currentMetadata.artist})
    });
    const d = await r.json();
    if (!r.ok) throw Error(d.error || '未检索到歌词');
    renderLyricsView(d.lyrics || '');
  } catch (err) {
    $('lrcContainer').innerHTML = `<div class="ui-text" style="color:var(--muted);text-align:center;padding-top:80px">${escapeHTML(ui(friendlyMessage(err)))}${/没有找到.*歌词/.test(err.message || '') ? '<br><small>' + escapeHTML(ui('可以在“编辑”里手动粘贴歌词。')) + '</small>' : ''}</div>`;
  }
});

$('downloadBtn').addEventListener('click', async () => {
  if (!currentMetadata) return;
  $('downloadBtn').disabled = true;
  const preferredEngine = $('enginePriority').value;
  const useAndroidYtDlp = shouldProcessOnAndroid() && preferredEngine === 'ytdlp';
  const downloadSettings = getDownloadSettings();
  const needsDesktopProcessing = downloadSettings.format !== 'mp3' || downloadSettings.bitrate !== '192' || downloadSettings.download_lrc;
  $('lookupStatus').textContent = useAndroidYtDlp
    ? '正在使用手机内置 yt-dlp 下载并转换为 MP3…'
    : `正在按优先级 (${preferredEngine}) 下载音频并自动内嵌 LRC 歌词，请稍候...`;
  $('sourceStatus').textContent = '';

  try {
    if (useAndroidYtDlp && needsDesktopProcessing) {
      throw Error('所选格式、比特率或独立 LRC 下载需要连接电脑服务。请在设置中心连接电脑后重试。');
    }
    if (useAndroidYtDlp) {
      const source = androidDownloadSource(currentMetadata);
      // Lyrics are looked up after the download, against the audio's own title and length,
      // so a translated catalog title (e.g. "Idol" for アイドル) cannot pull the lyrics of a
      // different-language version of the song.
      const downloadMetadata = {...currentMetadata, lookup_lyrics: true};
      const result = await downloadWithAndroidYtDlp(source, downloadMetadata);
      const lyricStatus = androidLyricsStatusText(result.lyricsStatus);
      $('lookupStatus').textContent = `本机下载完成，已保存音频：${result.filename}；${lyricStatus}${result.warning ? `；${result.warning}` : ''}`;
      $('sourceStatus').textContent = '本机 yt-dlp 下载后会转换为 MP3，并写入可用的曲目信息与封面标签。';
      return;
    }
    const payload = { ...currentMetadata, ...downloadSettings, preferred_engine: preferredEngine };
    const r = await requestMusicDeskApi('/api/download', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    if(!r.ok) {
      const d = await r.json();
      throw Error(d.error || '下载失败');
    }

    const rawSourceUrl = r.headers.get('X-Source-Url');
    const lrcStatus = downloadSettings.download_lrc && r.headers.get('X-Lyrics-Sidecar') === 'missing' ? '压缩包里没有 LRC，因为未找到这首歌的歌词。' : '';
    let sourceUrl = '';
    try {
      const parsedSource = new URL(rawSourceUrl);
      if (['http:', 'https:'].includes(parsedSource.protocol)) sourceUrl = parsedSource.href;
    } catch (_) {}
    if (window.AndroidMusic) {
      const filename = await saveApiResponse(r, `${currentMetadata.artist} - ${currentMetadata.title}.${downloadSettings.download_lrc ? 'zip' : downloadSettings.format}`);
      $('lookupStatus').textContent = `下载完成，已保存到你选择的位置：${filename}${lrcStatus ? `；${lrcStatus}` : ''}`;
    } else if (!downloadSettings.download_lrc) {
      const blob = await r.blob();
      const audioUrl = URL.createObjectURL(blob);
      const player = $('audioPlayer');
      player.src = audioUrl;
      $('playerBox').style.display = 'block';
      const a = document.createElement('a');
      a.href = audioUrl;
      a.download = responseFilename(r, `${currentMetadata.title}.${downloadSettings.download_lrc ? 'zip' : downloadSettings.format}`);
      a.click();
      $('lookupStatus').textContent = `下载完成！已自动装载至线上播放器试听。${lrcStatus ? ` ${lrcStatus}` : ''}`;
    } else {
      const blob = await r.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = responseFilename(r, `${currentMetadata.title}.zip`);
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      $('lookupStatus').textContent = `下载完成！音频与 LRC 已打包为 ZIP。${lrcStatus ? ` ${lrcStatus}` : ''}`;
    }
    if (sourceUrl) {
      $('sourceStatus').innerHTML = `音频抓取来源: <a href="${sourceUrl}" target="_blank" rel="noopener">${sourceUrl}</a>`;
    }
  } catch(err) {
    $('lookupStatus').textContent = friendlyMessage(err);
  } finally {
    $('downloadBtn').disabled = false;
  }
});


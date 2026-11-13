// Settings, Android desktop pairing, and first-run guidance.
let androidApiConfig = null;
let androidApiConnected = false;
const REQUIRED_ANDROID_API_VERSION = 1;
const REQUIRED_ANDROID_API_CAPABILITIES = ['metadata', 'search_metadata', 'lyrics_text', 'download', 'convert', 'parse_local_tag', 'package_custom_tag'];
try { androidApiConfig = JSON.parse(localStorage.getItem('musicdesk-api-config') || 'null'); } catch (_) {}
function normalizedApiConfig(url, token) {
  const parsed = new URL(url.trim());
  if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password || parsed.search || parsed.hash || (parsed.pathname !== '/' && parsed.pathname !== '')) {
    throw new Error('请输入电脑终端显示的 http://IP:端口 地址。');
  }
  const cleanToken = token.trim();
  if (cleanToken.length < 24) throw new Error('配对密钥格式不正确，请从电脑终端完整复制。');
  return {url: parsed.origin.replace(/\/$/, ''), token: cleanToken};
}

function updateStatusChip(connected) {
  const chip = $('statusChip'), text = $('statusChipText');
  if (!chip || !text) return;
  if (!window.AndroidMusic) { text.textContent = '本机运行'; chip.classList.remove('local'); return; }
  text.textContent = connected ? '已连接电脑' : '本机处理';
  chip.classList.toggle('local', !connected);
}
function updateApiConnectionMessage(connected, message = '') {
  updateStatusChip(connected);
  androidApiConnected = !!connected;
  updateAndroidApiGates();
  const saved = !!androidApiConfig;
  const badge = $('apiStateBadge');
  badge.textContent = connected ? '已连接' : saved ? '已保存，未验证' : '未连接';
  badge.classList.toggle('on', !!connected);
  $('apiConnectionStatus').textContent = message || (connected ? `已连接：${androidApiConfig.url}` : saved ? `已保存：${androidApiConfig.url}（点按钮测试连接）` : '尚未连接');
  $('androidOnlineNote').textContent = connected
    ? `已连接电脑服务：${androidApiConfig.url}。解析、歌词、下载、转换和封装任务由电脑处理，结果回传到手机。`
    : saved ? `已保存电脑地址 ${androidApiConfig.url}；验证连接后，相关任务将由电脑处理。当前使用手机本机能力。` : '当前使用手机本机能力；连接电脑 API 后，相关任务将交给电脑处理并回传结果。';
  $('androidCustomNote').firstChild.textContent = connected
    ? '已连接电脑：封装与格式转换会在电脑完成后回传；所选音频将通过配对的局域网连接发送到电脑。'
    : '未连接电脑：选择本地音频后，可在手机本机编辑标签、裁剪、转换格式并封装导出。';
}

function updateAndroidApiGates() {
  if (!window.AndroidMusic) return;
  document.querySelectorAll('#lookup input, #lookup button').forEach(control => { control.disabled = false; });
  $('enginePriority').disabled = !androidApiConnected;
  $('viewLrcBtn').disabled = false;
  $('downloadBtn').disabled = false;
  if (!androidApiConnected) $('enginePriority').value = 'ytdlp';
  updateAndroidDownloadButtonLabel();
  updateDownloadSettingsSummary();
  // Android handles conversion and custom tagging natively. Only the optional
  // remote metadata search and SpotDL source require a verified desktop API.
  document.querySelectorAll('#convert input, #convert select, #convert button')
    .forEach(control => { control.disabled = false; });
  $('tagSearchBtn').disabled = !androidApiConnected;
  $('customEngine').disabled = !androidApiConnected;
}

function updateAndroidDownloadButtonLabel() {
  if (!window.AndroidMusic) return;
  const settings = getDownloadSettings();
  const advanced = settings.format !== 'mp3' || settings.bitrate !== '192' || settings.download_lrc;
  $('downloadBtn').textContent = $('enginePriority').value === 'ytdlp' && !androidApiConnected
    ? (advanced ? '连接电脑以处理设置' : '下载音频（本机）')
    : `下载 ${settings.format.toUpperCase()}${settings.download_lrc ? ' + LRC' : ''}`;
}

async function testAndroidApiConnection(config, showProgress = true) {
  if (showProgress) updateApiConnectionMessage(false, '正在测试电脑服务…');
  try {
    const response = await fetch(`${config.url}/api/status`, {headers: {Authorization: `Bearer ${config.token}`}});
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || '电脑服务拒绝了连接。');
    if (result.service !== 'MusicDesk' || result.api_version !== REQUIRED_ANDROID_API_VERSION ||
        !REQUIRED_ANDROID_API_CAPABILITIES.every(capability => result.capabilities && result.capabilities.includes(capability))) {
      throw new Error('电脑端 API 版本或功能不匹配；请更新电脑端 MusicDesk 后再连接。功能已保持锁定。');
    }
    androidApiConfig = config;
    localStorage.setItem('musicdesk-api-config', JSON.stringify(config));
    $('apiPairingToken').value = config.token;
    updateApiConnectionMessage(true);
    return true;
  } catch (error) {
    updateApiConnectionMessage(false, /Failed to fetch|NetworkError|Load failed/i.test(error.message)
      ? '电脑服务未连通，在线功能已锁定：检查同一 Wi‑Fi、电脑 LAN 地址/端口、配对码及防火墙。'
      : error.message);
    return false;
  }
}


function refreshAndroidSettingsFolders() {
  if (!window.AndroidMusic) return;
  let folders = [];
  try { folders = JSON.parse(AndroidMusic.getSavedFolders() || '[]'); } catch (_) {}
  const container = $('androidSettingsFolders');
  if (!folders.length) {
    container.innerHTML = '<p class="status">尚未授权音乐文件夹。添加文件夹后，应用会在下次打开时恢复曲库。</p>';
    return;
  }
  container.innerHTML = folders.map((folder, index) => `<div class="settings-row"><div><strong>${escapeHTML(folder.name || '音乐文件夹')}</strong><div class="settings-about">${folder.authorized ? '已授权 · 可在启动时恢复' : '授权已失效 · 需要重新选择'}</div></div><div class="settings-folder-actions"><button type="button" class="settings-rescan-btn" data-index="${index}">${folder.authorized ? '重新扫描' : '重新授权'}</button><button type="button" class="settings-remove-folder-btn lrc-btn" data-index="${index}">移除</button></div></div>`).join('');
  container.querySelectorAll('.settings-rescan-btn').forEach(button => button.addEventListener('click', () => {
    const folder = folders[Number(button.dataset.index)];
    if (!folder.authorized) { AndroidMusic.pickFolder(); return; }
    const started = AndroidMusic.rescanSavedFolder(folder.uri) === 'true';
    button.textContent = started ? '正在扫描…' : '请重新授权';
    if (!started) refreshAndroidSettingsFolders();
  }));
  container.querySelectorAll('.settings-remove-folder-btn').forEach(button => button.addEventListener('click', () => {
    const folder = folders[Number(button.dataset.index)];
    if (AndroidMusic.removeSavedFolder(folder.uri) === 'true') refreshAndroidSettingsFolders();
  }));
}

function refreshAndroidPermissionStatus() {
  if (!window.AndroidMusic) return;
  $('notificationPermissionStatus').textContent = AndroidMusic.hasNotificationPermission() === 'true'
    ? '已允许通知；锁屏播放控制由 Android 系统管理。'
    : '通知已关闭；播放时可能看不到锁屏/通知栏控制。';
}

function refreshAndroidSettings() {
  if (!window.AndroidMusic) return;
  $('appVersionLabel').textContent = `当前版本：${AndroidMusic.getAppVersion()}`;
  refreshAndroidSettingsFolders();
  refreshAndroidPermissionStatus();
}
window.refreshAndroidSettings = refreshAndroidSettings;

function compareVersionStrings(left, right) {
  const parse = value => String(value || '').replace(/^[^\d]*/, '').split(/[.+-]/).map(part => parseInt(part, 10)).filter(Number.isFinite);
  const a = parse(left), b = parse(right);
  if (!a.length || !b.length) return null;
  for (let index = 0; index < Math.max(a.length, b.length); index++) {
    const difference = (a[index] || 0) - (b[index] || 0);
    if (difference) return difference;
  }
  return 0;
}

window.onAndroidUpdateCheck = raw => {
  let result;
  try { result = JSON.parse(raw); } catch (_) { result = null; }
  if (!result || !result.ok) {
    $('updateStatus').textContent = `检查失败：${result && result.error || '无法读取 GitHub Release'}`;
    return;
  }
  $('appVersionLabel').textContent = `当前版本：${result.current}`;
  const comparison = compareVersionStrings(result.latest, result.current);
  $('updateStatus').textContent = comparison === null
    ? `GitHub 最新版本：${result.latest || '未知'}。请打开发布页确认是否适用于 Android。`
    : comparison > 0 ? `发现新版本 ${result.latest}。请在发布页确认 Android 安装包后手动下载并安装。`
      : `当前版本已是最新版本：${result.current}`;
  $('openReleaseBtn').hidden = !result.url || comparison === 0;
  $('openReleaseBtn').dataset.url = result.url || '';
};

/* ===== First-run guide ===== */
const GUIDE_KEY = 'musicdesk-guide-done';
const GUIDE_STEPS = [
  { title: '下载', body: '粘贴链接或搜索歌名，选好格式后下载。', bodyPhone: '粘贴链接或搜索歌名即可下载 MP3；其他格式需要连接电脑。', tab: 'online' },
  { title: '编辑', body: '补全标题、歌手、封面和歌词。常用项在前，其余收在“更多信息”里。', tab: 'custom' },
  { title: '播放', body: '用“添加”导入歌曲或文件夹，离线播放、收藏和排队。', tab: 'local' },
];
let guideIndex = 0;
function guideSeen() { try { return localStorage.getItem(GUIDE_KEY) === '1'; } catch (_) { return true; } }
function renderGuide() {
  const step = GUIDE_STEPS[guideIndex];
  const phone = !!window.AndroidMusic && !androidApiConnected;
  $('guideStep').textContent = (guideIndex + 1) + ' / ' + GUIDE_STEPS.length;
  $('guideTitle').textContent = step.title;
  $('guideBody').textContent = phone && step.bodyPhone ? step.bodyPhone : step.body;
  $('guideNext').textContent = guideIndex === GUIDE_STEPS.length - 1 ? '开始使用' : '下一步';
  document.querySelectorAll('.guide-dots i').forEach((dot, i) => dot.classList.toggle('on', i === guideIndex));
  switchTab(step.tab);
}
function openGuide() {
  guideIndex = 0;
  $('guideBackdrop').hidden = false;
  renderGuide();
  $('guideNext').focus();
  if (window.AndroidMusic) AndroidMusic.setQueueOpen(true);
}
function closeGuide() {
  if ($('guideBackdrop').hidden) return;
  $('guideBackdrop').hidden = true;
  try { localStorage.setItem(GUIDE_KEY, '1'); } catch (_) {}
  switchTab('online');
  if (window.AndroidMusic) AndroidMusic.setQueueOpen(false);
}

let settingsInitialized = false;
function initSettings() {
  if (settingsInitialized) return;
  settingsInitialized = true;
  $('enginePriority').addEventListener('change', updateAndroidDownloadButtonLabel);
  $('connectApiBtn').addEventListener('click', async () => {
    let config;
    try { config = normalizedApiConfig($('apiServerUrl').value, $('apiPairingToken').value); }
    catch (error) { updateApiConnectionMessage(false, error.message); return; }
    $('connectApiBtn').disabled = true;
    await testAndroidApiConnection(config);
    $('connectApiBtn').disabled = false;
  });

  $('forgetApiBtn').addEventListener('click', () => {
    androidApiConfig = null;
    androidApiConnected = false;
    localStorage.removeItem('musicdesk-api-config');
    $('apiPairingToken').value = '';
    updateApiConnectionMessage(false, '已断开电脑服务。');
  });

  $('androidOpenApiSettings').addEventListener('click', () => {
    switchTab('settings');
    $('androidApiConnectCard').scrollIntoView({behavior: 'smooth', block: 'start'});
  });
  $('addAndroidFolderBtn').addEventListener('click', () => { if (window.AndroidMusic) AndroidMusic.pickFolder(); });
  $('manageNotificationBtn').addEventListener('click', () => { if (window.AndroidMusic) AndroidMusic.openNotificationSettings(); });
  $('manageAppPermissionsBtn').addEventListener('click', () => { if (window.AndroidMusic) AndroidMusic.openAppSettings(); });
  $('checkUpdatesBtn').addEventListener('click', () => {
    if (!window.AndroidMusic) return;
    $('updateStatus').textContent = '正在检查 GitHub Release…';
    $('openReleaseBtn').hidden = true;
    AndroidMusic.checkForUpdates();
  });
  $('openReleaseBtn').addEventListener('click', () => {
    const url = $('openReleaseBtn').dataset.url;
    if (url && window.AndroidMusic) AndroidMusic.openReleasePage(url);
  });
  $('openSettingsHelpBtn').addEventListener('click', () => $('helpDialog').showModal());
  $('guideNext').addEventListener('click', () => {
    if (guideIndex >= GUIDE_STEPS.length - 1) { closeGuide(); return; }
    guideIndex += 1; renderGuide();
  });
  $('guideSkip').addEventListener('click', closeGuide);
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !$('guideBackdrop').hidden) closeGuide(); });
  window.addEventListener('load', () => {
    const forced = /[?&]guide=1\b/.test(location.search);
    if (forced || (!guideSeen() && !navigator.webdriver)) setTimeout(openGuide, 400);
  });
  // ---- Bilingual lyrics: settings toggle and editor merge ----
  $('bilingualLyricsToggle').checked = bilingualLyrics;
  $('bilingualLyricsToggle').addEventListener('change', () => {
    bilingualLyrics = $('bilingualLyricsToggle').checked;
    try { localStorage.setItem('musicdesk-bilingual-lyrics', bilingualLyrics ? '1' : '0'); } catch (_) {}
    if (parsedLyrics.length) renderLyricsView(lastOnlineLrcText);
    if (parsedLocalLyrics.length) renderLocalLyrics(lastLocalLrcText);
  });
  $('mergeTranslationBtn').addEventListener('click', () => {
    const status = $('mergeTranslationStatus');
    const result = mergeTranslationIntoLyrics($('tagLyrics').value, $('tagTranslation').value);
    if (!result.timed) { status.textContent = '请先在上面填入带时间戳的 LRC 歌词。'; return; }
    if (!result.translations) { status.textContent = '请先填入译文。'; return; }
    $('tagLyrics').value = result.text;
    $('tagLyrics').dispatchEvent(new Event('input', {bubbles: true}));
    $('tagTranslation').value = '';
    status.textContent = result.translations === result.timed
      ? `已合并 ${result.used} 行译文。`
      : `已合并 ${result.used} 行译文（歌词 ${result.timed} 行，译文 ${result.translations} 行，数量不一致，请检查对应关系）。`;
  });
}

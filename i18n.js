(() => {
  'use strict';

  const translations = {
    '在线解析与下载': 'Online Search & Download',
    '自定义封装与标签编辑': 'Custom Packaging & Tag Editor',
    '本地离线播放器': 'Offline Music Player',
    '在线解析': 'Online', '自定义': 'Custom', '曲库': 'Library',
    '选择语言': 'Language', '帮助与快捷键': 'Help & Shortcuts',
    'MusicDesk 使用帮助': 'MusicDesk Help', '关闭帮助': 'Close help', '关闭': 'Close',
    '关闭帮助': 'Close help', '在线解析与下载': 'Online Search & Download',
    '粘贴 Spotify、YouTube 分享链接或输入歌曲关键词，读取公开曲目信息、查看歌词、下载音频；也可将本地音频转换为其他格式。': 'Paste a Spotify or YouTube link, or search by song keywords to view public track details and lyrics or download audio. You can also convert local audio.',
    '自定义封装': 'Custom Packaging',
    '选择本地音频后可试听、裁剪头尾、修改曲目信息和封面；同步歌词可逐句校时，纯文本歌词可制作时间戳并生成 LRC。': 'Preview and trim local audio, edit track details and cover art, calibrate synced lyrics line by line, or add timestamps to plain lyrics and create an LRC file.',
    '选择歌曲或文件夹建立曲库，浏览标签、专辑封面和歌词；支持队列、收藏、播放模式与上次播放状态恢复。': 'Choose songs or a folder to build your library. Browse tags, covers, and lyrics, manage the queue and favorites, and restore the last playback state.',
    '键盘快捷键': 'Keyboard shortcuts',
    '或': 'or', '：播放 / 暂停当前页面的音频。': ': Play or pause audio on the current page.',
    '：后退 / 前进 5 秒。': ': Seek backward or forward 5 seconds.',
    '：纯文本逐句打点模式下，标记当前句并前进。': ': In plain lyric timing mode, timestamp the current line and advance.',
    '：将选中的 LRC 歌词时间设为当前播放位置。': ': Set the selected LRC line to the current playback position.',
    '输入框、歌词文本框和进度滑杆获得焦点时，快捷键不会拦截输入或滑杆操作。打点使用 M，播放暂停使用 Space / K，二者互不冲突。': 'Shortcuts are disabled while typing in fields or using the seek bar. Use M to timestamp lyrics and Space or K to play or pause.',
    '播放全部': 'Play all', '选择播放顺序': 'Choose playback order', '顺序播放': 'Play in order', '随机播放': 'Shuffle order',
    '本地曲库，随时畅听。': 'Your music library, ready to play.',
    '选择电脑中的音乐文件夹，直接解析本地 ID3 标签、专辑原画与内嵌 LRC 歌词。': 'Choose a music folder to read local ID3 tags, album artwork, and embedded LRC lyrics.',
    '本地播放列表': 'Local playlist', '选择文件夹': 'Choose folder', '选择歌曲': 'Choose songs',
    '搜索本地歌曲名/歌手...': 'Search local songs or artists...', '拖入一首或多首音乐到此处添加': 'Drop one or more audio files here to add them',
    '播放全部': 'Play all', '首': ' tracks', '歌曲': 'Songs', '歌手': 'Artists', '专辑': 'Albums', '文件夹': 'Folders', '收藏': 'Favorites',
    '正在播放': 'Now Playing', '歌词': 'Lyrics', '未选择歌曲': 'No track selected', '本地音乐离线播放器': 'Offline music player',
    '暂无内嵌 LRC 歌词': 'No embedded LRC lyrics', '歌词准备就绪': 'Lyrics are ready', '清空': 'Clear queue', '移除': 'Remove',
    '上一首': 'Previous track', '下一首': 'Next track', '播放': 'Play', '暂停': 'Pause',
    '顺序播放': 'In order', '随机播放': 'Shuffle',
    '曲目信息搜索': 'Track Information Search', '粘贴 Spotify / YouTube 分享链接，或搜索“作者 - 标题”及单独标题': 'Paste a Spotify or YouTube link, or search “Artist - Title” or a title',
    '分享链接或关键词': 'Link or keywords', '读取 / 搜索曲目信息': 'Read / Search Track Details',
    '下载 MP3': 'Download MP3', '歌词阅读器': 'Lyrics Reader', '搜索完成，可继续查看歌词或下载。': 'Search complete. You can view lyrics or download audio.',
    '所有歌曲': 'All Songs', '播放全部（': 'Play all (', '首）': ' tracks)',
    '转换本地音频': 'Convert Local Audio', '转换引擎由 MusicDesk 自动准备；选择你拥有或有权处理的音频文件': 'MusicDesk prepares the conversion engine. Choose audio you own or are authorized to process.',
    '选择音频文件': 'Choose audio files', '导出格式': 'Output format', '保存并打包导出文件': 'Save and Export',
    '专辑封面预览': 'Album Cover Preview', '上传/更换封面': 'Upload / Change Cover',
    '歌曲标题 (Title)': 'Track Title', '歌手/作者 (Artist)': 'Artist', '专辑名称 (Album)': 'Album', '专辑歌手 (Album Artist)': 'Album Artist', '发行年份 (Year)': 'Year',
    '内嵌歌词 (LRC/Plain Lyrics)': 'Embedded Lyrics (LRC / Plain Text)', '允许追加文件名': 'Append text to filename',
    '关闭时使用“作者 - 标题”格式；开启后会把内容追加到文件名末尾。': 'When disabled, filenames use “Artist - Title”. When enabled, the text is appended to the filename.',
    '第一步：点击选择或将音乐文件拖到这里': 'Step 1: Choose or drop audio files here',
    '先点选一行歌词，再设置播放时间': 'Select a lyric line, then set its timestamp', '全部提前 0.5 秒': 'Move all earlier by 0.5 s', '全部延后 0.5 秒': 'Move all later by 0.5 s',
    '这段歌词没有时间戳。可以试听音频；校时工具需要 LRC 时间戳。': 'These lyrics have no timestamps. Preview the audio; calibration requires LRC timestamps.',
    '播放 / 暂停': 'Play / Pause', '标记当前歌词并前进': 'Timestamp current line and advance', '撤销上次标记': 'Undo last timestamp', '完成并生成 LRC': 'Finish and generate LRC',
    '音乐文件夹': 'Music folder', '尚未加载本地音乐': 'No local music loaded', '点击右上角“选择文件夹”': 'Choose a folder above to get started',
    'MusicDesk · 在本机运行，上传的文件不会发送到外部服务。': 'MusicDesk · Runs locally. Uploaded files are not sent to external services.',
    '曲库已就绪': 'Library ready', '正在扫描文件夹中的音频...': 'Scanning audio files in folder...', '正在播放本地歌曲': 'Playing local music',
    '搜索并填入': 'Search and Fill', '联网补全曲目信息（作者 - 标题，或只输入标题）': 'Look up track details online (Artist - Title, or title only)',
    '歌名': 'Title', '作者': 'Artist', '专辑': 'Album', '播放列表': 'Queue', '队列': 'Queue',
    '下一页': 'Next', '上一页': 'Previous', '暂无歌词': 'No lyrics available', '未检索到同步 LRC 歌词': 'No synced LRC lyrics found',
    '收藏歌曲': 'Add to favorites', '取消收藏': 'Remove from favorites', '选择歌曲或文件夹': 'Choose songs or a folder',
    '音频预览': 'Audio Preview', '裁剪音频': 'Trim Audio', '开始时间': 'Start time', '结束时间': 'End time',
    '歌词时间校准': 'Lyric Timing', '纯文本逐句打点': 'Timestamp Plain Lyrics', '选中歌词后按 T 校准时间': 'Select a lyric and press T to set its time',
    '按 M 标记当前句并自动前进': 'Press M to timestamp this line and advance', '按 Space 或 K 播放/暂停': 'Press Space or K to play or pause',
    'MusicDesk · 音乐资料与格式转换': 'MusicDesk · Music Details & Audio Conversion',
    '从分享链接查看公开曲目信息，或把你拥有使用权的音频转换成常见格式。轻量、私密，文件在本机处理。': 'Look up public track details from a shared link or convert audio you are authorized to use. Lightweight and private; files stay on this device.',
    '会按上方曲名和作者搜索音源，再写入标签并导出 MP3 或所选格式。': 'Searches for audio using the title and artist above, writes the tags, and exports MP3 or your selected format.',
    '当无法自动抓包时，可上传本地音频自行补充与修正封面、标题、歌手、专辑及歌词元数据。': 'When automatic lookup is unavailable, upload local audio to add or correct its cover, title, artist, album, and lyrics.',
    '自定义封装使用已连接电脑上的 FFmpeg 与标签写入服务。': 'Custom packaging uses FFmpeg and the tag-writing service on the connected computer.',
    '连接同一 Wi‑Fi 上运行的 MusicDesk 电脑，即可使用在线服务。': 'Connect to a MusicDesk computer on the same Wi-Fi network to use online services.',
    '连接电脑上的 MusicDesk': 'Connect to MusicDesk on your computer', '连接电脑': 'Connect Computer', '先在电脑运行': 'Start MusicDesk on your computer first',
    '电脑服务地址': 'Computer server address', '一次性配对密钥': 'One-time pairing token', '测试并保存连接': 'Test and Save Connection', '尚未连接': 'Not connected', '断开': 'Disconnect',
    '首选：spotdl (完整元数据)': 'Preferred: spotdl (full metadata)', '首选：yt-dlp': 'Preferred: yt-dlp',
    '未选择本地音频时的下载工具': 'Download source when no local audio is selected', '转换并保存': 'Convert and Save',
    '导出格式 (Format)': 'Output Format', '定制标签。': 'Custom tags.', '音乐资料，': 'Music details, ', '由你整理。': 'organized your way.',
    '‹ 返回分类': '‹ Back to categories', '▶ 播放全部': '▶ Play all', '播放列表': 'Playlist', '清空': 'Clear', '标记当前句': 'Timestamp current line', '撤销上一条': 'Undo last timestamp',
    '试听会在终点暂停；拖动起点和终点可去掉头尾多余音频，导出时只保留选中片段。': 'Preview pauses at the end point. Move the handles to trim silence from either end; only the selected section is exported.',
    '选择音频并载入 LRC 歌词后，可试听并点选歌词校时。': 'Load audio and LRC lyrics to preview playback and calibrate selected lines.',
    '为纯文本逐句添加时间戳': 'Add timestamps to plain lyrics line by line', '音频试听与裁剪': 'Audio Preview & Trimming', '试听选中片段': 'Preview Selected Section',
    '裁剪起点': 'Trim start', '裁剪终点': 'Trim end', '设为当前播放位置': 'Set to current position', '将选中歌词设为当前播放时间': 'Set selected lyric to current playback time',
    '选择歌曲或导入文件夹，建立本地曲库。': 'Choose songs or import a folder to build your local library.',
    '点击右上角“选择文件夹”': 'Choose a folder above to get started', '歌词阅读器': 'Lyrics Reader', '正在加载歌词…': 'Loading lyrics…',
    '测试并保存连接': 'Test and Save Connection', '选择音频文件': 'Choose audio files', '文件夹': 'Folders', '在线播放': 'Online Playback',
    '首': 'tracks', '音乐文件夹': 'Music folder', '转换本地音频': 'Convert Local Audio',
    '0 首': '0 tracks', '▶ 播放全部': '▶ Play all', '一次性配对密钥': 'One-time pairing token',
    '专辑名称 (Album)': 'Album', '发行年份 (Year)': 'Year', '歌手/作者 (Artist)': 'Artist',
    '专辑歌手 (Album Artist)': 'Album Artist', '保存并打包导出文件': 'Save and Export', '允许追加文件名': 'Append text to filename',
    '关闭时使用“作者 - 标题.格式”；开启后会把内容追加到文件名末尾。': 'When disabled, filenames use “Artist - Title”. When enabled, the text is appended to the filename.',
    '先在电脑运行': 'Start MusicDesk on your computer first', '全部延后 0.5 秒': 'Move all later by 0.5 s', '全部提前 0.5 秒': 'Move all earlier by 0.5 s',
    '完成并生成 LRC': 'Finish and generate LRC', '定制标签。': 'Custom tags.', '导出格式': 'Output Format',
    '将选中歌词设为当前播放时间': 'Set selected lyric to current playback time', '尚未加载本地音乐': 'No local music loaded',
    '尚未连接': 'Not connected', '手动封装，': 'Package manually, ', '拖入一首或多首音乐到此处添加': 'Drop one or more audio files here to add them',
    '撤销上一条': 'Undo last timestamp', '曲库': 'Library', '未选择歌曲': 'No track selected', '本地曲库，': 'Your music library, ',
    '本地音乐离线播放器': 'Offline music player', '标记当前句': 'Timestamp current line', '歌手': 'Artists', '歌曲': 'Songs', '歌词': 'Lyrics',
    '歌词准备就绪': 'Lyrics are ready', '正在加载歌词…': 'Loading lyrics…', '清空': 'Clear queue', '由你整理。': 'organized your way.',
    '粘贴 Spotify / YouTube 分享链接，或搜索“作者 - 标题”及单独标题': 'Paste a Spotify or YouTube link, or search “Artist - Title” or a title',
    '联网补全曲目信息（作者 - 标题，或只输入标题）': 'Look up track details online (Artist - Title, or title only)',
    '裁剪终点': 'Trim end', '设为当前播放位置': 'Set to current position', '试听选中片段': 'Preview Selected Section',
    '读取 / 搜索曲目信息': 'Read / Search Track Details', '转换并保存': 'Convert and Save',
    '转换引擎由 MusicDesk 自动准备；选择你拥有或有权处理的音频文件': 'MusicDesk prepares the conversion engine. Choose audio you own or are authorized to process.',
    '连接电脑': 'Connect Computer', '选择播放顺序': 'Choose playback order', '随时畅听。': 'ready to play.',
    '随机播放': 'Shuffle order', '音乐资料，': 'Music details, ', '音频试听与裁剪': 'Audio Preview & Trimming',
    '首选：yt-dlp': 'Preferred: yt-dlp', '，再填入终端显示的地址和一次性配对密钥。手机与电脑需在同一 Wi‑Fi。': ', then enter the server address and one-time pairing token shown in the terminal. Your phone and computer must use the same Wi-Fi.',
    '：播放 / 暂停当前页面的音频。': ': Play or pause audio on this page.',
  };

  const reverse = new Map(Object.entries(translations).map(([zh, en]) => [en, zh]));
  const protectedSelectors = 'script,style,textarea,input,select,[contenteditable="true"],#lrcContainer,#localLrcContainer,#customLyricsPreview,.track-list,.queue-sheet,.result-info,#nowTitle,#nowArtist,#miniTitle,#miniArtist,#title,#artist';
  const mobileNames = {
    online: { zh: '在线解析与下载', en: 'Online' },
    custom: { zh: '自定义封装与标签编辑', en: 'Custom' },
    local: { zh: '本地离线播放器', en: 'Library' },
  };
  let language = 'zh';

  function lookup(value, lang) {
    const trimmed = value.trim();
    if (!trimmed) return value;
    const count = trimmed.match(/^(\d+)\s*(首|tracks?)$/i);
    if (count) return value.replace(trimmed, lang === 'en' ? `${count[1]} tracks` : `${count[1]} 首`);
    const translated = lang === 'en' ? translations[trimmed] : reverse.get(trimmed);
    return translated === undefined ? value : value.replace(trimmed, translated);
  }

  function translateTextNode(node) {
    const parent = node.parentElement;
    if (!parent || parent.closest(protectedSelectors)) return;
    const translated = lookup(node.nodeValue, language);
    if (translated !== node.nodeValue) node.nodeValue = translated;
  }

  function translateTree(root) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) {
      translateTextNode(root);
      return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE || root.matches(protectedSelectors)) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) translateTextNode(walker.currentNode);
    root.querySelectorAll('[placeholder],[title],[aria-label],[alt]').forEach(element => {
      if (element.matches(protectedSelectors)) return;
      for (const attribute of ['placeholder', 'title', 'aria-label', 'alt']) {
        const value = element.getAttribute(attribute);
        if (value) element.setAttribute(attribute, lookup(value, language));
      }
    });
  }

  function updateMobileTabLabel(tabName) {
    const label = document.getElementById('mobileTabLabel');
    if (label) label.textContent = mobileNames[tabName]?.[language] || mobileNames.online[language];
  }
  window.updateMobileTabLabel = updateMobileTabLabel;

  function applyLanguage(nextLanguage) {
    language = nextLanguage === 'en' ? 'en' : 'zh';
    document.documentElement.lang = language === 'en' ? 'en' : 'zh-CN';
    const select = document.getElementById('languageSelect');
    if (select) select.value = language;
    try { localStorage.setItem('musicdesk-language', language); } catch (_) {}
    translateTree(document.body);
    const active = document.querySelector('.tab-btn.active');
    const index = active ? [...document.querySelectorAll('.tab-btn')].indexOf(active) : 0;
    updateMobileTabLabel(['online', 'custom', 'local'][Math.max(index, 0)]);
  }

  document.addEventListener('DOMContentLoaded', () => {
    try { language = localStorage.getItem('musicdesk-language') === 'en' ? 'en' : 'zh'; } catch (_) {}
    document.getElementById('languageSelect')?.addEventListener('change', event => applyLanguage(event.target.value));
    document.getElementById('navMobileBtn')?.addEventListener('click', () => {
      const tabs = document.getElementById('navTabs');
      const open = tabs.classList.toggle('mobile-open');
      document.getElementById('navMobileBtn').setAttribute('aria-expanded', String(open));
    });
    document.addEventListener('click', event => {
      const actions = document.getElementById('headerActions');
      const tabs = document.getElementById('navTabs');
      if (actions && tabs && !actions.contains(event.target)) {
        tabs.classList.remove('mobile-open');
        document.getElementById('navMobileBtn')?.setAttribute('aria-expanded', 'false');
      }
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        document.getElementById('navTabs')?.classList.remove('mobile-open');
        document.getElementById('navMobileBtn')?.setAttribute('aria-expanded', 'false');
      }
    });
    applyLanguage(language);
    const observer = new MutationObserver(records => {
      for (const record of records) {
        if (record.type === 'characterData') translateTextNode(record.target);
        else record.addedNodes.forEach(translateTree);
      }
    });
    observer.observe(document.body, { subtree: true, childList: true, characterData: true });
  });
})();

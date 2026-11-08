(() => {
  'use strict';

  const translations = {
    '从列表移除': 'Remove from list',
    '取消': 'Cancel',
    '收起，回到曲库': 'Collapse and return to library',
    '收起': 'Collapse',
    '标题': 'Title',
    '年份': 'Year',
    '从网上补全信息': 'Fill in from the web',
    '按歌名搜索': 'Search by title',
    '作者 - 标题，或只输入标题': 'Artist - Title, or just the title',
    '未填写': 'Empty',
    '裁剪': 'Trim',
    '不裁剪': 'No trim',
    '更多信息': 'More details',
    '曲目号 · 流派 · 作曲': 'Track · Genre · Composer',
    '输出格式': 'Output format',
    '歌词内容': 'Lyrics text',
    '不填写的字段会保持为空。': 'Fields you leave blank stay empty.',
    '完成': 'Done',
    '虚线选项需要连接电脑。': 'Dashed options need a connected computer.',
    '去连接': 'Connect',
    '格式': 'Format',
    '比特率': 'Bitrate',
    '同时保存独立 .lrc 歌词': 'Also save a separate .lrc file',
    '设置自动保存在这台设备上。同时保存歌词时，音频和 .lrc 会放进同一个 ZIP。': 'Settings are saved on this device. When lyrics are saved too, the audio and .lrc go into one ZIP.',
    '无损格式不使用比特率': 'Lossless formats do not use a bitrate',
    'Android 可直接联网检索 MusicBrainz 曲目信息和 LRCLIB 歌词；格式转换与自定义封装仍需电脑服务。': 'Android can look up MusicBrainz track details and LRCLIB lyrics directly; format conversion and custom packaging still need the computer service.',
    '已连接电脑：封装与格式转换会在电脑完成后回传；所选音频将通过配对的局域网连接发送到电脑。': 'Computer connected: packaging and conversion run on the computer and the result is sent back. The selected audio is sent to the computer over the paired local network.',
    '当前使用手机本机能力；连接电脑 API 后，相关任务将交给电脑处理并回传结果。': 'Using this phone for now. After you connect the computer API, these tasks run on the computer and the results are sent back.',
    '未连接电脑：选择本地音频后，可在手机本机编辑标签、裁剪、转换格式并封装导出。': 'No computer connected: after choosing local audio you can edit tags, trim, convert, and export on this phone.',
    '电脑在线时优先由电脑端处理并回传文件；无法连接时，本机支持的功能仍可离线使用。需要先在电脑上启动 MusicDesk LAN API。': 'When the computer is online it handles the work and sends files back; when it is unreachable, features this phone supports keep working offline. Start the MusicDesk LAN API on the computer first.',
    '连接成功后，在线解析、歌词、下载、转换和封装任务会交给电脑处理，结果再传回手机；断开连接时改用手机本机能力。传输仅发生在你配对的局域网电脑与手机之间。': 'Once connected, lookup, lyrics, download, conversion, and packaging run on the computer and the results are sent back to the phone. When disconnected, the phone uses its own capabilities. Data only travels between your paired computer and phone on the local network.',
    '下载': 'Download',
    '编辑': 'Edit',
    '本机运行': 'Running on this computer',
    '本机处理': 'On this device',
    '已连接电脑': 'Computer connected',
    '通用': 'General',
    '语言': 'Language',
    '使用指南与快捷键': 'Guide & Shortcuts',
    '查看': 'View',
    '只转换格式': 'Convert only',
    '下载设置': 'Download settings',
    '下载来源': 'Download source',
    'yt-dlp（默认）': 'yt-dlp (default)',
    'SpotDL（元数据更完整）': 'SpotDL (fuller metadata)',
    '可以在“编辑”里手动粘贴歌词。': 'You can paste lyrics manually in Edit.',
    '网络连接失败，请检查网络后重试。': 'Network connection failed. Check your connection and try again.',
    '处理位置，点按查看设置': 'Processing location, open settings',
    '主导航': 'Main navigation',
    '含 .lrc': 'with .lrc',
    '在线解析与下载': 'Online Search & Download',
    '自定义封装与标签编辑': 'Custom Packaging & Tag Editor',
    '本地离线播放器': 'Offline Music Player',
    '在线解析': 'Online', '自定义': 'Custom', '曲库': 'Library',
    '选择语言': 'Language', '帮助与快捷键': 'Help & Shortcuts',
    'MusicDesk 使用帮助': 'MusicDesk Help', '关闭帮助': 'Close help', '关闭': 'Close',
    '关闭帮助': 'Close help', '在线解析与下载': 'Online Search & Download',
    '设置': 'Settings', '设置中心': 'Settings', '管理电脑服务连接、曲库访问权限和应用信息。': 'Manage computer connections, library access, and app information.',
    '电脑服务连接': 'Computer Service', '在线解析、下载和格式转换需要连接同一 Wi‑Fi 下运行的电脑端 MusicDesk。': 'Online search, downloads, and conversions require MusicDesk running on a computer on the same Wi-Fi network.',
    '曲目信息、歌词、格式转换和 SpotDL 下载使用电脑服务；yt-dlp 音频下载可由手机内置引擎执行。': 'Track details, lyrics, conversion, and SpotDL downloads use the computer service. yt-dlp audio downloads can run on the phone.',
    '曲目信息与歌词需连接电脑服务；yt-dlp 下载可在本机运行。': 'Track details and lyrics require the computer service. yt-dlp downloads can run on this device.',
    'Spotify 曲目信息需要连接电脑服务；本机 yt-dlp 支持 YouTube 链接和关键词搜索。': 'Spotify track details require the computer service. On-device yt-dlp supports YouTube links and keyword searches.',
    '下载音频（本机）': 'Download Audio (On Device)',
    '曲库与权限': 'Library & Permissions', 'MusicDesk 仅访问你选择的文件夹。撤销授权后，下次启动将不再自动载入该文件夹。': 'MusicDesk only accesses folders you select. Revoked folders will no longer be restored at startup.',
    'MusicDesk 仅访问你选择的文件夹。撤销授权后，下次启动将不再自动载入该文件夹；当前已载入的曲目会保留到本次使用结束。': 'MusicDesk only accesses folders you select. Revoked folders will no longer be restored at startup; tracks already loaded remain available until you close the app.',
    '添加音乐文件夹': 'Add Music Folder', '正在读取已授权文件夹…': 'Loading authorized folders…', '尚未授权音乐文件夹。添加文件夹后，应用会在下次打开时恢复曲库。': 'No music folders are authorized. Add a folder and the library will be restored next time.',
    '已授权 · 可在启动时恢复': 'Authorized · Restored at startup', '授权已失效 · 需要重新选择': 'Access expired · Select the folder again',
    '重新扫描': 'Rescan', '正在扫描…': 'Scanning…', '请重新授权': 'Reauthorize', '移除': 'Remove',
    '通知权限': 'Notifications', '正在检查…': 'Checking…', '已允许通知；锁屏播放控制由 Android 系统管理。': 'Notifications are enabled. Android controls lock-screen playback settings.',
    '通知已关闭；播放时可能看不到锁屏/通知栏控制。': 'Notifications are disabled. Lock-screen and notification playback controls may be hidden.',
    '管理': 'Manage', '系统应用权限': 'App Permissions', '在 Android 系统设置中查看和管理': 'View and manage permissions in Android Settings',
    '打开系统设置': 'Open System Settings', '检查更新': 'Check for Updates', '当前版本：读取中…': 'Current version: Loading…',
    '检查公开的 GitHub Release，不会自动下载或安装。': 'Checks public GitHub releases. Updates are not downloaded or installed automatically.',
    '当前版本：': 'Current version: ', '检查失败：': 'Check failed: ', '无法读取 GitHub Release': 'Could not read GitHub release information',
    'GitHub 最新版本：': 'Latest GitHub version: ', '。请打开发布页确认是否适用于 Android。': '. Open the release page to confirm Android availability.',
    '发现新版本 ': 'A newer version is available: ', '。请在发布页确认 Android 安装包后手动下载并安装。': '. Check for an Android package on the release page, then download and install it manually.',
    '当前版本已是最新版本（': 'You are using the latest version (', '）。': ').', '正在检查 GitHub Release…': 'Checking GitHub releases…',
    '查看更新': 'View Release', '关于 MusicDesk': 'About MusicDesk', 'MusicDesk · 本地音乐播放器与曲目信息工具': 'MusicDesk · Local music player and track information tools',
    '音乐文件在本机处理；在线检索、下载和转换通过你连接的电脑服务完成。': 'Music files are processed locally. Online lookup, downloads, and conversion use your connected computer service.',
    '项目主页与更新记录': 'Project page and release notes', '使用帮助与快捷键': 'Help & Keyboard Shortcuts',
    '在线': 'Online', '设置': 'Settings',
    '在线资料、歌词、SpotDL 下载与转换可用；yt-dlp 可在手机本机下载。': 'Online track details, lyrics, SpotDL downloads, and conversion are available; yt-dlp can download on this device.',
    '请测试连接后使用在线资料和歌词。yt-dlp 下载在手机本机执行。': 'Test the connection to use online track details and lyrics. yt-dlp downloads run on this device.',
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
    '本地播放列表': 'Local playlist', '粘贴链接或搜索歌名，选好格式后下载。': 'Paste a link or search a title, pick a format, then download.', '粘贴链接或搜索歌名即可下载 MP3；其他格式需要连接电脑。': 'Paste a link or search a title to download MP3. Other formats need a connected computer.', '补全标题、歌手、封面和歌词。常用项在前，其余收在“更多信息”里。': 'Fill in title, artist, cover and lyrics. Common fields come first; the rest is under “More info”.', '用“添加”导入歌曲或文件夹，离线播放、收藏和排队。': 'Use “Add” to import songs or a folder, then play offline, favorite and queue.', '下一步': 'Next', '跳过': 'Skip', '开始使用': 'Get started', '手机本机下载会把歌词直接写进 MP3；独立 .lrc 需要连接电脑。': 'Phone downloads embed lyrics directly in the MP3. A separate .lrc file needs a connected computer.', 'YouTube 暂时要求验证身份（移动网络或共享网络上常见）。请换一个 Wi‑Fi 或稍后重试，也可以连接电脑后再下载。': 'YouTube is asking for verification (common on mobile or shared networks). Try another Wi‑Fi or retry later, or connect your computer and download there.', '保存时在系统选择器里选已有文件即可覆盖，输入新名字则另存为。': 'In the system picker, choose an existing file to overwrite it, or type a new name to save a copy.', '选择文件夹': 'Choose folder', '＋ 添加': '+ Add', '选择歌曲': 'Choose songs',
    '搜索本地歌曲名/歌手...': 'Search local songs or artists...', '拖入一首或多首音乐到此处添加': 'Drop one or more audio files here to add them',
    '播放全部': 'Play all', '首': ' tracks', '歌曲': 'Songs', '歌手': 'Artists', '专辑': 'Albums', '文件夹': 'Folders', '收藏': 'Favorites',
    '正在播放': 'Now Playing', '歌词': 'Lyrics', '未选择歌曲': 'No track selected', '本地音乐离线播放器': 'Offline music player',
    '暂无内嵌 LRC 歌词': 'No embedded LRC lyrics', '歌词准备就绪': 'Lyrics are ready', '清空': 'Clear queue', '移除': 'Remove',
    '上一首': 'Previous track', '下一首': 'Next track', '播放': 'Play', '暂停': 'Pause',
    '顺序播放': 'In order', '随机播放': 'Shuffle',
    '曲目信息搜索': 'Track Information Search', '粘贴 Spotify / YouTube 分享链接，或搜索“作者 - 标题”及单独标题': 'Paste a Spotify or YouTube link, or search “Artist - Title” or a title',
    '分享链接或关键词': 'Link or keywords', '读取 / 搜索曲目信息': 'Read / Search Track Details',
    '下载 MP3': 'Download MP3', '歌词阅读器': 'Lyrics Reader', '搜索完成，可继续查看歌词或下载。': 'Search complete. You can view lyrics or download audio.',
    '本机下载完成，已保存音频：': 'Download complete. Audio saved on this device: ', '本机 yt-dlp 当前保存来源音频格式；MP3 转换、内嵌歌词及 SpotDL 仍由电脑服务提供。': 'On-device yt-dlp currently preserves the source audio format. MP3 conversion, embedded lyrics, and SpotDL still use the computer service.',
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
    '音乐文件夹': 'Music folder', '尚未加载本地音乐': 'No local music loaded', '点击右上角“添加”': 'Tap Add at the top right to get started',
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
    '从电脑终端复制配对密钥': 'Copy the pairing token from your computer terminal',
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

  Object.assign(translations, {
  "选择音频并载入 LRC 歌词后，可试听并点选歌词校时。": "Choose audio and load LRC lyrics to preview and click a line to adjust its timing.",
  "收藏歌曲": "Favorite song", "取消收藏": "Remove from favorites", "播放": "Play", "暂停": "Pause", "播放列表": "Playlist",
  "解析本机音频标签失败。": "Failed to read tags from this audio.",
  "音频抓取来源:": "Audio source:",
    "想让手机用这台电脑处理下载和转换：": "To let your phone use this computer for downloads and conversion:",
    "暂无内嵌歌词": "No embedded lyrics",
    "Spotify 曲目信息需要连接电脑服务；手机可直接搜索 MusicBrainz。": "Spotify track info needs the computer service. Your phone can search MusicBrainz directly.",
    "电脑服务未连通，在线功能已锁定：检查同一 Wi‑Fi、电脑 LAN 地址/端口、配对码及防火墙。": "Cannot reach the computer service, so online features stay locked. Check the Wi‑Fi, the computer’s LAN address and port, the pairing token and the firewall.",
    "播放进度": "Playback position",
    "音轨编号": "Track number",
    "碟片编号": "Disc number",
    "专辑歌手": "Album artist",
    "流派": "Genre",
    "作曲": "Composer",
    "连接后，下载、转换和歌词等任务交给电脑处理，结果传回手机；不连接也能用手机本机功能。": "When connected, downloads, conversion and lyrics run on your computer and the results come back to your phone. Without it, the phone still works on its own.",
    "已保存，未验证": "Saved, not verified",
    "所有歌词行已标记": "All lyric lines are marked",
    "请先选择音频，或搜索并填写曲名后直接封装。": "Choose an audio file first, or search and fill in the title before packaging.",
    "已断开电脑服务。": "Disconnected from the computer service.",
    "WebVTT 字幕": "WebVTT subtitles",
    "SRT 字幕": "SRT subtitles",
    "标准 LRC": "Standard LRC",
    "增强 LRC（逐词时间）": "Enhanced LRC (word timing)",
    "纯文本": "Plain text",
    "自动识别": "Auto-detect",
    "歌词来源格式": "Lyrics source format",
    "使用 YouTube 官方嵌入播放器；部分视频因版权、地区或禁止嵌入设置可能无法试听。": "Uses the official YouTube embedded player. Some videos cannot be previewed because of copyright, region or embedding settings.",
    "手机 yt-dlp 备用搜索": "Phone yt-dlp fallback search",
    "yt-dlp 备用搜索": "yt-dlp fallback search",
    "手机 yt-dlp 搜索": "Phone yt-dlp search",
    "手机 yt-dlp": "Phone yt-dlp",
    "手机直连 MusicBrainz": "Phone → MusicBrainz",
    "MusicBrainz 关键词搜索": "MusicBrainz keyword search",
    "无法恢复上次的曲库，请重新选择文件夹或歌曲。": "Could not restore the last library. Choose folders or songs again.",
    "无法恢复上次的音乐文件，请重新选择文件夹或歌曲。": "Could not restore the last music files. Choose folders or songs again.",
    "上次的音乐文件暂时无法访问，请重新选择文件夹或歌曲。": "The last music files are not accessible right now. Choose folders or songs again.",
    "歌曲已添加；标签解析库未加载，播放仍可用，但无法读取封面和内嵌歌词。": "Songs added. The tag reader did not load, so playback works but covers and embedded lyrics cannot be read.",
    "手机端返回了无法读取的曲目信息。": "The phone returned track info that could not be read.",
    "MusicBrainz 返回了无法读取的曲目信息。": "MusicBrainz returned track info that could not be read.",
    "LRCLIB 返回了无法读取的歌词。": "LRCLIB returned lyrics that could not be read.",
    "解析元数据失败": "Failed to read metadata",
    "下载失败": "Download failed",
    "转换失败": "Conversion failed",
    "读取失败": "Read failed",
    "定制封装失败": "Packaging failed",
    "搜索曲目信息失败": "Track info search failed",
    "正在搜索公开曲目信息…": "Searching public track info…",
    "已根据关键词补全信息，请检查后导出。": "Filled in from your keywords. Review it, then export.",
    "未知": "Unknown",
    "未知标题": "Unknown title",
    "未知歌手": "Unknown artist",
    "未知艺人": "Unknown artist",
    "未知专辑": "Unknown album",
    "未知曲目": "Unknown track",
    "搜索本地歌名/歌手...": "Search local songs or artists…",
    "压缩包里没有 LRC，因为未找到这首歌的歌词。": "The ZIP has no LRC because no lyrics were found for this song.",
    "公开歌词库中没有找到这首歌的歌词。": "No lyrics for this song were found in the public lyrics library.",
    "音频没有内嵌歌词，正在尝试从 LRCLIB 获取…": "No embedded lyrics. Trying LRCLIB…",
    "未找到歌词，将不嵌入歌词": "No lyrics found; none will be embedded",
    "未检索到歌词": "No lyrics found",
    "启动。": "to start it.",
    "在电脑上双击": "On your computer, double-click",
    "关闭当前窗口，改用": "Close this window and start with",
    "暂停试听": "Pause preview",
    "YouTube 歌曲试听": "YouTube song preview",
    "在浏览器试听": "Preview in browser",
    "YouTube 试听": "YouTube preview",
    "在 YouTube 打开": "Open on YouTube",
    "无法试听音频。": "Cannot preview the audio.",
    "追加内容，例如：Live": "Extra text, e.g. Live",
    "文件不能超过 150 MB。": "File must be 150 MB or smaller.",
    "音频预听与裁剪": "Audio preview and trim",
    "电脑连接": "Computer connection",
    "手机配对": "Phone pairing",
    "选择或读取音乐文件失败。": "Failed to choose or read music files.",
    "选择音乐文件失败。": "Failed to choose music files.",
    "打开文件夹选择窗口失败。": "Could not open the folder picker.",
    "打开音乐文件选择窗口失败。": "Could not open the music file picker.",
    "正在检索并载入 LRC 歌词…": "Searching and loading LRC lyrics…",
    "播放全部方式": "Play all as",
    "播放队列": "Play queue",
    "收起播放列表": "Collapse play queue",
    "向下拖动收起播放列表": "Drag down to collapse the play queue",
    "此功能已锁定。请先连接电脑上的 MusicDesk 服务，确认 API 匹配后再使用。": "This feature is locked. Connect to the MusicDesk service on your computer and confirm the API matches first.",
    "这些歌曲已在播放列表中": "These songs are already in the playlist",
    "正在 Android 设备本机转换…": "Converting on this Android device…",
    "正在本机转换…": "Converting on this device…",
    "正在读取并解析音频标签元数据...": "Reading and parsing audio tag metadata…",
    "连接电脑以处理设置": "Connect computer to use these settings",
    "已读取内部资料。您可以更改上述内容后点击导出。": "Embedded info loaded. Edit anything above, then export.",
    "密钥每次启动都会变化，只在你信任的家庭或办公 Wi‑Fi 中使用。": "The token changes on every start. Use it only on a home or office Wi‑Fi you trust.",
    "MusicBrainz 没有匹配结果，已自动改用手机 yt-dlp 搜索。": "MusicBrainz had no match, so the phone searched with yt-dlp instead.",
    "MusicBrainz 没有匹配结果，已自动改用 yt-dlp 搜索；下载将使用该结果链接。": "MusicBrainz had no match, so yt-dlp searched instead. The download will use that result’s link.",
    "文件夹中没有新的支持格式音频，请选择包含音乐的文件夹。": "No new supported audio in that folder. Choose a folder that contains music.",
    "文件夹中没有新的支持格式音频": "No new supported audio in the folder",
    "已导入文件夹": "Imported folder",
    "（空歌词行）": "(empty lyric line)",
    "待标记": "To mark",
    "可以粘贴 LRC 格式或纯文本歌词...": "Paste LRC or plain-text lyrics…",
    "正在使用手机内置 yt-dlp 下载并转换为 MP3…": "Downloading with the phone’s built-in yt-dlp and converting to MP3…",
    "无法读取所选音频": "Could not read the selected audio",
    "窗口会显示“Phone server address”和“One-run pairing token”。": "The window shows “Phone server address” and “One-run pairing token”.",
    "窗口里会显示“Phone server address”和“One-run pairing token”。": "The window shows “Phone server address” and “One-run pairing token”.",
    "手机和电脑连同一个 Wi‑Fi，把它们填在下面。": "Put both devices on the same Wi‑Fi and enter them below.",
    "在手机 MusicDesk 的“设置 → 电脑连接”里填入。": "Enter them in MusicDesk on your phone under Settings → Computer connection.",
    "暂无分类内容": "Nothing in this category",
    "播放列表为空": "The playlist is empty",
    "配对密钥格式不正确，请从电脑终端完整复制。": "The pairing token looks wrong. Copy it in full from the computer terminal.",
    "配对密钥无效或已过期；功能已锁定，请重新连接。": "The pairing token is invalid or expired. Features are locked; reconnect.",
    "信息已读取。": "Info loaded.",
    "音乐文件": "Music files",
    "正在本机写入音频标签…": "Writing audio tags on this device…",
    "所选格式、比特率或独立 LRC 下载需要连接电脑服务。请在设置中心连接电脑后重试。": "The chosen format, bitrate or standalone LRC needs the computer service. Connect your computer in Settings and try again.",
    "SpotDL 来源与在线标签搜索": "SpotDL source and online tag search",
    "WAV、FLAC、AAC 等所有格式和比特率": "All formats and bitrates, including WAV, FLAC and AAC",
    "歌词下载与格式转换": "Lyrics download and format conversion",
    "连接电脑后可用": "Available once connected",
    "正在搜索音源并封装标签，请稍候...": "Searching for a source and packaging tags…",
    "请输入“作者 - 标题”或歌曲标题。": "Enter “Artist - Title” or a song title.",
    "没有选择受支持的音乐文件。": "No supported music files were chosen.",
    "已嵌入普通歌词（来源无时间戳）": "Plain lyrics embedded (source has no timestamps)",
    "已嵌入同步 LRC 歌词": "Synced LRC lyrics embedded",
    "正在发送音频到电脑读取标签…": "Sending audio to the computer to read tags…",
    "正在发送到电脑封装并回传文件，请稍候…": "Sending to the computer for packaging; the file will come back shortly…",
    "正在发送到电脑转换…": "Sending to the computer for conversion…",
    "封装区一次处理一个音频文件，已选取第一个文件。": "Only one audio file is processed at a time; the first file was chosen.",
    "已载入纯文本歌词（无时间戳）；点击“保存并打包导出文件”即可内嵌。": "Plain-text lyrics loaded (no timestamps). Tap “Save and Export” to embed them.",
    "已从 LRCLIB 载入同步 LRC；点击“保存并打包导出文件”即可内嵌。": "Synced LRC loaded from LRCLIB. Tap “Save and Export” to embed it.",
    "单曲循环": "Repeat one",
    "列表循环": "Repeat all",
    "切换播放模式": "Switch play mode",
    "无法读取所选音乐文件，请重新授权后重试。": "Could not read the chosen music file. Grant access again and retry.",
    "退出逐句打点": "Exit line-by-line marking",
    "正在打包并写回标签元数据，请稍候...": "Packaging and writing tag metadata…",
    "浏览器需要重新授权访问上次的音乐文件；请点击“选择文件夹”或“选择歌曲”。": "The browser needs permission again to open the last music files. Choose a folder or songs again.",
    "已从所选音频读取标签。可以修改后本机封装。": "Tags read from the chosen audio. Edit them, then package on this device.",
    "电脑服务无法访问；在线功能已锁定。请确认电脑服务运行中且手机和电脑在同一 Wi‑Fi。": "The computer service cannot be reached, so online features are locked. Make sure it is running and both devices are on the same Wi‑Fi.",
    "已选歌曲": "Selected songs",
    "请拖入 MP3、M4A、FLAC、WAV 或 OGG 音频文件。": "Drop an MP3, M4A, FLAC, WAV or OGG audio file.",
    "没有找到支持的音频；可拖入 MP3、M4A、FLAC、WAV 或 OGG": "No supported audio found. Drop an MP3, M4A, FLAC, WAV or OGG file.",
    "正在读取…": "Reading…",
    "我的收藏": "My favorites",
    "未连接": "Not connected",
    "已连接": "Connected",
    "正在整理曲库…": "Organizing library…",
    "正在从文件夹读取音频…": "Reading audio from the folder…",
    "请输入电脑终端显示的 http://IP:端口 地址。": "Enter the http://IP:port address shown in the computer terminal.",
    "Spotify 链接，或 作者 - 标题 / 标题": "Spotify link, or Artist - Title / Title",
    "封面": "Cover",
    "正在测试电脑服务…": "Testing the computer service…",
    "MusicBrainz 曲目信息、LRCLIB 歌词和 yt-dlp 下载可由手机联网使用。": "Your phone can use MusicBrainz track info, LRCLIB lyrics and yt-dlp downloads over the internet.",
    "MusicBrainz 曲目信息已载入，可继续检索歌词或下载。": "MusicBrainz track info loaded. You can look up lyrics or download next.",
    "已由手机 yt-dlp 读取曲目信息，可直接下载音频。": "Track info read by the phone’s yt-dlp. You can download the audio now.",
    "电脑端 API 版本或功能不匹配；请更新电脑端 MusicDesk 后再连接。功能已保持锁定。": "The computer’s API version or features do not match. Update MusicDesk on the computer, then reconnect. Features stay locked.",
    "本机 yt-dlp 下载后会转换为 MP3，并写入可用的曲目信息与封面标签。": "Phone yt-dlp downloads are converted to MP3 with any available track info and cover tags.",
    "电脑服务拒绝了连接。": "The computer service refused the connection.",
    "这段歌词没有时间戳。选择音频后，可以开启逐句打点模式。": "These lyrics have no timestamps. Choose audio, then turn on line-by-line marking.",
    "无法读取所选文件夹，请检查浏览器文件访问权限。": "Could not read the chosen folder. Check the browser’s file access permission.",
    "已填 0 项": "0 filled"
  });

  const reverse = new Map(Object.entries(translations).map(([zh, en]) => [en, zh]));
  const protectedSelectors = 'script,style,textarea,input,select,[contenteditable="true"],#lrcContainer,#localLrcContainer,#customLyricsPreview,.track-list,.queue-sheet,.result-info,#nowTitle,#nowArtist,#miniTitle,#miniArtist,#title,#artist';
  const mobileNames = {
    online: { zh: '在线解析与下载', en: 'Online' },
    custom: { zh: '自定义封装与标签编辑', en: 'Custom' },
    local: { zh: '本地离线播放器', en: 'Library' },
    settings: { zh: '设置', en: 'Settings' },
  };
  let language = 'zh';

  function lookup(value, lang) {
    const trimmed = value.trim();
    if (!trimmed) return value;
    const count = trimmed.match(/^(\d+)\s*(首|tracks?)$/i);
    if (count) return value.replace(trimmed, lang === 'en' ? `${count[1]} tracks` : `${count[1]} 首`);
    const phrases = lang === 'en'
      ? [['。请打开发布页确认是否适用于 Android。', '. Open the release page to confirm Android availability.'], ['。请在发布页确认 Android 安装包后手动下载并安装。', '. Check for an Android package on the release page, then download and install it manually.']]
      : [['. Open the release page to confirm Android availability.', '。请打开发布页确认是否适用于 Android。'], ['. Check for an Android package on the release page, then download and install it manually.', '。请在发布页确认 Android 安装包后手动下载并安装。']];
    for (const [source, target] of phrases) {
      if (trimmed.includes(source)) return value.replace(trimmed, trimmed.replace(source, target));
    }
    const patterns = [
      [/^已连接电脑服务：(\S+?)。解析、歌词、下载、转换和封装任务由电脑处理，结果回传到手机。$/, 'Connected to computer service: $1. Lookup, lyrics, download, conversion, and packaging run on the computer and the results are sent back to the phone.',
       /^Connected to computer service: (\S+?)\. Lookup, lyrics, download, conversion, and packaging run on the computer and the results are sent back to the phone\.$/, '已连接电脑服务：$1。解析、歌词、下载、转换和封装任务由电脑处理，结果回传到手机。'],
      [/^已保存电脑地址 (\S+?)；验证连接后，相关任务将由电脑处理。当前使用手机本机能力。$/, 'Saved computer address $1. After the connection is verified, these tasks run on the computer. Using this phone for now.',
       /^Saved computer address (\S+?)\. After the connection is verified, these tasks run on the computer\. Using this phone for now\.$/, '已保存电脑地址 $1；验证连接后，相关任务将由电脑处理。当前使用手机本机能力。'],
      [/^(\d+) 首歌曲$/, '$1 songs'],
      [/^例如：3 或 3\/12$/, 'e.g. 3 or 3/12'],
      [/^例如：(.+)$/, 'e.g. $1'],
      [/^MusicBrainz 搜索失败（(.+)）；yt-dlp 备用搜索也失败（(.+)）。$/, 'MusicBrainz search failed ($1); the yt-dlp fallback search also failed ($2).'],
      [/^导出成功，已保存为 (.+)$/, 'Exported and saved as $1'],
      [/^本机封装完成，已保存为 (.+)$/, 'Packaged on this device and saved as $1'],
      [/^转换完成，已保存为 (.+)$/, 'Conversion finished and saved as $1'],
      [/^播放列表（(\d+) 首）$/, 'Playlist ($1 tracks)'],
      [/^文件夹导入完成：曲库共 (\d+) 首（达到单次导入上限）$/, 'Folder imported: $1 tracks in the library (single-import limit reached)'],
      [/^文件夹导入完成：曲库共 (\d+) 首$/, 'Folder imported: $1 tracks in the library'],
      [/^曲库已就绪，共 (\d+) 首歌曲。已达到单次导入上限。$/, 'Library ready: $1 songs. The single-import limit was reached.'],
      [/^曲库已就绪，共 (\d+) 首歌曲。$/, 'Library ready: $1 songs.'],
      [/^正在载入曲库…已处理 (\d+) 首$/, 'Loading library… $1 processed'],
      [/^正在导入歌曲：已加入 (\d+) 首$/, 'Importing songs: $1 added'],
      [/^已添加 (\d+) 首；可继续拖入音乐$/, '$1 added. You can keep dropping music.'],
      [/^已添加 (\d+) 首；关闭后会记住这次选择$/, '$1 added. This choice is remembered after you close the app.'],
      [/^已选择：(.+)$/, 'Selected: $1'],
      [/^已标记 (\d+) \/ (\d+) 句。播放到每句开始处，按空格或点击“标记当前句”。$/, '$1 / $2 lines marked. Play to the start of each line, then press Space or tap “Timestamp current line”.'],
      [/^标记第 (\d+) 行（空格）$/, 'Mark line $1 (Space)'],
      [/^本机下载完成，已保存音频：(.+?)；(.+)$/, 'Downloaded on this device and saved: $1; $2'],
      [/^下载完成，已保存到你选择的位置：(.+?)(?:；(.+))?$/, 'Download finished and saved to the place you chose: $1'],
      [/^下载完成！已自动装载至线上播放器试听。\s*(.*)$/, 'Download finished! Loaded into the online player for preview. $1'],
      [/^下载完成！音频与 LRC 已打包为 ZIP。\s*(.*)$/, 'Download finished! Audio and LRC are packed in a ZIP. $1'],
      [/^已读取音频标签，但未能补全歌词：(.+)$/, 'Audio tags read, but lyrics could not be filled in: $1'],
      [/^正在按优先级 \((.+)\) 下载音频并自动内嵌 LRC 歌词，请稍候\.\.\.$/, 'Downloading audio by priority ($1) and embedding LRC lyrics…'],
      [/^当前：(.+)，点击切换$/, 'Current: $1. Tap to switch.'],
      [/^(.+)，需要连接电脑$/, '$1, needs a connected computer'],
      [/^更多操作：(.+)$/, 'More actions: $1'],
      [/^已填 (\d+) 项$/, '$1 filled', /^(\d+) filled$/, '已填 $1 项'],
      [/^(\d+) 行$/, '$1 lines', /^(\d+) lines$/, '$1 行'],
      [/^已连接：(\S+)$/, 'Connected: $1', /^Connected: (\S+)$/, '已连接：$1'],
      [/^已保存：(\S+?)（点按钮测试连接）$/, 'Saved: $1 (tap the button to test the connection)', /^Saved: (\S+?) \(tap the button to test the connection\)$/, '已保存：$1（点按钮测试连接）'],
    ];
    for (const [zhRe, enText, enRe, zhText] of patterns) {
      const re = lang === 'en' ? zhRe : enRe;
      if (!re) continue;
      if (re.test(trimmed)) {
        let out = lang === 'en'
          ? trimmed.replace(re, (...match) => enText.replace(/\$(\d)/g, (_, n) => lookup(match[Number(n)] || '', lang)))
          : trimmed.replace(re, zhText);
        // Messages built from several parts ("saved X; <status>") can carry a Chinese tail.
        const firstCjk = lang === 'en' ? out.search(/[\u4e00-\u9fff]/) : -1;
        if (firstCjk >= 0) {
          const tail = out.slice(firstCjk).split('；').map(part => lookup(part, lang)).join('; ');
          out = out.slice(0, firstCjk) + tail;
        }
        return value.replace(trimmed, out);
      }
    }
    const translated = lang === 'en' ? translations[trimmed] : reverse.get(trimmed);
    if (translated !== undefined) return value.replace(trimmed, translated);
    const prefixes = lang === 'en'
      ? [['当前版本：', 'Current version: '], ['检查失败：', 'Check failed: '], ['GitHub 最新版本：', 'Latest GitHub version: '], ['发现新版本 ', 'A newer version is available: '], ['当前版本已是最新版本：', 'You are using the latest version: '], ['已连接：', 'Connected: '], ['已保存：', 'Saved: ']]
      : [['Current version: ', '当前版本：'], ['Check failed: ', '检查失败：'], ['Latest GitHub version: ', 'GitHub 最新版本：'], ['A newer version is available: ', '发现新版本 '], ['You are using the latest version: ', '当前版本已是最新版本：'], ['Connected: ', '已连接：'], ['Saved: ', '已保存：']];
    const prefix = prefixes.find(([source]) => trimmed.startsWith(source));
    return prefix ? value.replace(trimmed, prefix[1] + trimmed.slice(prefix[0].length)) : value;
  }

  window.translateUi = value => lookup(String(value), language);

  function translateTextNode(node) {
    const parent = node.parentElement;
    if (!parent || (parent.closest(protectedSelectors) && !parent.closest('.ui-text'))) return;
    const translated = lookup(node.nodeValue, language);
    if (translated !== node.nodeValue) node.nodeValue = translated;
  }

  function translateTree(root) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) {
      translateTextNode(root);
      return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE) return;
    const protectedAttributeSelectors = 'script,style,[contenteditable="true"],#lrcContainer,#localLrcContainer,#customLyricsPreview,.track-list,.result-info,#nowTitle,#nowArtist,#miniTitle,#miniArtist,#title,#artist';
    const translateAttributes = element => {
      if (element.matches(protectedAttributeSelectors)) return;
      for (const attribute of ['placeholder', 'title', 'aria-label', 'alt']) {
        const value = element.getAttribute(attribute);
        if (value) element.setAttribute(attribute, lookup(value, language));
      }
    };
    translateAttributes(root);
    if (root.matches(protectedSelectors)) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) translateTextNode(walker.currentNode);
    root.querySelectorAll('[placeholder],[title],[aria-label],[alt]').forEach(element => {
      translateAttributes(element);
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
    updateMobileTabLabel(['online', 'custom', 'local', 'settings'][Math.max(index, 0)]);
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

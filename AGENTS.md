# AGENTS.md — MusicDesk 协作指南

本文件写给在本仓库工作的 AI 编码代理（Claude Code、Codex、Copilot Agent 等），也适合新加入的开发者先读一遍。
目标：不用反复摸索，就能写出符合本项目约定、不会踩旧坑的改动。

## 0. 硬性规则（必须遵守）

1. 每次改动完成都必须创建对应的 git commit，用于追踪和回滚。
2. 每次改动都必须编写或更新相关测试，并在交付前确保所有测试和验证全部通过。
3. `master` 受保护：只能经 PR 合并（squash），且 CI 的 `desktop-and-android-python`、`android-compile` 必须通过。**每个新分支都从最新的 `master` 切出**，不要从已合并的旧分支继续开 PR（#34/#35 就是旧分支合并后把 #33 的改动删了又加回来）。
4. 永远不要提交签名密钥、`releases/` 下的构建产物、下载的音频、个人凭证（`.gitignore` 已挡住，测试也会检查）。

---

## 1. 项目速览

**MusicDesk** 是一套音乐元数据与音频工具：按链接或「作者 - 标题」检索曲目信息，用 yt-dlp / SpotDL 下载，自动内嵌封面与同步歌词，编辑标签、裁剪、转换格式，并带一个本地音乐播放器（播放列表、均衡器、双语歌词）。

| 项 | 值 |
|---|---|
| 当前版本 | 0.3.0（`android/app/build.gradle.kts` 的 `versionName` / `versionCode`） |
| 运行形态 | Windows 桌面（原生窗口）、浏览器、Android |
| 桌面 | Python 3.10+ 本地 HTTP 服务 + pywebview 窗口，PyInstaller 打包为便携版 |
| Android | Java + WebView，Chaquopy 内嵌 Python 3.14，ffmpeg-kit 转码；minSdk 24 / targetSdk 35 / compileSdk 36，仅 arm64-v8a |
| 外部服务 | MusicBrainz、Cover Art Archive、LRCLIB、Spotify oEmbed、YouTube（yt-dlp） |
| 界面语言 | 源码里是中文，英文由 `i18n.js` 翻译 |

---

## 2. 架构与目录

**核心设计：一份网页，两个外壳。** 电脑和手机显示的是同一个 `index.html`。页面用 `window.AndroidMusic` 是否存在来判断运行环境：

- **电脑 / 浏览器**：页面通过 `fetch('/api/...')` 调用本地 Python 服务。
- **Android**：页面调用 `AndroidMusic.xxx(...)`（Java 的 `@JavascriptInterface`），Java 做完后回调 `window.onAndroidXxx(...)`。
- **手机连接电脑**：手机配对电脑服务后（电脑用 `start_lan.bat` 以局域网模式启动），手机上的相关任务改由电脑处理并回传结果。

```
index.html            # ★ 唯一的界面：HTML + CSS + 全部页面 JS（下载 / 编辑 / 播放 / 设置）
i18n.js               # 中英翻译：静态文案表 + 动态消息的正则 patterns
library_sort.js       # 曲库排序（页面渲染曲库时直接调用 window.sortLibraryTracks）
default_song_img.png  # 默认封面

launcher.py           # 桌面入口：起服务 + pywebview 窗口（--browser / --port / --lan --token）
app.py                # 桌面服务：Handler 的 /api/* 路由 + 元数据、歌词、下载、转换、标签封装
desktop_media.py      # 桌面原生选文件，以及为页面私有提供本地音频
musicdesk_core/       # ★ 桌面与 Android 共用、不依赖平台的逻辑
  media.py            #   ffmpeg 参数、裁剪时间、导出文件名
  lyrics.py           #   歌词规范化、LRC 解析/平移、describe_embedded_lyrics（歌词存在哪些标签字段）
  metadata.py         #   分享链接解析、「作者 - 标题」拆分、MusicBrainz 查询串
  batch.py            #   歌单批量下载队列

android/app/src/main/
  assets/             # index.html 等的副本（由 tools/sync_android_assets.py 同步，勿手改）
  java/com/musicdesk/android/
    MainActivity.java     # WebView、AndroidMusicBridge（JS 接口）、SAF 文件访问、下载保存
    LocalMediaRoutes.java # 缓存音频的 https 地址与 Range 解析（见 §3.4）
    MusicPlaybackService.java  # 前台播放通知与媒体按键
  python/musicdesk_downloader.py  # 手机端 Python：yt-dlp 下载、MusicBrainz、LRCLIB、标签读写
android/ffmpeg-kit-maven/  # 本地 Maven 仓库里的 ffmpeg-kit AAR

tools/sync_android_assets.py  # 把根目录的网页文件复制到 Android assets（--check 只检查）
build_windows.bat     # 便携版打包（PyInstaller → dist/MusicDesk-portable.zip）
package_portable.py   # 打 ZIP，并把 Deno/Node/QuickJS 放进包里（yt-dlp 需要 JS 运行时）
start.bat / start_lan.bat  # 源码方式启动（自动建 .venv）
test_app.py           # 桌面与跨端测试（含对页面、Java 源码的结构检查）
tests/                # Node 回归测试（i18n、Android 界面门控等）和批量队列测试
android/app/src/test/ # Android 的 Python 测试与 Java 单元测试
docs/release-notes/   # 各版本发行说明
```

---

## 3. 必须遵守的约定（以及为什么）

### 3.1 只改根目录的网页文件，再同步到 Android

`index.html`、`i18n.js`、`library_sort.js`、`default_song_img.png` 以根目录为准。改完运行 `python tools/sync_android_assets.py`；测试会用 `--check` 确认两份一致。

### 3.2 页面新引用的文件，必须加进便携版打包

便携版只从包内目录提供文件，漏打包就是 404。`library_sort.js` 曾经漏打，导致电脑端曲库列表无法显示（v0.2.0 受影响）。

新增 `<script src>` 或资源时：加进 `build_windows.bat` 的 `--add-data`，以及 `tools/sync_android_assets.py` 的 `SHARED`。测试 `test_every_local_page_asset_is_bundled_in_the_portable_build` 会检查前者。`MusicDesk.spec` 是自动生成的，已被忽略，不要改它。

### 3.3 文案写中文，英文走 i18n.js

- **固定文案**：加进 `i18n.js` 的翻译表。
- **运行时拼出来的句子**（带文件名、数字等）：在 `patterns` 里加正则。
- **页面翻译器不处理的区域**（歌词、曲目列表、aria/title）：用 `ui()` / `.ui-text`。

每条新的动态消息都要在 `tests/test_i18n_dynamic_copy.js` 里加样例，确认英文模式下没有残留中文。

### 3.4 Android 播放的音频必须走 https 媒体地址，不能用 file://

WebView 把 `file://` 媒体视为跨域，接上 Web Audio（均衡器）后会**静音**。所以缓存音频由 `MainActivity.serveCachedAudio` 通过 `https://appassets.androidplatform.net/musicdesk-audio/<文件>` 提供（带 CORS 头），页面用 `setPlayerSource()` 设置 `crossOrigin="anonymous"`。

**Range 的坑**：WebView 会自己把返回的流跳到 Range 起点。所以要交出**整个文件**的流，只在终点处截断（`BoundedInputStream(range[1] + 1)`），并返回 206 和 `Content-Range`。自己再跳一次会导致偏移翻倍、拖动进度条失败。

### 3.5 下载时的歌词按「实际下载到的音频」匹配

MusicBrainz 常把日文歌名给成英文译名（アイドル → "Idol"），而英文版歌曲也叫 "Idol"，只按歌名查 LRCLIB 会拿到英文歌词。

手机下载时，页面发 `lookup_lyrics: true`，由 Python 在**下载完成后**调用 `lookup_lyrics(title, artist, duration=…, source_title=视频原标题, source_artist=频道)`。排序依次看：文字系统是否一致（原标题含中日韩文字时优先同类歌词），时长是否在 ±3 秒内，是否带时间戳。**不要把歌词查询挪回下载之前。**

### 3.6 读歌词要看隐藏字段

mutagen 的 easy 接口看不到 ID3 的 USLT/SYLT。读歌词用 `_read_embedded_lyrics()`，列出字段用 `describe_embedded_lyrics()`。编辑页的格式提示（如「内嵌歌词：ID3 USLT + ID3 SYLT · 带时间戳」）依赖后者。

### 3.7 可选步骤失败不能拖垮主任务

歌词、封面、候选列表都是锦上添花：失败时给提示或留空，音频照常下载和保存。

### 3.8 安全边界

- 局域网模式一定要有配对令牌：
  - `start_lan.bat`（即 `app.py --lan`）每次启动会自动生成一个一次性令牌。
  - 自定义的 `--token` 至少 24 位；便携版的 `MusicDesk.exe --lan` 必须显式提供 `--token`。
- 本机请求视为可信，但 `Origin: null` 除外。
- 下载来源和封面地址先经过 `validate_download_source()` / `validate_thumbnail_url()` 校验。
- 日志、Issue、提交里不要写真实账号、Cookie、token。

### 3.9 外部服务的礼貌

MusicBrainz 每秒最多 1 次请求（手机端用 `_MB_LOCK` 节流）。LRCLIB 和 YouTube 都可能临时失败，界面要给出可读的原因（`friendlyMessage`）。

---

## 4. 验证

交付前在仓库根目录跑完下面这些（CI 只跑了其中一部分，本地要补全）：

```powershell
python -m unittest test_app -v
python -m unittest discover -s android/app/src/test/python -v
python tests/test_batch_queue.py
python tools/sync_android_assets.py --check
node tests/test_android_search_fallback.js   # tests/ 下 8 个 .js 都要跑，见 CONTRIBUTING.md
cd android; .\gradlew.bat testDebugUnitTest assembleDebug
```

改了界面或 Android 行为时，还要在真机上验证，并在 PR 里写清楚测了什么、没测什么。

**真机调试经验：**

- **无线 adb**：`%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`。在 Git Bash 里要先 `export MSYS_NO_PATHCONV=1`，否则 `/sdcard/...` 会被改写成 Windows 路径。
- **调试版可用 Chrome DevTools 协议**：`adb forward tcp:9333 localabstract:webview_devtools_remote_<pid>`，即可读取和操作页面状态。
- **输入中文环境的手机**：`adb shell input text` 会被拼音输入法吞字，输入后按一次回车（keyevent 66）让原文上屏。
- **调试版和正式版签名不同**，不能互相覆盖安装；为了装正式版而卸载会清空 App 数据。

---

## 5. 发版流程

版本号规则：界面或功能的大更新升第二位（0.2.0 → 0.3.0），修复更新升第三位。

1. 从最新 `master` 切 `release/vX.Y.Z` 分支：改 `versionName`，`versionCode` +1，写 `docs/release-notes/vX.Y.Z.md`，开 PR 合并。
2. 便携版：`build_windows.bat` → `dist/MusicDesk-portable.zip`。解压后冒烟测试：`MusicDesk.exe --port 8765` 能正常提供页面，内置的 yt-dlp、spotdl、Deno 都能运行。
3. Android：`gradlew assembleRelease` 得到未签名包，由作者用 `releases/musicdesk-release.jks` 签名（apksigner 或 Android Studio）。**代理不输入签名密码。**
4. 用 `apksigner verify --print-certs` 核对证书与历史版本一致：`CN=Yap Sheng Pei`，SHA-256 `5a826e425ba008a81add2f0fa861811c25e664aea31056da4a2d86c007553b9b`。证书变了，用户就无法覆盖升级。
5. 在合并后的 `master` 上打 `vX.Y.Z` 标签，用 `gh release create` 发布：附上两个文件，说明末尾附 SHA-256 校验值，并设为 Latest。

---

## 6. 代理工作方式

- **动手前**：先读同类代码再写；涉及签名、局域网鉴权、下载来源校验的改动，先说明方案并等用户确认。
- **改动中**：保持改动聚焦，不顺手重构；不引入新依赖或新框架，确实需要时先征得同意。注释用英文，写清楚**为什么**（沿用现有代码风格）。
- **交付时**：说明测了什么、没测什么（尤其是没能在真机或打包后验证的部分），以及对兼容性的影响。

---

## 7. 已知限制与风险

| 事项 | 说明 |
|---|---|
| 均衡器削波 | 「低音」等加强预设在响亮的歌曲上峰值会超过 1.0，可考虑加前置衰减 |
| 手机息屏播放 | 均衡器走 Web Audio，已在真机验证息屏 26 秒正常；不同厂商的系统可能不同 |
| 外部接口变化 | YouTube 的机器人验证、LRCLIB / MusicBrainz 的数据质量都会变，以实际结果为准 |
| 单文件过大 | `index.html` 约 4200 行（其中约 3360 行是 JS），`app.py` 约 1800 行，`MainActivity.java` 约 1550 行；拆分计划见 `docs/architecture-plan.md` |

# 拆分计划：把大文件按功能解耦

状态：**阶段 1 进行中**。步骤 1a、1b、1c 已完成；继续逐步拆分时更新本文件和 `AGENTS.md` §2。

| 步骤 | 内容 | 状态 |
|---|---|---|
| 1a | 基础设施（`tools/page_assets.py`、自动同步、`web/` 整体打包、测试改读 `page_source()`）+ 样式 → `web/styles.css` + 均衡器 → `web/equalizer.js` | 已完成 |
| 1b | 设置页、电脑连接、双语歌词设置与首次引导 → `web/settings.js` | 已完成 |
| 1c | 公共工具 → `web/core.js`；Android 桥接 → `web/android.js` | 已完成 |
| 1d | 下载页 / 编辑页 / 播放页 → `web/download.js`、`web/editor.js`、`web/player.js` | 待做 |

## 为什么要拆

| 文件 | 行数 | 问题 |
|---|---|---|
| `index.html` | 约 3300 行（页面结构与剩余主脚本；公共工具、Android 桥接、样式、均衡器、设置模块已外拆） | 下载、编辑、播放仍集中在一起；每个 PR 容易冲突，审查难；测试仍有较多源码结构检查 |
| `app.py` | 约 1799 行 | HTTP 路由、元数据检索、歌词、下载、转换、标签封装混在一起 |
| `MainActivity.java` | 约 1550 | WebView 设置、29 个 JS 接口、文件访问、下载保存、媒体服务在同一个类里 |

拆分的收益：
- 改一个功能只动对应文件，PR 更小、冲突更少。
- 测试可以直接加载单个模块做行为测试，不用再在整页源码里找字符串。
- AI 代理和新开发者不必读完 4000 行才能下手。

## 约束（拆的时候不能破坏）

1. **不引入构建步骤。** 页面要能直接从 `file:///android_asset/` 和便携版目录加载。
   - Android WebView 从 `file://` 加载 ES 模块（`type="module"`）会被跨域策略拦截，所以拆出的文件用普通 `<script src>`，按依赖顺序加载，通过少量全局对象通信。
2. **每个新文件都要同步和打包。**
   - 加进 `tools/sync_android_assets.py` 的 `SHARED`，以及 `build_windows.bat` 的 `--add-data`。
   - 现有测试会检查后者；建议顺手让 `SHARED` 也由测试从页面引用的文件自动校验。
3. **行为不变。** 每个阶段都是纯搬移，不改逻辑。
   - 搬移前后跑全部测试，并在真机和便携版上冒烟测试。
   - `test_app.py` 里读取 `index.html` 的结构检查，要改成读取对应的新文件。
4. **一个阶段一个 PR**，从最新的 `master` 切分支，不要把多个阶段攒在一起。

## 阶段

### 阶段 1：页面 JS 拆成功能文件（收益最大）

```
web/
  core.js        # $()、ui()、friendlyMessage、requestMusicDeskApi、shouldProcessOnAndroid 等公共工具
  android.js     # AndroidMusic 的 Promise 封装与 window.onAndroidXxx 回调
  download.js    # 下载页：检索、候选、下载设置、歌单批量下载
  editor.js      # 编辑页：读标签、歌词工具（打点、平移、译文合并）、封装导出
  player.js      # 播放页：曲库、播放列表、迷你播放器、歌词显示
  equalizer.js   # 均衡器
  core.js        # 公共 DOM、文案、API 与文件响应工具
  android.js     # AndroidMusic Promise 桥接
  settings.js    # 设置页、连接电脑、首次引导
styles.css       # 从 <style> 搬出
```

- 先搬 `equalizer.js`、`settings.js` 这类依赖少的，再搬播放器和编辑器。
- **搬移前先查依赖**：要搬的那段代码在顶层（不在函数里）立即调用的函数，必须在它之前已经加载。普通脚本之间，后加载文件里的函数声明，对先执行的文件不可见（同一个 `<script>` 内的函数提升不跨文件）。只在事件里调用的函数不受影响。
- **用脚本验证是纯搬移**：把新文件拼回去，应当与搬移前的 `index.html` 逐行一致（1a 就是这样验证的）。
- `index.html` 最后只保留页面结构和 `<script>` 列表。

### 阶段 2：`app.py` 按职责拆模块

```
desktop/
  server.py      # Handler 与路由分发（/api/* → 各模块函数）
  metadata.py    # MusicBrainz、Spotify、yt-dlp 搜索
  lyrics.py      # LRCLIB（可与手机端共用 musicdesk_core.lyrics 的排序逻辑）
  downloads.py   # yt-dlp / SpotDL 子进程、下载与导出
  tagging.py     # 读写标签、封面处理
```

- `app.py` 保留为兼容入口，`start.bat` 和 PyInstaller 都不用改。
- 顺带把手机端已有的「按实际音频匹配歌词」移到 `musicdesk_core`，电脑端也用上。

### 阶段 3：`MainActivity.java` 拆出 JS 接口与功能类

- `AndroidMusicBridge` 移到独立文件，再按领域拆成几组辅助类：曲库与文件访问、下载与保存、标签与歌词、播放。
- `MainActivity` 只负责 WebView 生命周期和接线。
- Java 单元测试按领域补齐，对照 `LocalMediaRoutesTest` 的写法：纯逻辑放进不依赖 Android 的类。

## 不打算做的

- 不改用前端框架或打包工具（React、Vite 等）。现有页面不需要，还会让 Android 资源和便携版变复杂。
- 不改用 Kotlin / Jetpack Compose 重写 Android 界面。网页一份两用是本项目的核心设计。

# 拆分计划：把大文件按功能解耦

状态：**阶段 1、阶段 2 已完成；阶段 3 进行中**。页面脚本按功能拆分完成；桌面服务按职责迁入 `desktop/`，`app.py` 保留兼容入口；Android 的 JS 接口已迁到独立文件，按领域再拆分的工作待续。

| 步骤 | 内容 | 状态 |
|---|---|---|
| 1a | 基础设施（`tools/page_assets.py`、自动同步、`web/` 整体打包、测试改读 `page_source()`）+ 样式 → `web/styles.css` + 均衡器 → `web/equalizer.js` | 已完成 |
| 1b | 设置页、电脑连接、双语歌词设置与首次引导 → `web/settings.js` | 已完成 |
| 1c | 公共工具 → `web/core.js`；Android 桥接 → `web/android.js` | 已完成 |
| 1d | 下载页 / 编辑页 / 播放页 → `web/download.js`、`web/editor.js`、`web/player.js` | 已完成 |

### 阶段 2 进度：桌面服务解耦

| 步骤 | 内容 | 状态 |
|---|---|---|
| 2a | HTTP Handler 与路由 → `desktop/server.py`；保留 `app.Handler` 和 `app.*` 测试替换点 | 已完成 |
| 2b | MusicBrainz、Spotify、yt-dlp 元数据查询 → `desktop/metadata.py`；保留 `app.py` 函数兼容包装 | 已完成 |
| 2c | LRCLIB 歌词查询 → `desktop/lyrics.py`；保留 `app.py` 函数兼容包装 | 已完成 |
| 2d | yt-dlp / SpotDL 下载与格式导出 → `desktop/downloads.py`；保留 `app.py` 函数兼容包装 | 已完成 |
| 2e | 本地标签读写与封面处理 → `desktop/tagging.py`；保留 `app.py` 函数兼容包装 | 已完成 |

### 阶段 3 进度：`MainActivity.java` 解耦

| 步骤 | 内容 | 状态 |
|---|---|---|
| 3a | `AndroidMusicBridge`（29 个 `@JavascriptInterface` 方法）移到独立文件 `AndroidMusicBridge.java`，持有 `MainActivity host` 引用；`MainActivity` 里被它调用的字段/方法从 `private` 放宽为包内可见 | 已完成 |
| 3b | 按领域把 `AndroidMusicBridge` 和 `MainActivity` 里相关的顶层私有方法（曲库扫描、保存到文档等）再拆成几组协作类：曲库与文件访问、下载与保存、标签与歌词、播放 | 待做 |
| 3c | 把其中不依赖 Android API 的纯逻辑单独抽出并补 JUnit 测试（参照 `LocalMediaRoutesTest`） | 待做 |

## 为什么要拆

| 文件 | 行数 | 问题 |
|---|---|---|
| `index.html` | 约 484 行（页面结构和脚本清单） | 页面结构仍包含较多模板 HTML，但交互逻辑已按功能拆入普通脚本 |
| `app.py` | 约 374 行 | HTTP、元数据、LRCLIB、下载与标签功能已迁出；保留兼容包装、服务配置、运行时工具和 CLI |
| `MainActivity.java` | 约 857 行 | JS 接口已迁到 `AndroidMusicBridge.java`（约 737 行）；`MainActivity` 仍负责 WebView 设置、文件访问、下载保存和媒体服务的接线 |

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
  download.js    # 在线检索、下载设置、试听、批量下载
  editor.js      # 本地转换、标签编辑、歌词工具与封装
  player.js      # 曲库、播放队列、播放器与恢复逻辑
  core.js        # 公共 DOM、文案、API 与文件响应工具
  android.js     # AndroidMusic Promise 桥接
  settings.js    # 设置页、连接电脑、首次引导
  equalizer.js   # 均衡器
styles.css       # 从 <style> 搬出
```

- 先搬 `equalizer.js`、`settings.js` 这类依赖少的，再搬播放器和编辑器。
- **搬移前先查依赖**：要搬的那段代码在顶层（不在函数里）立即调用的函数，必须在它之前已经加载。普通脚本之间，后加载文件里的函数声明，对先执行的文件不可见（同一个 `<script>` 内的函数提升不跨文件）。只在事件里调用的函数不受影响。
- **用脚本验证是纯搬移**：把新文件拼回去，应当与搬移前的 `index.html` 逐行一致（1a 就是这样验证的）。
- `index.html` 最后只保留页面结构和 `<script>` 列表。

### 阶段 2：`app.py` 按职责拆模块

```
desktop/
  server.py      # Handler 与路由分发（/api/* → 各模块函数，已迁移）
  metadata.py    # MusicBrainz、Spotify、yt-dlp 搜索（已迁移）
  lyrics.py      # LRCLIB（已迁移；可与手机端共用 musicdesk_core.lyrics 的排序逻辑）
  downloads.py   # yt-dlp / SpotDL 子进程、下载与导出（已迁移）
  tagging.py     # 读写标签、封面处理（已迁移）
```

- `app.py` 保留为兼容入口，`start.bat` 和 PyInstaller 都不用改。
- 顺带把手机端已有的「按实际音频匹配歌词」移到 `musicdesk_core`，电脑端也用上。

### 阶段 3：`MainActivity.java` 拆出 JS 接口与功能类

- `AndroidMusicBridge` 移到独立文件（已完成，3a）：
  - 构造函数持有 `MainActivity host`；`host.` 前缀的用法替代了内部类原来对外层字段/方法的隐式访问。
  - `MainActivity` 中被它调用的字段、方法、常量从 `private` 放宽为包内可见（去掉 `private` 关键字，不是 `public`——仍只有同包能访问）。
  - **搬移方式**：用脚本精确提取内部类的原始文本，对已知的外层标识符列表做定向加前缀替换（`host.xxx` / `MainActivity.xxx`），再整体粘贴进新文件——不是逐行手改。Java 是静态类型语言，任何遗漏或改错的引用在编译期就会报错（这次实测抓到了一处漏改的继承常量 `MODE_PRIVATE`），这比动态语言的拆分更有把握。
  - `test_app.py` 里凡是读取 `MainActivity.java` 内容做结构检查的地方，统一改成读取 `MainActivity.java + AndroidMusicBridge.java` 拼接文本（同 `app.py + desktop/server.py` 的做法）。
- 再按领域把 `AndroidMusicBridge` 和 `MainActivity` 里相关的顶层私有方法拆成几组协作类：曲库与文件访问、下载与保存、标签与歌词、播放（3b，待做）。
- 把其中不依赖 Android API 的纯逻辑单独抽出并补 JUnit 测试，参照 `LocalMediaRoutesTest` 的写法（3c，待做）。注意：`AndroidMusicBridge` 里几乎所有方法都直接调用 `ContentResolver`、`DocumentsContract`、`FFmpegKit`、`Python`/Chaquopy 等 Android/第三方 API，真正可以抽成零 Android 依赖纯函数的逻辑不多，不要为了"看起来分得细"而强行拆。
- `MainActivity` 最终只负责 WebView 生命周期和接线；曲库扫描、保存到文档等目前仍是 `MainActivity` 的顶层私有方法（被 `onActivityResult` 和 `AndroidMusicBridge` 共用），3b 要连这部分一起挪，不能只挪 `AndroidMusicBridge`。

## 不打算做的

- 不改用前端框架或打包工具（React、Vite 等）。现有页面不需要，还会让 Android 资源和便携版变复杂。
- 不改用 Kotlin / Jetpack Compose 重写 Android 界面。网页一份两用是本项目的核心设计。

# MusicDesk

> 一站式本地音乐播放器 + 元数据检索 + 音频格式转换 + 自定义标签封装工具
>
> 纯本地服务（Python 后端 + Web 前端），支持 Windows 原生窗口和 Android 移动端。

[![Release](https://img.shields.io/github/v/release/shengpeiyap/music_downloader?label=最新%20Release)](https://github.com/shengpeiyap/music_downloader/releases)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-42%20passed-brightgreen)](#tests)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Android%20%7C%20macOS%2FLinux-lightgrey)](#)

---

## ✨ 功能亮点

### 🎧 本地播放器
- 拖拽导入、文件选择两种方式添加本地音频到播放列表
- 自定义播放控件：上一首 / 播放暂停 / 下一首 / 进度条 / 时间显示
- 顺序播放、单曲循环、列表循环、**随机播放**四种模式
- 播放队列可拖拽排序，支持单独删除或清空
- 内嵌 LRC 同步歌词 + 纯文本歌词两种渲染模式，支持显示内嵌封面

### 🔎 在线元数据检索
- 粘贴 **Spotify 单曲**或 **YouTube / YouTube Music** 分享链接，自动读取
  - 歌曲标题、艺人、专辑、年份、缩略图封面
  - （Spotify 通过 oEmbed + Embed 双源互补解析；YouTube 通过 yt-dlp 读 rich metadata）
- 关键词搜索：只需输入 `艺人 - 标题` 或仅标题，通过
  - **MusicBrainz** 公库获取专辑 / 年份 / Cover Art Archive 封面
  - **LRCLIB** 公库检索同步 LRC 歌词
  - 歌词库信息回填 MusicBrainz 检索不到的艺人/专辑

### ⬇️ 双引擎下载（可选功能）
- 支持 yt-dlp（YouTube 搜索/直链）和 SpotDL（Spotify 曲库）双引擎，自动降级重试
- 链接下载：粘贴 Spotify / YouTube 分享 URL
- 关键词下载：在搜索栏填 `艺人 - 标题` → 直接转成关键词搜索下载
- 自动下载 YouTube 缩略图并**智能裁剪四周黑色/白色 padding** 作为最终封面
- 输出统一为带 ID3 标签的 MP3（内嵌标题/艺人/专辑/年份/LRC 歌词/封面）

### 🔄 音频格式转换
- 拖拽上传本地音频，选择目标格式一键转换
- 支持：`MP3` / `WAV` / `FLAC` / `OGG` / `M4A`
- 自动调用 imageio-ffmpeg 自带的 FFmpeg，无需系统安装

### 🏷️ 自定义标签编辑器 & 封装导出
- 读取本地音频现有标签（标题/艺人/专辑/年份/歌词/多封面）
- 或通过关键词搜索一键回填 MusicBrainz + LRCLIB 信息
- 支持自定义封面图上传、内嵌歌词编辑
- **无本地音频时自动调用下载引擎先获取音频**，再写入所选标签并输出
- 输出文件名自动按 `艺人 - 标题 [附加文本].格式` 规范化

### 📱 Android 移动端 (WebView App)
- 构建见 [android/](android/) 目录，minSdk 23 / targetSdk 35 / compileSdk 36
- 支持：本地音频多选 / **文件夹递归导入**（保存权限后自动重扫）
- Library / Now Playing 双视图，按 **歌曲/艺人/专辑/文件夹/收藏** 过滤
- 可拖拽队列 Sheet + Mini Player，顺序/单曲循环/列表循环/随机播放
- 大文件夹智能分批扫描（chunk 100）、封面按需解码缩放，内存友好
- **远程连接桌面 MusicDesk LAN API**：输入电脑 LAN IP + 一次性配对密钥 →
  在 Android 中即可调用桌面的在线元数据、歌词、下载、格式转换、自定义标签封装

> Android 端音频播放完全本机；**涉及网络检索、下载、格式转换的功能需要桌面上的 MusicDesk 服务在同一信任 Wi-Fi 下打开。**

---

## ⚠️ 版权与合规声明

- MusicDesk **仅**提供以下两种合法用途的辅助：
  1. 处理**您自己拥有版权或被授权处理**的本地音频文件
  2. 检索公开元数据数据库（MusicBrainz / LRCLIB / Spotify oEmbed / YouTube oEmbed）中的
     **公开描述信息**（不含流媒体传输）
- 通过 yt-dlp / SpotDL 等第三方工具下载音频时，**请确保您拥有对应的使用权利**，并遵守
  各平台的服务条款与所在地区的版权法。
- 所有上传到本工具的音频仅在本机临时目录处理，下载/转换完成后临时文件自动删除。

---

## 📥 快速开始

### 方式一：下载发行版（推荐，开箱即用）

前往 [GitHub Releases](https://github.com/shengpeiyap/music_downloader/releases) 下载：

| 平台 | 文件名 | 说明 |
|---|---|---|
| 🪟 Windows | `MusicDesk-v0.1.0-windows-portable.zip` | 解压后双击 `MusicDesk.exe` 以**原生桌面窗口**启动（Edge WebView2）；如无 WebView2 可使用 `MusicDesk.exe --browser` 在系统默认浏览器打开。已内封 FFmpeg / yt-dlp / SpotDL |
| 🤖 Android | `MusicDesk-v0.1.0-android-release.apk` | 安装到手机，需允许"从未知来源安装"；如需连接桌面功能请在桌面端用 LAN 模式启动 |

### 方式二：Windows 从源码启动
1. 安装 Python **3.10 或更新版本**（建议 3.12+）
2. 双击 `start.bat`
   - 首次运行自动创建 `.venv` 并安装全部依赖（含 imageio-ffmpeg，自带 FFmpeg 二进制，无需手动配置 PATH）
   - 需要联网
3. 浏览器或原生窗口自动打开 <http://127.0.0.1:8765>

### 方式三：macOS / Linux 从源码启动
```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```
然后访问 <http://127.0.0.1:8765>。

### 🖥️ 构建原生 Windows 便携包
```cmd
start.bat                 :: 先完成一次普通启动（安装运行时依赖）
build_windows.bat         :: 构建 dist\MusicDesk-portable.zip
```
产物：
- `dist\MusicDesk\MusicDesk.exe` → **强制以 Microsoft Edge WebView2 原生窗口启动**（不再自动回退浏览器；如缺少 WebView2 运行时会弹出安装指引对话框并退出，或手动加 `--browser` 参数改为系统浏览器打开）
- `dist\MusicDesk\yt-dlp.exe`、`dist\MusicDesk\spotdl.exe` → 打包的下载引擎可执行文件
- `dist\MusicDesk-portable.zip` → 完整便携压缩包（可直接分发，**约 144 MB**）
> 命令行额外参数：
> - `MusicDesk.exe --browser`  不使用原生窗口，改用系统默认浏览器打开（类似 start.bat 体验）
> - `MusicDesk.exe --lan --token 自定义密钥`  允许同局域网其他设备访问（与 start_lan.bat 一致）
> - `MusicDesk.exe --port 8765`  手动指定 HTTP 端口

### 📱 构建 Android APK
前置：JDK 17、Android SDK Platform 36。
```sh
cd android
./gradlew assembleRelease       # Windows 用 gradlew.bat
```
输出：`android/app/build/outputs/apk/release/app-release-unsigned.apk`
> 当前 `android/app/build.gradle.kts` 配置的是 **unsigned release**。要上架应用商店请自行用正式 Keystore 做 `jarsigner` / `apksigner` 签名。

---

## 🌐 手机连接桌面 LAN API（Android 在线功能解锁）

1. 桌面端：双击 `start_lan.bat`（或命令行 `python app.py --lan`）
   - 终端会显示本机在局域网中的 IP（如 `http://192.168.1.7:8765`）和一个**一次性配对密钥**
2. Windows 防火墙提示时，**允许专用网络访问**
3. 手机与电脑连接**同一信任 Wi-Fi**
4. 打开 Android App → 在线解析 Tab → 填入电脑的 LAN IP + 配对密钥 → 点连接
5. 成功后：元数据检索 / 歌词 / 下载 / 格式转换 / 自定义标签封装全部解锁

> 🔐 **安全提醒**：`--lan` 模式下远端仅能调用带 `Authorization: Bearer <token>` 的 JSON API，无法访问桌面浏览器 UI 页面。令牌每次启动随机生成，可在专用私有 Wi-Fi 下安全使用。请勿暴露到公网。

---

## 🧪 测试

```sh
python -m unittest discover -v
# 或指定文件
python -m unittest test_app -v
```

当前状态：**42 passed ✅**
覆盖模块：FFmpeg 查找、桌面启动器、便携打包、本地标签元数据、HTML 前端完整性、Android asset 同步、关键词与链接元数据、Spotify/YouTube URL 解析、歌词库检索、媒体下载调度、LAN API 鉴权与 CORS、智能封面 padding 裁剪、导出处理。

---

## 🗂️ 目录结构速览

```
music_downloader/
├── app.py                      # Python 后端：HTTP 服务、元数据/歌词检索、下载/转换/标签
├── launcher.py                 # 桌面原生窗口入口（pywebview + 浏览器回退）
├── index.html                  # 整个前端页面（播放器 / 检索 / 转换 / 标签 / Android UI）
├── test_app.py                 # 42 个单元测试
├── spotdl_launcher.py / yt_dlp_launcher.py  # 打包为独立 exe 时的入口
├── package_portable.py         # PyInstaller onedir → portable.zip
├── build_windows.bat           # Windows 一键构建脚本
├── start.bat / start_lan.bat   # 普通启动 / LAN 模式启动
├── requirements.txt / requirements-build.txt
├── default_song_img.png / icon.ico
├── LICENSE                     # MIT License
└── android/                    # Android WebView 工程（Gradle）
    └── app/src/main/
        ├── java/com/musicdesk/android/MainActivity.java
        ├── AndroidManifest.xml
        └── assets/index.html  ← 与根目录 index.html 保持同步（构建测试会校验）
```

---

## 📄 License

[MIT License](LICENSE) · Copyright (c) 2026 shengpeiyap

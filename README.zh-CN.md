# MusicDesk

> 面向 Windows 与 Android 的本地音乐库、播放器、元数据与歌词工具。项目处于早期开发阶段，接口和功能可能变化。
>
> [English](README.md) · 简体中文

[![CI](https://github.com/shengpeiyap/music_downloader/actions/workflows/ci.yml/badge.svg)](https://github.com/shengpeiyap/music_downloader/actions/workflows/ci.yml)
[![最新发行版](https://img.shields.io/github/v/release/shengpeiyap/music_downloader)](https://github.com/shengpeiyap/music_downloader/releases)
[![许可证：MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

MusicDesk 将本地播放、歌曲信息检索、歌词处理、音频转换和标签封装放在一个应用中。Windows 桌面端由 Python 服务和网页界面构成；Android 使用原生应用外壳与 WebView，并通过 Chaquopy 运行部分 Python 逻辑。在线服务依赖网络及对应数据源可用性。

**项目状态：**早期开发，功能与接口仍可能变化。升级前请查看对应发行说明；报告问题时请按模板提供可复现步骤和环境信息。

## 功能

- 本地音乐库和播放器：播放队列、搜索、收藏、播放模式与歌词显示。
- 元数据与歌词检索：支持公开数据源以及 YouTube / Spotify 分享链接的公开信息解析。
- 音频处理：转换为 MP3、WAV、FLAC、OGG 或 M4A；编辑元数据、封面及歌词，并导出音频。
- 下载：桌面端可使用 yt-dlp 与 SpotDL；Android 的能力和格式取决于本机依赖或已连接的桌面服务。
- Android 文件夹导入和播放；连接桌面端后可通过局域网使用部分桌面处理功能。

不同容器对封面、标签和同步歌词的支持并不完全相同。第三方网站、网络策略和媒体格式变化也可能影响解析或下载。

## 下载

请从 [GitHub Releases](https://github.com/shengpeiyap/music_downloader/releases) 获取当前发行版。每个版本的文件、平台和已知限制以对应发行说明为准。Debug 构建仅供测试，不是正式发行版。

## 从源码运行

### Windows 桌面端

需要 Python 3.12 或更新版本。在仓库根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

随后访问 <http://127.0.0.1:8765>。也可使用仓库提供的 `start.bat`。

### Android

需要 JDK 17、Android SDK Platform 36 和 Python 3.14（Chaquopy 构建依赖）。在仓库根目录运行：

```powershell
cd android
.\gradlew.bat assembleDebug
```

Release 构建请参考 Gradle 配置和对应发行说明。不要提交个人签名密钥或密码。

## 局域网连接与隐私

桌面端默认只监听本机回环地址。LAN 模式用于可信的私人 Wi-Fi，并要求访问令牌。不要将服务端口暴露到互联网或不可信网络；连接前请核对设备地址和配对令牌。

本地音频由应用在设备上处理。检索、下载和歌词等在线功能会按用户操作访问对应的第三方服务；启用 Android 到桌面端的 LAN 连接时，请将电脑视为该处理请求的服务端。请先阅读各数据源和第三方工具的隐私政策及服务条款。

## 测试

在仓库根目录安装 `requirements.txt`，并准备 Node.js 20 后运行：

```powershell
python -m unittest test_app -v
python -m unittest discover -s android/app/src/test/python -v
node tests/test_android_search_fallback.js
node tests/test_android_processing_route.js
node tests/test_android_ui_gates.js
node tests/test_library_sort.js
```

Android Java 编译由 GitHub Actions 检查；本地可在 `android` 目录运行 `gradlew.bat assembleDebug`。测试数量以当前 CI 结果为准，不在 README 中固定写死。

## 贡献与安全

欢迎提交问题报告和改进。请阅读 [贡献指南](CONTRIBUTING.md)、[行为准则](CODE_OF_CONDUCT.md) 和 [安全政策](SECURITY.md)。漏洞请通过 GitHub Security 页面私下报告，不要公开发布在普通 Issue 中。

## 第三方组件与许可证

MusicDesk 源码按 [MIT License](LICENSE) 发布。项目使用的 Python、Android 和媒体处理依赖各自遵循其许可证；发行包中的第三方二进制也受各自许可证约束。分发或修改发行包前，请查看对应依赖的许可与声明。MusicDesk 与 YouTube、Spotify、MusicBrainz、LRCLIB 或其他第三方平台没有隶属关系。

## 版权与使用责任

请仅处理你拥有或获准使用的音频，并遵守所在地法律以及第三方网站和工具的服务条款。MusicDesk 不提供版权授权，也不保证任何外部来源始终可用。

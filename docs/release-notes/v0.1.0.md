# MusicDesk v0.1.0 发行说明

🎉 **MusicDesk 第一个正式版本发布！**

MusicDesk 是一套三端一体的音乐元数据与音频工具箱：
- **Web 前端 + Python 后端**（本地 HTTP 服务，可在任何浏览器中打开）
- **Windows 原生窗口桌面应用**（WebView2，无需浏览器）
- **Android 移动应用**（WebView 封装本地播放器 + 可联网调用桌面 LAN API）

---

## 📦 下载地址

| 平台 | 文件名 | 大小 | 校验 |
|---|---|---|---|
| 🪟 Windows (便携版) | `MusicDesk-v0.1.0-windows-portable.zip` | ≈144 MB | 解压后双击 `MusicDesk.exe` 即开即用 |
| 🤖 Android | `MusicDesk-v0.1.0-android-release.apk` | ≈670 KB | unsigned release，安装时允许未知来源即可 |

> 💡 若发行页面没有看到 Windows 便携包 ZIP，说明该文件超过 Git 仓库单文件 100MB 上限未能自动同步——您仍可
> 在仓库根目录通过 `build_windows.bat` 一键构建（产物位于 `dist/MusicDesk-portable.zip`）。

---

## ✨ v0.1.0 新功能

### 🌐 Web + 后端 双模块
1. **本地音频播放器**
   - 拖拽 / 文件选择 / 多选一次性导入
   - 播放队列（可拖拽排序、单条删除、清空）
   - 四种播放模式：顺序 / 单曲循环 / 列表循环 / 随机
   - 内嵌封面显示，内嵌 LRC 同步歌词 + 纯文本歌词双模式渲染
2. **元数据检索**
   - 粘贴 Spotify 单曲 / YouTube / YouTube Music 分享链接 → 自动读标题/艺人/专辑/年份/封面
   - 关键词搜索 `艺人 - 标题` 或 `标题` → MusicBrainz + LRCLIB 双公库联合检索
   - 检索结果回填封面/歌词/专辑/年份
3. **双引擎下载（yt-dlp + SpotDL）**
   - 链接下载 / 关键词下载双模式，失败自动降级到另一引擎
   - YouTube 缩略图自动智能裁剪四周 padding 做封面
   - 输出 MP3 带完整 ID3v2 标签（标题/艺人/专辑/年份/LRC 歌词/封面）
4. **格式转换器**
   - 本地音频 → MP3 / WAV / FLAC / OGG / M4A
   - imageio-ffmpeg 自带 FFmpeg，无需系统级安装
5. **自定义标签编辑器 / 封装导出**
   - 本地音频读取 + 公库搜索回填
   - 可选自定义封面图、内嵌歌词
   - 若未选本地音频，会自动先用下载引擎拉取音频 → 写标签 → 输出
   - 规范化文件名 `艺人 - 标题 [后缀].格式`

### 🪟 Windows 桌面应用
- 通过 PyInstaller 封装为 onedir：`MusicDesk.exe`
- **默认强制以 Microsoft Edge WebView2 原生窗口启动**（不再自动回退到外部浏览器）
- 若本机未安装 WebView2 运行时，会弹出带下载链接的错误对话框，并提供 `MusicDesk.exe --browser` 作为备选启动方式
- 支持命令行参数：`--browser`（改用系统默认浏览器）、`--lan` / `--token` / `--port`（局域网模式/自定义密钥/自定义端口）
- 窗口标题栏与任务栏图标已使用 `icon.ico`，并设置窗口最小尺寸 (800x600) 与暗色背景
- 内封 yt-dlp.exe、spotdl.exe、FFmpeg，全部开箱即用
- 下载/转换通过系统"另存为"对话框选择保存位置

### 🤖 Android 应用
- minSdk 23（Android 6.0+）/ targetSdk 35 / compileSdk 36
- 本地功能（不需联网）
  - 多音频选择 / 文件夹递归导入（持久化保存的文件夹，启动自动重扫）
  - Library / Now Playing 双 Tab；Mini Player；可拖拽队列 Sheet
  - 按 歌曲 / 艺人 / 专辑 / 文件夹 / 收藏 过滤
  - 顺序 / 单曲循环 / 列表循环 / 随机播放
  - 大文件夹分批扫描 + 封面按需解码缩放，兼顾流畅与内存
  - 曲库索引在本机缓存；重新打开先恢复上次列表，再按文件修改时间复用未变化歌曲的标签
  - 通知栏、锁屏和兼容蓝牙耳机支持播放 / 暂停 / 上一首 / 下一首
  - 锁定应用 WebView 缩放；播放列表和“播放全部”弹层支持下滑收起
- 在线功能（需连接同 Wi-Fi 下的桌面 MusicDesk LAN API）
  - 元数据检索 / 歌词 / 下载 / 格式转换 / 自定义标签封装
  - 使用一次性 Bearer Token 配对鉴权；远端仅暴露 JSON API，看不到桌面 UI

---

## 🐛 Bug 修复
- **[fix] crop_yt_padding_smart 左右边界检测循环变量覆盖**
  - 左右 padding 裁剪时，内层 `for x in range(...)` 意外覆盖外层列号 `x` 并使用未定义的 `y`
  - 修复：内层改用 `for y in range(0, sq_h, 5)`，横向裁剪现在与纵向裁剪一致正确
  - 新增 3 个 SmartPaddingCropTests 单元测试覆盖

---

## ✅ 质量 & 测试

```
Ran 45 tests
OK
```

测试覆盖：FFmpeg 查找、桌面 launcher、便携打包路径、HTML 前端完整性、Android asset 同步、关键词/链接元数据、Spotify/YouTube URL 解析、歌词库检索、下载引擎调度、LAN API 鉴权/CORS、智能封面 padding 裁剪、ID3 导出与清理。

---

## 🚀 快速上手指南

### Windows 用户
1. 下载 `MusicDesk-v0.1.0-windows-portable.zip`，解压到任意目录
2. 双击 `MusicDesk.exe`，程序会在自己的 WebView2 原生窗口中打开
3. 如果提示缺少 WebView2，请按错误对话框中的链接安装运行时；只有显式启动 `MusicDesk.exe --browser` 才会改用默认浏览器
4. （可选，手机联动）关闭后重新双击 `start_lan.bat` → 进入 LAN 模式

### Android 用户
1. 安装 `MusicDesk-v0.1.0-android-release.apk`（允许"从未知来源安装"）
2. 在「本地」Tab 选音频或导入文件夹 → 直接播放
3. （在线功能）桌面端用 `start_lan.bat` 启动 → 记下 IP + 一次性密钥
   → Android「在线解析」Tab 填入 → 连接成功后可下载/检索/转换

### 源码启动（macOS / Linux / 开发者）
```sh
git clone https://github.com/shengpeiyap/music_downloader.git
cd music_downloader
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py        # 浏览器打开 http://127.0.0.1:8765
```

---

## 📝 合规与版权提示
- MusicDesk 只处理您拥有版权或被授权的本地音频文件
- 通过 yt-dlp / SpotDL 下载音频时，请遵守对应平台 ToS 与您所在地区版权法
- 所有上传音频仅在本机临时目录处理，完成后自动删除

---

🙏 欢迎在 [Issues](https://github.com/shengpeiyap/music_downloader/issues) 提 Bug 与建议！

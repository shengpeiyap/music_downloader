# MusicDesk

一个在本机运行的音乐 metadata 查看与音频格式转换工具。

## 功能

- 读取 Spotify 单曲及 YouTube Music / YouTube 视频分享链接的公开 metadata（标题、发布者和缩略图）。
- 将本地音频转换为 MP3、M4A、FLAC、WAV 或 OGG。
- 不从 Spotify 或 YouTube Music 下载受版权保护的音频。请仅转换你拥有或获准处理的文件。
- 上传文件只在本机临时目录处理；转换结束后临时目录自动清理。

## 运行

需要 Python 3.10+。音频转换需要安装 FFmpeg，并确保 `ffmpeg` 命令可从 PATH 使用。

```powershell
python app.py
```

打开 <http://127.0.0.1:8765>。metadata 查询需要互联网连接；转换完全在本机运行。

## 验证

```powershell
python -m unittest -v
```

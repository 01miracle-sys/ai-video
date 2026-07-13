# 🎬 AI Video Learning Assistant

一个**一键式视频学习助手** —— 把网课、讲座、会议视频丢进去，自动帮你：
- 📝 转成文字（中文）
- 📊 生成结构化的学习笔记
- 🔥 烧录字幕回视频

全程本地运行，**不联网、不上传**，保护你的隐私。

---

## ✨ 能做什么？

| 功能 | 说明 |
|------|------|
| **语音识别** | 用 `faster-whisper` 把视频语音转成中文字幕和文本，支持 CPU 运行，无需 GPU |
| **AI 笔记** | 用 `Ollama` 本地大模型，把转写文字整理成结构化笔记（标题 + 要点 + 总结） |
| **字幕烧录** | 用 `FFmpeg` 把字幕嵌入视频，生成带字幕的 MP4 |
| **统一入口** | 一条命令搞定全部，自动判断你是视频还是文本 |

---

## 🏗️ 项目架构

```
ai-video/
├── main.py                    # 统一入口，一条命令搞定全部
├── config/
│   └── settings.yaml          # 配置文件（模型、字体、质量等）
├── src/
│   ├── asr/transcriber.py     # 语音识别（faster-whisper）
│   ├── notes/generator.py     # 笔记生成（Ollama）
│   ├── subtitle/burner.py     # 字幕烧录（FFmpeg）
│   └── utils/file_utils.py    # 工具函数
├── outputs/                     # 输出目录（字幕、文本、笔记）
├── tests/                       # 测试文件
├── requirements.txt            # Python 依赖
└── scripts/run.bat             # Windows 批处理快捷入口
```

---

## 🚀 快速开始（5 分钟搞定）

### 第 0 步：准备环境

需要提前安装以下软件：

| 软件 | 作用 | 下载地址 |
|------|------|----------|
| **Python** ≥ 3.9 | 运行本项目 | [python.org](https://www.python.org/downloads/) |
| **Ollama** | 本地运行大模型 | [ollama.com](https://ollama.com/) |
| **FFmpeg** | 视频/字幕处理 | [ffmpeg.org](https://ffmpeg.org/download.html) |

> 💡 安装后，在命令行输入 `python --version`、`ollama --version`、`ffmpeg -version` 能显示版本号，说明装好了。

### 第 1 步：下载项目

打开终端（Win+R → 输入 `cmd`），执行：

```bash
git clone https://github.com/01miracle-sys/ai-video.git
cd ai-video
```

### 第 2 步：安装 Python 依赖

```bash
pip install -r requirements.txt
```

> 如果遇到权限问题，加上 `--user`：`pip install -r requirements.txt --user`

### 第 3 步：下载 AI 模型（只需一次）

```bash
ollama pull deepseek-r1
```

> 这是一个 3B 参数的中文模型，约 2GB，速度快、效果够用。电脑好的话可以用 `qwen2.5:7b`（7GB）。

### 第 4 步：运行！

把视频放在 `tests/` 文件夹下，然后执行：

```bash
python main.py tests/你的视频.mp4
```

程序会自动帮你：
1. 转文字 → 保存到 `outputs/`
2. 生成笔记 → 保存到 `outputs/`

全部搞定！

---

## 📖 使用指南

### 基础用法

```bash
# 全流程：转文字 + 生成笔记
python main.py 视频.mp4

# 全流程 + 烧录字幕到视频
python main.py 视频.mp4 --burn

# 只转文字，不生成笔记
python main.py 视频.mp4 --no-notes

# 用更强的模型生成笔记
python main.py 视频.mp4 --model qwen2.5:7b

# 已有文字，直接生成笔记
python main.py outputs/字幕.txt
```

### 输出文件

运行后 `outputs/` 目录下会有：

| 文件 | 说明 |
|------|------|
| `*.txt` | 完整语音转文字 |
| `*.srt` | 带时间轴的字幕文件 |
| `*_notes.txt` | AI 生成的结构化学习笔记 |
| `*_burned.mp4` | 带字幕烧录的视频（用了 `--burn` 时） |

---

## ⚙️ 配置文件

打开 `config/settings.yaml` 可以调整：

```yaml
asr:
  model_size: small          # 模型：tiny（快）→ large（准）
  device: cpu                # 用 CPU 还是 GPU
  compute_type: int8         # 量化精度

notes:
  model: "deepseek-r1"        # 笔记模型
  temperature: 0.3           # 创意度（0=严谨，1=自由）

subtitle:
  font: "Microsoft YaHei"    # 字幕字体
  font_size: 18              # 字体大小
  crf: 23                    # 视频质量（0=无损，51=最差）
```

---

## 🐢 常见问题

### 1. 第一次运行慢？

正常！第一次会自动下载 `faster-whisper` 模型（约 1GB），下载到缓存后下次飞快。

### 2. 运行报 `Ollama connection refused`？

先启动 Ollama 服务：

```bash
ollama serve
```

然后**新开一个终端**运行 `main.py`。

### 3. 视频没有字幕？

检查一下 `outputs/` 目录下的 `.srt` 文件是否存在。如果存在，说明转文字成功了，只是没烧录 —— 用 `--burn` 参数再跑一次。

### 4. 笔记是英文的？

确保 `config/settings.yaml` 里 `asr.language` 是 `zh`，并且下载了中文模型（如 `deepseek-r1`）。

### 5. 内存不够？

把 `asr.model_size` 改成 `tiny` 或 `base`，或者减小 `notes.chunk_size`。

---

## 📝 技术栈

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — 语音识别（CPU 友好）
- [Ollama](https://ollama.com/) — 本地大模型运行
- [FFmpeg](https://ffmpeg.org/) — 视频处理
- Python 3.9+

---

## 🤝 贡献

如果你发现 bug 或有新想法，欢迎：
1. Fork 本仓库
2. 创建你的分支 `git checkout -b feature/xxx`
3. 提交更改 `git commit -m 'Add some feature'`
4. 推送到分支 `git push origin feature/xxx`
5. 发起 Pull Request

---

## 📄 License

MIT License — 自由使用，商用也没问题。

---

> 🎉 祝你学习效率翻倍！

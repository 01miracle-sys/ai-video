# AI Video Learning Assistant — 项目记忆

## 项目概况
- 项目：AI Video Learning Assistant（视频学习工具）
- 位置：E:\AI-Video
- 核心链路：视频 → faster-whisper ASR → TXT/SRT → Ollama 笔记
- 技术栈：faster-whisper (CPU int8) + Ollama (qwen2.5:3b) + FFmpeg
- 硬件约束：无 GPU、16GB 内存

## 关键约定
- 统一入口：`python main.py`，自动识别输入类型
- 输出目录：`outputs/`
- 配置：`config/settings.yaml`
- 模块化结构：`src/asr/`、`src/notes/`、`src/subtitle/`、`src/utils/`

## 历史里程碑
- 2026-07-11：创建开发文档、规范、流程、项目规划看板
- 2026-07-13：项目目录重构、模块化、字幕烧录模块、统一入口

"""
AI Video Learning Assistant — 统一入口

一键完成"视频转文字 → 生成字幕 → AI 笔记 → 字幕烧录"全流程。

用法:
    python main.py video.mp4                              # 全流程：转文字 + 生成笔记
    python main.py video.mp4 --no-notes                    # 仅转文字，不生成笔记
    python main.py video.mp4 --burn                        # 转文字 + 烧录字幕 + 生成笔记
    python main.py outputs/test.txt                        # 已有 TXT，仅生成笔记
    python main.py outputs/test.txt --model qwen2.5:7b     # 指定模型生成笔记
"""

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI Video Learning Assistant — 视频学习工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python main.py video.mp4             全流程\n"
            "  python main.py video.mp4 --burn      全流程 + 字幕烧录\n"
            "  python main.py output/test.txt       仅生成笔记\n"
        ),
    )
    parser.add_argument("input", help="视频文件 (.mp4/.avi/.mkv) 或 TXT 文件")
    parser.add_argument(
        "--model",
        default=None,
        help="Ollama 模型名 (默认: settings.yaml 中的配置)",
    )
    parser.add_argument(
        "--burn",
        action="store_true",
        help="同时烧录字幕到视频",
    )
    parser.add_argument(
        "--no-notes",
        action="store_true",
        help="跳过笔记生成，仅做语音识别",
    )
    parser.add_argument(
        "--asr-model",
        default=None,
        help="ASR 模型大小 (tiny/base/small/medium/large)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 文件不存在: {args.input}")
        sys.exit(1)

    # ─── 判断输入类型 ────────────────────────────
    video_extensions = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"}
    is_video = input_path.suffix.lower() in video_extensions

    # ─── 视频 → 语音识别 ────────────────────────
    txt_path: Path | None = None
    srt_path: Path | None = None

    if is_video:
        print("=" * 50)
        print("🎬 阶段 1/3: 语音识别")
        print("=" * 50)

        from src.asr.transcriber import WhisperTranscriber

        asr_model = args.asr_model or "small"
        transcriber = WhisperTranscriber(model_size=asr_model)
        result = transcriber.transcribe(input_path)

        txt_path = result.txt_path
        srt_path = result.srt_path
    else:
        # 直接使用 TXT 文件
        txt_path = input_path
        # 查找同名的 SRT 文件
        srt_candidate = txt_path.with_suffix(".srt")
        if srt_candidate.exists():
            srt_path = srt_candidate

    # ─── 字幕烧录 ────────────────────────────────
    if args.burn and srt_path and srt_path.exists():
        print("\n" + "=" * 50)
        print("🔥 字幕烧录")
        print("=" * 50)

        from src.subtitle.burner import SubtitleBurner

        video_input = input_path if is_video else (srt_path.parent / "video.mp4")
        if video_input.exists():
            burner = SubtitleBurner()
            burner.burn(video_input, srt_path)
        else:
            print("⚠️  烧录字幕需要视频文件，跳过")

    # ─── 生成笔记 ────────────────────────────────
    if not args.no_notes and txt_path and txt_path.exists():
        print("\n" + "=" * 50)
        print("📝 阶段 2/3: 生成学习笔记")
        print("=" * 50)

        from src.notes.generator import NotesGenerator

        gen = NotesGenerator()

        # 前置检查
        if not gen.check_service():
            sys.exit(1)

        # 生成
        notes = gen.generate(str(txt_path))

        if notes:
            output = gen.save(notes, str(txt_path))
            print("\n📋 笔记预览 (前500字):")
            print("-" * 40)
            print(notes[:500])
        else:
            print("\n❌ 未能生成笔记，请检查 Ollama 状态")
            sys.exit(1)

    # ─── 完成 ────────────────────────────────────
    print("\n" + "=" * 50)
    print("✅ 全部完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()

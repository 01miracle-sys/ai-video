"""
字幕烧录模块 - 使用 FFmpeg 将 SRT 字幕嵌入视频

用法:
    from src.subtitle.burner import SubtitleBurner

    burner = SubtitleBurner()
    result = burner.burn("test.mp4", "test.srt")
    # result -> Path("outputs/test_with_subtitles.mp4")
"""

import shutil
import subprocess
from pathlib import Path

from src.utils.file_utils import ensure_dir


class SubtitleBurner:
    """FFmpeg 字幕烧录封装"""

    def __init__(
        self,
        output_dir: str | Path = "outputs",
        font: str = "Microsoft YaHei",
        font_size: int = 18,
        outline: int = 1,
    ) -> None:
        """
        Args:
            output_dir: 输出目录
            font: 字幕字体
            font_size: 字体大小
            outline: 文字描边宽度
        """
        self.output_dir = Path(output_dir)
        self.font = font
        self.font_size = font_size
        self.outline = outline

    def burn(
        self,
        video_path: str | Path,
        srt_path: str | Path,
        output_path: str | Path | None = None,
        preset: str = "fast",
        crf: int = 23,
    ) -> Path:
        """
        将 SRT 字幕烧录到视频中。

        Args:
            video_path: 输入视频文件路径
            srt_path: SRT 字幕文件路径
            output_path: 输出视频路径（默认: outputs/视频名_with_subtitles.mp4）
            preset: FFmpeg 编码预设 (ultrafast/fast/medium/slow)
            crf: 视频质量 (0-51，越小质量越高)

        Returns:
            输出视频文件的 Path

        Raises:
            FileNotFoundError: 视频或字幕文件不存在
            RuntimeError: FFmpeg 执行失败
        """
        video_path = Path(video_path)
        srt_path = Path(srt_path)

        if not video_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        if not srt_path.exists():
            raise FileNotFoundError(f"字幕文件不存在: {srt_path}")

        ensure_dir(self.output_dir)

        if output_path is None:
            output_path = (
                self.output_dir
                / f"{video_path.stem}_with_subtitles{video_path.suffix}"
            )
        else:
            output_path = Path(output_path)

        # ── 复制 SRT 到输出目录（用简单文件名避免 Windows 盘符冒号问题） ──
        temp_srt = self.output_dir / f"_sub_{srt_path.name}"
        shutil.copy2(srt_path, temp_srt)

        # ── 构建滤镜字符串 ──
        # 使用相对于 CWD 的路径（outputs/_sub_xxx.srt），不含盘符冒号
        # fontsdir 不用指定，FFmpeg + libass 在 Windows 上会自动找系统字体
        # force_style 的值必须用单引号包裹，否则 FFmpeg 会把内部的逗号
        # 误判成滤镜选项分隔符（而不是 ASS 样式属性分隔符）
        subtitles_filter = (
            f"subtitles={temp_srt.as_posix()}:"
            f"force_style='FontName={self.font},"
            f"FontSize={self.font_size},"
            f"Outline={self.outline},"
            f"PrimaryCol=&H00FFFFFF,"
            f"OutlineCol=&H00000000,"
            f"BackCol=&H80000000'"
        )

        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", subtitles_filter,
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", preset,
            "-c:a", "copy",
            "-y",
            str(output_path),
        ]

        print(f"🔥 开始烧录字幕...")
        print(f"   输入视频: {video_path.name}")
        print(f"   输入字幕: {srt_path.name}")
        print(f"   输出视频: {output_path.name}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() or "未知错误"
                raise RuntimeError(f"FFmpeg 执行失败:\n{error_msg}")

            file_size = (
                output_path.stat().st_size / 1024 / 1024
            )
            print(f"✅ 字幕烧录完成！")
            print(f"   输出: {output_path.resolve()}")
            print(f"   大小: {file_size:.1f} MB")

            return output_path

        except FileNotFoundError:
            raise RuntimeError(
                "未找到 FFmpeg，请确保已安装并添加到系统 PATH\n"
                "  下载: https://ffmpeg.org/download.html"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("FFmpeg 执行超时 (>3600s)")
        finally:
            # 清理临时 SRT 副本
            if temp_srt.exists():
                temp_srt.unlink()

    def list_fonts(self) -> list[str]:
        """列出系统可用字体（仅 Windows）"""
        fonts_dir = Path("C:/Windows/Fonts")
        if not fonts_dir.exists():
            return []
        return sorted(
            f.stem for f in fonts_dir.glob("*.ttf")
        )

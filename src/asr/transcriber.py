"""
语音识别模块 - 使用 faster-whisper 进行本地语音转文字

用法:
    from src.asr.transcriber import WhisperTranscriber

    transcriber = WhisperTranscriber(model_size="small")
    result = transcriber.transcribe("video.mp4")
    # result.segments  -> list[Segment]
    # result.txt_path  -> Path (纯文本文件)
    # result.srt_path  -> Path (字幕文件)
"""

import os

# Anaconda + faster-whisper 的 OpenMP 运行时冲突处理
# 详情: https://github.com/SYSTRAN/faster-whisper/issues/219
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from pathlib import Path
from typing import NamedTuple

from faster_whisper import WhisperModel


def format_timestamp(seconds: float) -> str:
    """将秒数转为 SRT 格式时间戳 (HH:MM:SS,mmm)"""
    milliseconds = int(round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds, milliseconds = divmod(milliseconds, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


class TranscribeResult(NamedTuple):
    """语音识别结果"""
    segments: list
    txt_path: Path
    srt_path: Path


class WhisperTranscriber:
    """faster-whisper 语音识别封装"""

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        cpu_threads: int = 4,
    ) -> None:
        """
        初始化语音识别器。

        Args:
            model_size: 模型大小 (tiny/base/small/medium/large)
            device: 推理设备 (cpu/cuda)
            compute_type: 精度类型 (int8/float16/float32)
            cpu_threads: CPU 线程数
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self._model: WhisperModel | None = None

    def _load_model(self) -> WhisperModel:
        """加载模型（延迟加载，仅在首次调用时创建）"""
        if self._model is None:
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=self.cpu_threads,
            )
        return self._model

    def transcribe(
        self,
        media_path: str | Path,
        output_dir: str | Path = "outputs",
        language: str = "zh",
        beam_size: int = 5,
        vad_filter: bool = True,
    ) -> TranscribeResult:
        """
        对视频/音频文件进行语音识别，输出 TXT 和 SRT 文件。

        Args:
            media_path: 视频/音频文件路径
            output_dir: 输出目录
            language: 语言代码 (zh/en/ja...)
            beam_size: 束搜索宽度
            vad_filter: 是否启用语音活动检测

        Returns:
            TranscribeResult 包含 segments 列表和输出文件路径
        """
        media_path = Path(media_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        txt_path = output_dir / f"{media_path.stem}.txt"
        srt_path = output_dir / f"{media_path.stem}.srt"

        model = self._load_model()

        print(f"开始识别：{media_path.name}")
        segments, info = model.transcribe(
            str(media_path),
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
            condition_on_previous_text=False,
        )

        print(f"识别语言：{info.language}")
        print(f"语言置信度：{info.language_probability:.2%}")

        segments_list: list = []

        with (
            txt_path.open("w", encoding="utf-8") as txt_file,
            srt_path.open("w", encoding="utf-8") as srt_file,
        ):
            for index, segment in enumerate(segments, start=1):
                text = segment.text.strip()
                if not text:
                    continue

                print(
                    f"[{segment.start:8.2f}s -> {segment.end:8.2f}s] {text}"
                )

                txt_file.write(text + "\n")

                srt_file.write(f"{index}\n")
                srt_file.write(
                    f"{format_timestamp(segment.start)} --> "
                    f"{format_timestamp(segment.end)}\n"
                )
                srt_file.write(text + "\n\n")

                segments_list.append(segment)

        print(f"\n✅ 识别完成！")
        print(f"   纯文本：{txt_path.resolve()}")
        print(f"   字幕文件：{srt_path.resolve()}")

        return TranscribeResult(
            segments=segments_list,
            txt_path=txt_path,
            srt_path=srt_path,
        )

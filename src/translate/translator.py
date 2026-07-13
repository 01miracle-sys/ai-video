"""
翻译引擎 - 将 SRT 字幕从源语言翻译为目标语言

支持双后端:
  - Ollama: 本地大模型翻译（隐私优先，免费）
  - API:   接入第三方翻译 API（质量更高）

用法:
    from src.translate.translator import create_translator

    translator = create_translator(provider="ollama")
    translated_srt = translator.translate_srt(
        srt_content="...", source_lang="ja", target_lang="zh"
    )
"""

import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import requests
import yaml


# ─── SRT 解析/生成工具 ─────────────────────────────

SRT_BLOCK_PATTERN = re.compile(
    r"(\d+)\n"
    r"(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})\n"
    r"((?:.+\n?)*?)(?:\n|$)",
    re.MULTILINE,
)


def parse_srt(srt_content: str) -> list[dict]:
    """将 SRT 格式字幕解析为段落列表

    返回:
        [{"index": 1, "time": "00:00:01,000 --> 00:00:04,000", "text": "..."}, ...]
    """
    blocks: list[dict] = []
    for match in SRT_BLOCK_PATTERN.finditer(srt_content.strip()):
        blocks.append({
            "index": int(match.group(1)),
            "time": match.group(2),
            "text": match.group(3).strip(),
        })
    return blocks


def build_srt(blocks: list[dict]) -> str:
    """将段落列表重新组装为 SRT 格式字符串"""
    lines: list[str] = []
    for block in blocks:
        lines.append(str(block["index"]))
        lines.append(block["time"])
        lines.append(block["text"])
        lines.append("")
    return "\n".join(lines)


def srt_to_vtt(srt_content: str) -> str:
    """将 SRT 格式转为 WebVTT 格式"""
    vtt_lines = ["WEBVTT", ""]
    for block in parse_srt(srt_content):
        # SRT: 00:00:01,000  →  VTT: 00:00:01.000
        time_vtt = block["time"].replace(",", ".")
        vtt_lines.append(time_vtt)
        vtt_lines.append(block["text"])
        vtt_lines.append("")
    return "\n".join(vtt_lines)


# ─── 翻译 Prompt ──────────────────────────────────

TRANSLATION_PROMPT_TPL = """你是一个专业翻译。请将以下{source_lang}视频字幕逐段翻译成{target_lang}。

要求：
1. 保持口语化，符合视频语境
2. 保持时间轴顺序不变
3. 每段翻译结果独占一行
4. 只输出翻译结果，不要添加额外说明
5. 如果某段已经是{target_lang}，直接原样输出
6. 专有名词（人名、地名）保留原文

需要翻译的内容（每行一段）：

{segments_text}
"""


# ─── 抽象翻译器 ────────────────────────────────────

class BaseTranslator(ABC):
    """翻译器基类"""

    @abstractmethod
    def translate_text(
        self, text: str, source_lang: str, target_lang: str
    ) -> str:
        """翻译纯文本"""
        ...

    def translate_srt(
        self,
        srt_content: str,
        source_lang: str = "ja",
        target_lang: str = "zh",
        batch_size: int = 5,
    ) -> str:
        """翻译 SRT 字幕，保持时间轴不变

        Args:
            srt_content: SRT 格式的字幕内容
            source_lang: 源语言代码
            target_lang: 目标语言代码
            batch_size: 每批翻译段落数

        Returns:
            翻译后的 SRT 格式字幕
        """
        blocks = parse_srt(srt_content)
        if not blocks:
            return srt_content

        total = len(blocks)
        translated_texts: list[str] = [""] * total

        # 按批次翻译
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            batch = blocks[start:end]

            segments_text = "\n".join(
                f"[{b['index']}] {b['text']}" for b in batch
            )

            lang_map = {"ja": "日语", "zh": "中文", "en": "英文"}
            prompt = TRANSLATION_PROMPT_TPL.format(
                source_lang=lang_map.get(source_lang, source_lang),
                target_lang=lang_map.get(target_lang, target_lang),
                segments_text=segments_text,
            )

            result = self.translate_text(
                prompt, source_lang=source_lang, target_lang=target_lang
            )

            if not result:
                # 翻译失败，保持原文
                for i, block in enumerate(batch):
                    translated_texts[start + i] = block["text"]
                continue

            # 解析翻译结果
            result_lines = result.strip().split("\n")
            for i, line in enumerate(result_lines):
                if i < len(batch):
                    # 去掉可能的 [N] 前缀
                    clean = re.sub(r"^\[\d+\]\s*", "", line).strip()
                    translated_texts[start + i] = clean

            # 批次间休息，避免频率限制
            if end < total:
                time.sleep(0.5)

        # 组装回 SRT
        for i, block in enumerate(blocks):
            if translated_texts[i]:
                block["text"] = translated_texts[i]

        return build_srt(blocks)


# ─── Ollama 翻译后端 ──────────────────────────────

class OllamaTranslator(BaseTranslator):
    """使用 Ollama 本地模型翻译"""

    def __init__(
        self,
        model: str = "qwen2.5:3b",
        api_url: str = "http://localhost:11434/api/generate",
        temperature: float = 0.3,
    ) -> None:
        self.model = model
        self.api_url = api_url
        self.temperature = temperature

    def translate_text(
        self, text: str, source_lang: str = "", target_lang: str = ""
    ) -> str:
        try:
            resp = requests.post(
                self.api_url,
                json={
                    "model": self.model,
                    "prompt": text,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": 2048,
                    },
                },
                timeout=120,
            )
            if resp.status_code == 200:
                return resp.json().get("response", "")
            return ""
        except Exception:
            return ""

    def check_available(self) -> bool:
        """检查 Ollama 服务是否可用"""
        try:
            resp = requests.get(
                "http://localhost:11434/api/tags", timeout=5
            )
            return resp.status_code == 200
        except requests.ConnectionError:
            return False


# ─── API 翻译后端（预留）───────────────────────────

class ApiTranslator(BaseTranslator):
    """使用第三方 API 翻译（预留实现）

    支持: Google Cloud Translation / Baidu / DeepL
    使用前需在 settings.yaml 中配置 api_key
    """

    def __init__(
        self,
        provider: str = "",
        api_key: str = "",
        endpoint: str = "",
    ) -> None:
        self.provider = provider
        self.api_key = api_key
        self.endpoint = endpoint

    def translate_text(
        self, text: str, source_lang: str = "", target_lang: str = ""
    ) -> str:
        # TODO: 根据 self.provider 实现对应 API 调用
        #   - google: 使用 google-cloud-translate
        #   - baidu:  调用百度翻译 API
        #   - deepl:  调用 DeepL API
        raise NotImplementedError(
            "API 翻译后端尚未实现。\n"
            "请先配置 settings.yaml 中的 translation.api_key，\n"
            "或使用 'ollama' 作为翻译后端。"
        )

    def check_available(self) -> bool:
        return bool(self.api_key)


# ─── 工厂函数 ──────────────────────────────────────

def create_translator(
    provider: str = "ollama",
    config_path: str | Path = "config/settings.yaml",
) -> BaseTranslator:
    """创建翻译器实例

    Args:
        provider: 翻译后端类型 (ollama / api)
        config_path: 配置文件路径

    Returns:
        BaseTranslator 实例
    """
    # 加载配置
    config_path = Path(config_path)
    config: dict = {}
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    tcfg = config.get("translation", {})

    if provider == "api":
        return ApiTranslator(
            provider=tcfg.get("api_provider", ""),
            api_key=tcfg.get("api_key", ""),
            endpoint=tcfg.get("api_endpoint", ""),
        )

    # 默认使用 Ollama
    return OllamaTranslator(
        model=tcfg.get("model", "qwen2.5:3b"),
        api_url=tcfg.get("api_url", "http://localhost:11434/api/generate"),
        temperature=tcfg.get("temperature", 0.3),
    )


def check_translation_available(
    provider: str = "ollama",
) -> bool:
    """检查翻译后端是否可用"""
    translator = create_translator(provider=provider)
    return translator.check_available()

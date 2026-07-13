"""
学习笔记生成模块 - 调用 Ollama 将 ASR 文本转为结构化 Markdown 笔记

用法:
    from src.notes.generator import NotesGenerator

    gen = NotesGenerator(model="qwen2.5:3b")
    notes = gen.generate("outputs/test.txt")
"""

import json
import time
from pathlib import Path

import requests

from src.utils.file_utils import ensure_dir


# ─── 提示词模板 ─────────────────────────────────────
SYSTEM_PROMPT = """你是一个专业的学习助手，擅长将课程讲稿整理成高质量的学习笔记。

请根据提供的课程文字内容，生成一份完整的学习笔记，必须包含以下所有部分（严格按照顺序输出，用 Markdown 格式）：

## 📋 课程概述
用 2-3 句话概括这堂课的核心内容和学习目标。

## 🎯 核心知识点
列出 3-6 个最重要的知识点，每条用一句话说明。

## 📝 详细笔记
将课程内容按照逻辑分成几个小节，每个小节一个小标题，展开详细整理。不要遗漏重要内容。

## 🔑 重点术语
如果课程中出现了专业术语，用表格列出并解释。

## ❓ 复习思考题
出 3-5 道简答题，帮助复习和检查理解程度。

注意：
- 使用中文输出
- 要忠实于课程原文，不要编造内容
- 术语解释要准确
- 如果课程内容较少，相应部分可以简短但不要省略"""


class NotesGenerator:
    """Ollama 学习笔记生成器"""

    def __init__(
        self,
        model: str = "qwen2.5:3b",
        api_url: str = "http://localhost:11434/api/generate",
        temperature: float = 0.3,
        chunk_size: int = 4000,
    ) -> None:
        """
        Args:
            model: Ollama 模型名
            api_url: Ollama API 地址
            temperature: 生成温度 (0-1)
            chunk_size: 长文本分段大小（字符数）
        """
        self.model = model
        self.api_url = api_url
        self.temperature = temperature
        self.chunk_size = chunk_size

    # ─── 公共方法 ─────────────────────────────────

    def check_service(self) -> bool:
        """检查 Ollama 服务是否在运行"""
        try:
            resp = requests.get(
                "http://localhost:11434/api/tags", timeout=5
            )
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                print(f"✅ Ollama 服务已连接，可用模型: {len(models)} 个")
                return True
        except requests.ConnectionError:
            pass
        print("❌ 无法连接 Ollama，请确认 Ollama 已启动")
        print("   如果未启动，请在终端运行: ollama serve")
        return False

    def check_model(self, model: str | None = None) -> bool:
        """检查模型是否已下载"""
        model = model or self.model
        try:
            resp = requests.get(
                "http://localhost:11434/api/tags", timeout=5
            )
            models = [m["name"] for m in resp.json().get("models", [])]
            base = model.split(":")[0]
            for m in models:
                if m.startswith(base) or m == model:
                    print(f"✅ 模型 {m} 可用")
                    return True
            print(f"⚠️  模型 {model} 未找到，将尝试使用")
            return True
        except Exception:
            return True

    def generate(self, content: str | Path) -> str:
        """
        从文本内容生成笔记。

        Args:
            content: 文本内容字符串，或指向 TXT 文件的 Path

        Returns:
            生成的 Markdown 笔记文本
        """
        # 如果传入的是路径，先读取文件
        if isinstance(content, Path) or (
            isinstance(content, str)
            and Path(content).exists()
        ):
            path = Path(content)
            text = path.read_text(encoding="utf-8").strip()
            if not text:
                raise ValueError(f"文件内容为空: {path}")
            print(f"📄 输入文件: {path.name}")
        else:
            text = str(content).strip()

        print(f"📖 原文长度: {len(text)} 字符")
        print(f"📦 模型: {self.model}")

        chunks = self._chunk_text(text)

        if len(chunks) == 1:
            print("⚙️  生成学习笔记中...")
            return self._call_ollama(text)
        else:
            print(f"📑 文本较长，分为 {len(chunks)} 段处理")
            summaries = []
            for i, chunk in enumerate(chunks):
                print(
                    f"  ⏳ 处理第 {i + 1}/{len(chunks)} 段 "
                    f"({len(chunk)} 字符)..."
                )
                summary = self._summarize_chunk(chunk, i, len(chunks))
                if summary:
                    summaries.append(summary)
                time.sleep(1)

            merged = "\n\n---\n\n".join(summaries)
            print(f"⚙️  基于 {len(chunks)} 段摘要生成完整笔记...")
            return self._call_ollama(merged)

    def save(self, notes: str, txt_path: str | Path, output_dir: str | Path = "outputs") -> Path:
        """将笔记保存为 Markdown 文件"""
        txt_path = Path(txt_path)
        output_dir = Path(output_dir)
        ensure_dir(output_dir)

        output_path = output_dir / f"{txt_path.stem}_学习笔记.md"

        header = (
            f"# {txt_path.stem} 学习笔记\n\n"
            f"> 🤖 由 {self.model} 自动生成\n"
            f"> 📅 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"> 📄 原始文本: {txt_path.name}\n\n"
            f"---\n\n"
        )

        output_path.write_text(header + notes, encoding="utf-8")
        print(f"✅ 笔记已保存: {output_path.resolve()}")
        return output_path

    # ─── 私有方法 ─────────────────────────────────

    def _chunk_text(self, text: str) -> list[str]:
        """将长文本按句子边界智能分段"""
        if len(text) <= self.chunk_size:
            return [text]

        chunks: list[str] = []
        current = ""
        sentences = text.replace("\n\n", "\n").split("\n")

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            if len(current) + len(sentence) < self.chunk_size:
                current += sentence + "\n"
            else:
                if current:
                    chunks.append(current.strip())
                if len(sentence) > self.chunk_size:
                    for i in range(0, len(sentence), self.chunk_size):
                        chunks.append(
                            sentence[i : i + self.chunk_size]
                        )
                    current = ""
                else:
                    current = sentence + "\n"

        if current.strip():
            chunks.append(current.strip())

        return chunks

    def _summarize_chunk(
        self, text: str, chunk_idx: int, total: int
    ) -> str:
        """对单个文本块生成摘要"""
        prompt = (
            f"请对以下课程内容的第 {chunk_idx + 1}/{total} 部分进行整理，"
            f"提取出关键知识点和要点。\n\n内容：\n{text}\n\n"
            f"请用简洁的要点形式输出（每条一行），不要遗漏关键信息。"
        )

        try:
            resp = requests.post(
                self.api_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": 2048,
                    },
                },
                timeout=300,
            )
            if resp.status_code == 200:
                return resp.json().get("response", "")
            print(f"  ⚠️ 请求失败: {resp.status_code}")
            return ""
        except Exception as e:
            print(f"  ⚠️ 请求异常: {e}")
            return ""

    def _call_ollama(self, content: str) -> str:
        """调用 Ollama API 生成笔记"""
        full_prompt = f"{SYSTEM_PROMPT}\n\n---\n以下是课程内容：\n\n{content}"

        print(f"  📤 发送请求 ({len(content)} 字符)...")
        start = time.time()

        try:
            resp = requests.post(
                self.api_url,
                json={
                    "model": self.model,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": 4096,
                        "num_ctx": 8192,
                    },
                },
                timeout=600,
            )

            elapsed = time.time() - start

            if resp.status_code == 200:
                result = resp.json().get("response", "")
                tokens = resp.json().get("eval_count", 0)
                print(
                    f"  ✅ 完成 ({elapsed:.1f}s, 生成 {tokens} tokens)"
                )
                return result
            else:
                print(f"  ❌ API 错误: {resp.status_code}")
                print(f"     {resp.text[:500]}")
                return ""
        except requests.Timeout:
            print("  ❌ 请求超时 (>600s)")
            return ""
        except Exception as e:
            print(f"  ❌ 请求异常: {e}")
            return ""

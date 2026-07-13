"""
⚠️  此文件已迁移，请使用新的统一入口。

新用法:
    python main.py test.txt                     # 生成笔记
    python main.py video.mp4                    # 全流程
    python main.py video.mp4 --burn             # 全流程 + 字幕烧录

保留此文件保持向后兼容，后续将移除。
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

# ─── 配置 ───────────────────────────────────────────
OLLAMA_API = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5:3b"
DEFAULT_CHUNK_SIZE = 4000  # 每段最大字符数（中文）

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


def check_ollama() -> bool:
    """检查 Ollama 服务是否在运行"""
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            print(f"✅ Ollama 服务已连接，可用模型: {len(models)} 个")
            return True
    except requests.ConnectionError:
        pass
    print("❌ 无法连接 Ollama，请确认 Ollama 已启动")
    print("   如果未启动，请在终端运行: ollama serve")
    return False


def check_model(model: str) -> bool:
    """检查模型是否已下载"""
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        # 匹配模型名（可能是 qwen2.5:3b 或 qwen2.5:latest 等）
        base = model.split(":")[0]
        for m in models:
            if m.startswith(base) or m == model:
                print(f"✅ 模型 {m} 可用")
                return True
        print(f"⚠️  模型 {model} 未找到，将尝试使用")
        return True  # 仍然尝试，Ollama 可能会自动下载
    except Exception:
        return True  # 宽松处理


def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> list[str]:
    """将长文本按句子边界智能分段"""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    current = ""
    # 按句子分割（中文句号、问号、感叹号、换行）
    sentences = text.replace("\n\n", "\n").split("\n")

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(current) + len(sentence) < chunk_size:
            current += sentence + "\n"
        else:
            if current:
                chunks.append(current.strip())
            # 如果单句超过 chunk_size，强制分段
            if len(sentence) > chunk_size:
                for i in range(0, len(sentence), chunk_size):
                    chunks.append(sentence[i : i + chunk_size])
                current = ""
            else:
                current = sentence + "\n"

    if current.strip():
        chunks.append(current.strip())

    return chunks


def summarize_chunk(model: str, text: str, chunk_idx: int, total: int) -> str:
    """对单个文本块生成摘要（用于合并多段内容）"""
    prompt = f"""请对以下课程内容的第 {chunk_idx + 1}/{total} 部分进行整理，提取出关键知识点和要点。

内容：
{text}

请用简洁的要点形式输出（每条一行），不要遗漏关键信息。"""

    try:
        resp = requests.post(
            OLLAMA_API,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 2048},
            },
            timeout=300,
        )
        if resp.status_code == 200:
            return resp.json().get("response", "")
        else:
            print(f"  ⚠️ 请求失败: {resp.status_code}")
            return ""
    except Exception as e:
        print(f"  ⚠️ 请求异常: {e}")
        return ""


def generate_notes(model: str, content: str, chunk_size: int) -> str:
    """主流程：将文本发送给 Ollama 生成笔记"""
    print(f"📖 原文长度: {len(content)} 字符")
    print(f"📦 模型: {model}")

    # 如果文本太长，先让 AI 分段总结再合并
    chunks = chunk_text(content, chunk_size)

    if len(chunks) == 1:
        # 直接生成笔记
        print("⚙️  生成学习笔记中...")
        return _call_ollama(model, content)
    else:
        # 多段：先逐段总结
        print(f"📑 文本较长，分为 {len(chunks)} 段处理")
        summaries = []
        for i, chunk in enumerate(chunks):
            print(f"  ⏳ 处理第 {i + 1}/{len(chunks)} 段 ({len(chunk)} 字符)...")
            summary = summarize_chunk(model, chunk, i, len(chunks))
            if summary:
                summaries.append(summary)
            time.sleep(1)  # 避免请求过快

        merged = "\n\n---\n\n".join(summaries)
        # 用合并后的摘要生成最终笔记
        print(f"⚙️  基于 {len(chunks)} 段摘要生成完整笔记...")
        return _call_ollama(model, merged)


def _call_ollama(model: str, content: str) -> str:
    """调用 Ollama API"""
    full_prompt = f"{SYSTEM_PROMPT}\n\n---\n以下是课程内容：\n\n{content}"

    print(f"  📤 发送请求 ({len(content)} 字符)...")
    start = time.time()

    try:
        resp = requests.post(
            OLLAMA_API,
            json={
                "model": model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 4096,
                    "num_ctx": 8192
                },
            },
            timeout=600,
        )

        elapsed = time.time() - start

        if resp.status_code == 200:
            result = resp.json().get("response", "")
            tokens = resp.json().get("eval_count", 0)
            print(f"  ✅ 完成 ({elapsed:.1f}s, 生成 {tokens} tokens)")
            return result
        else:
            print(f"  ❌ API 错误: {resp.status_code}")
            print(f"     {resp.text[:500]}")
            return ""
    except requests.Timeout:
        print(f"  ❌ 请求超时 (>600s)")
        return ""
    except Exception as e:
        print(f"  ❌ 请求异常: {e}")
        return ""


def save_result(txt_path: str, notes: str, model: str) -> str:
    """保存生成的笔记为 Markdown 文件"""
    src = Path(txt_path)
    output_path = src.parent / f"{src.stem}_学习笔记.md"

    header = f"""# {src.stem} 学习笔记

> 🤖 由 {model} 自动生成
> 📅 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}
> 📄 原始文本: {src.name}

---

"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + notes)

    return str(output_path)


def main():
    parser = argparse.ArgumentParser(
        description="AI 学习笔记生成器 - 将课程 TXT 转为结构化 Markdown 笔记"
    )
    parser.add_argument("txt_file", help="faster-whisper 输出的 TXT 文件路径")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama 模型名 (默认: {DEFAULT_MODEL})")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE,
                        help=f"分段大小字符数 (默认: {DEFAULT_CHUNK_SIZE})")
    parser.add_argument("--output", "-o", default=None, help="输出文件路径 (默认: 同目录下_学习笔记.md)")
    args = parser.parse_args()

    # ─── 前置检查 ────────────────────────────────
    if not check_ollama():
        sys.exit(1)
    if not check_model(args.model):
        print("⚠️  将尝试继续...")

    # ─── 读取文件 ────────────────────────────────
    txt_path = Path(args.txt_file)
    if not txt_path.exists():
        print(f"❌ 文件不存在: {args.txt_file}")
        sys.exit(1)
    if txt_path.suffix.lower() not in (".txt", ".md"):
        print(f"⚠️  文件类型为 {txt_path.suffix}，建议使用 .txt 文件")

    content = txt_path.read_text(encoding="utf-8").strip()
    if not content:
        print("❌ 文件内容为空")
        sys.exit(1)

    print(f"{'='*50}")
    print(f"📄 输入文件: {txt_path.name}")
    print(f"{'='*50}")

    # ─── 生成笔记 ────────────────────────────────
    notes = generate_notes(args.model, content, args.chunk_size)

    if not notes:
        print("\n❌ 未能生成笔记，请检查 Ollama 状态")
        sys.exit(1)

    # ─── 保存结果 ────────────────────────────────
    output_path = args.output or save_result(args.txt_file, notes, args.model)
    print(f"\n{'='*50}")
    print(f"✅ 笔记已保存: {output_path}")
    print(f"{'='*50}")

    # 打印预览
    print("\n📋 笔记预览 (前500字):")
    print("-" * 40)
    print(notes[:500])


if __name__ == "__main__":
    main()

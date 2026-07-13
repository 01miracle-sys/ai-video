"""
文件工具函数

用法:
    from src.utils.file_utils import ensure_dir, get_output_path
"""

from pathlib import Path


def ensure_dir(path: str | Path) -> Path:
    """确保目录存在，不存在则创建"""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_output_path(
    input_path: str | Path,
    suffix: str = "_notes.md",
    output_dir: str | Path = "outputs",
) -> Path:
    """根据输入文件路径生成输出文件路径"""
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    ensure_dir(output_dir)
    return output_dir / f"{input_path.stem}{suffix}"

"""只负责安全、稳定地读写本项目产生的文件。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    """按UTF-8读取JSON。"""

    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    """按UTF-8写入格式稳定的JSON，并确保父目录存在。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    """分块计算文件哈希，避免大文件一次性进入内存。"""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_space(text: str) -> str:
    """统一空白字符，便于跨DOCX/PDF验证原文。"""

    return " ".join(text.split())


def normalized_contains(container: str, fragment: str) -> bool:
    """判断片段是否出现在容器文本中。

    比较前只统一空白与大小写，不做同义替换、不做词干化，
    因此改写、概括或凭空生成的引文仍然会被拒绝。
    """

    if not fragment or not fragment.strip():
        return False
    return normalize_space(fragment).lower() in normalize_space(container).lower()



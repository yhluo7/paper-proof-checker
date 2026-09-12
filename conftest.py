"""让tests/可以直接导入仓库级tools包和src源码。"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
for candidate in (ROOT, ROOT / "src"):
    text = str(candidate)
    if text not in sys.path:
        sys.path.insert(0, text)

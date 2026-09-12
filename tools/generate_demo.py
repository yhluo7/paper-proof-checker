"""生成公开合成Demo、冻结标准答案并产出标准报告。

用法：
    python tools/generate_demo.py

产物：
    examples/quick-demo/           可直接使用的输入、标准审核JSON、标准报告与说明
    eval/ground-truth.json         冻结的标准答案（只由Demo结构决定）

同一次运行会依次执行 prepare -> validate -> report，因此标准报告本身就是
"文档中的命令真实可跑通"的证据。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    text = str(candidate)
    if text not in sys.path:
        sys.path.insert(0, text)

from paper_proof_checker.cli import prepare_project  # noqa: E402
from paper_proof_checker.io_utils import read_json  # noqa: E402
from paper_proof_checker.report import build_report  # noqa: E402
from paper_proof_checker.validator import validate_run  # noqa: E402
from tools.benchmark import (  # noqa: E402
    HIGH_RISK_TOTAL,
    SCENARIO_TOTAL,
    build_expected_reviews,
    dump_json,
    resolve_ground_truth,
)
from tools.demo_data import build_demo_project  # noqa: E402


DEMO_README = """# quick-demo：五分钟复现一次完整检查

这是一个**完全虚构的合成论文项目**，用于公开复现 paper-proof-checker 的完整流程。
它不含任何真实论文内容，所有作者、期刊、DOI 与数值均为演示而编造。

## 目录内容

```text
quick-demo/
├── manuscript.docx          主文（含1张表、5条编号参考文献、5处引用）
├── supplement.docx          补充材料（提供88.4%的来源）
├── reference-map.json       参考文献编号到PDF文件的手工映射
├── references/
│   ├── Smith_2022.pdf       有DOI，可直接匹配
│   ├── Brown_2021.pdf       没有DOI且元数据标题不同，只能靠手工映射匹配
│   └── archive/
│       ├── Jones_2023.pdf   放在子目录里，用于验证递归发现
│       └── Chen_2020.pdf    同上
└── expected/
    ├── numeric-reviews.json 标准数值审核答案
    ├── citation-reviews.json 标准引用审核答案
    ├── paper-proof-report.md 由标准答案生成的正式报告
    ├── reference-mapping.md 参考文献匹配结果
    └── run-summary.json      运行规模摘要（不含本机绝对路径）
```

参考文献 **5（Miller 2019）故意没有提供PDF**，用于演示"全文不可用"必须被如实报告。

## 运行方式

```powershell
paper-proof prepare quick-demo --checks all --reference-map reference-map.json
paper-proof validate quick-demo/paper-proof-output/<时间戳目录>
paper-proof report quick-demo/paper-proof-output/<时间戳目录>
```

不需要参考文献目录时（只做数值检查）：

```powershell
paper-proof prepare quick-demo --checks numbers
```

## 这14项场景分别验证什么

| # | 场景 | 期望判断 | 高风险 |
|---:|---|---|:--:|
| 1 | 软件版本等非研究结果数值 | `not_a_result` |  |
| 2 | 正文与表格数值完全一致 | `exact_match` |  |
| 3 | 四舍五入后一致 | `rounded_match` |  |
| 4 | 百分比与小数换算一致 | `converted_match` |  |
| 5 | P值阈值与精确值兼容 | `threshold_compatible` |  |
| 6 | 同一结果数值不同 | `conflict` | ✔ |
| 7 | 数值没有任何表格或图注来源 | `source_not_found` | ✔ |
| 8 | 补充材料提供正文数值的来源 | `exact_match` |  |
| 9 | 数值只在图片里，像素无法读取 | `manual_figure_check` | ✔ |
| 10 | 正文主张被原文直接支撑 | `direct_support` |  |
| 11 | 原文只支撑特定亚组 | `partial_support` | ✔ |
| 12 | 原文结论与正文相反 | `conflict` | ✔ |
| 13 | 全文可解析但找不到证据 | `evidence_not_found` | ✔ |
| 14 | 参考文献没有本地全文 | `full_text_unavailable` | ✔ |

另有第15项结构性验证：`reference-map.json` 的手工映射优先于自动匹配，
且每条引用证据都能回到具体段落ID与真实PDF页码。

## 结果与边界

- 标准答案冻结在 `eval/ground-truth.json`，先于任何模型运行写好，之后不得修改。
- 本Demo是**合成数据**，无真实论文验证。它证明的是流程可复现、判断可回溯，
  不代表在真实论文上的表现。
- 预埋高风险问题共 {high_risk_total} 项，用于计算高风险召回率与误报数。
- 场景总数为 {scenario_total} 项，用于计算总体判断准确率。
"""


def _run_dir(output_root: Path) -> Path:
    return sorted(path for path in output_root.iterdir() if path.is_dir())[-1]


def main() -> int:
    parser = argparse.ArgumentParser(description="生成公开合成Demo并冻结标准答案")
    parser.add_argument("--demo-root", default=str(ROOT / "examples" / "quick-demo"))
    parser.add_argument("--ground-truth", default=str(ROOT / "eval" / "ground-truth.json"))
    args = parser.parse_args()

    demo_root = Path(args.demo_root)
    expected_dir = demo_root / "expected"
    expected_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/5] 生成合成输入：{demo_root}")
    build_demo_project(demo_root)
    output_root = demo_root / "paper-proof-output"
    if output_root.exists():
        for stale in sorted(path for path in output_root.iterdir() if path.is_dir()):
            shutil.rmtree(stale, ignore_errors=True)

    print("[2/5] 执行 prepare（确定性解析）")
    namespace = argparse.Namespace(
        project=str(demo_root),
        manuscript="manuscript.docx",
        supplement="supplement.docx",
        references="references",
        checks="all",
        reference_map="reference-map.json",
        output="paper-proof-output",
    )
    started = time.perf_counter()
    prepare_project(namespace)
    run_dir = _run_dir(demo_root / "paper-proof-output")

    print("[3/5] 冻结标准答案并生成参考审核JSON")
    ground_truth = resolve_ground_truth(run_dir)
    ground_truth["frozen_note"] = (
        "由Demo结构与预埋设计决定；在任何模型运行之前生成，之后不得修改。"
    )
    dump_json(Path(args.ground_truth), ground_truth)
    numeric_reviews, citation_reviews = build_expected_reviews(run_dir, ground_truth)
    dump_json(expected_dir / "numeric-reviews.json", numeric_reviews)
    dump_json(expected_dir / "citation-reviews.json", citation_reviews)
    shutil.copyfile(expected_dir / "numeric-reviews.json", run_dir / "reviews" / "numeric-reviews.json")
    shutil.copyfile(
        expected_dir / "citation-reviews.json", run_dir / "reviews" / "citation-reviews.json"
    )

    print("[4/5] 执行 validate 与 report")
    errors = validate_run(run_dir)
    if errors:
        print("validate失败：", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 2
    report_path = build_report(run_dir)
    elapsed = round(time.perf_counter() - started, 2)

    shutil.copyfile(report_path, expected_dir / "paper-proof-report.md")
    shutil.copyfile(run_dir / "reference-mapping.md", expected_dir / "reference-mapping.md")

    manifest = read_json(run_dir / "manifest.json")
    references = read_json(run_dir / "references.json")["references"]
    dump_json(
        expected_dir / "run-summary.json",
        {
            "version": manifest["version"],
            "rules_version": manifest["rules_version"],
            "enabled_checks": manifest["enabled_checks"],
            "created_at": manifest["created_at"],
            "counts": manifest["counts"],
            "reference_match_status": {
                str(item["reference_id"]): item["match_status"] for item in references
            },
            "reference_match_method": {
                str(item["reference_id"]): item["match_method"] for item in references
            },
            "elapsed_seconds_prepare_to_report": elapsed,
        },
    )

    readme = DEMO_README.format(
        high_risk_total=HIGH_RISK_TOTAL, scenario_total=SCENARIO_TOTAL
    )
    (demo_root / "README.md").write_text(readme, encoding="utf-8")

    print("[5/5] 完成")
    print(f"  运行目录：{run_dir}")
    print(f"  标准报告：{expected_dir / 'paper-proof-report.md'}")
    print(f"  标准答案：{args.ground_truth}")
    summary = json.dumps(manifest["counts"], ensure_ascii=False)
    print(f"  规模：{summary}")
    print(f"  prepare到report耗时：{elapsed}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

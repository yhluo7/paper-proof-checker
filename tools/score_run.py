"""对一次模型运行打分，并写入 eval/runs/ 供对照实验记录使用。

用法：
    python tools/score_run.py <run-dir> --label with-skill

约束：
- 只读取运行目录与冻结的 eval/ground-truth.json，不读取任何模型对话内容。
- 打分前先运行验证器；未通过验证的运行直接判为不可用，不产生分数。
- 结果写入 eval/runs/<label>/score.json（该目录被 .gitignore 忽略，属本地实验产物）。
  计划文档要求"保留所有失败结果，不覆盖或挑选最好结果"，因此同名目录不会被静默覆盖，
  而是追加时间戳后缀。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    text = str(candidate)
    if text not in sys.path:
        sys.path.insert(0, text)

from paper_proof_checker.io_utils import read_json  # noqa: E402
from paper_proof_checker.validator import validate_run  # noqa: E402
from tools.benchmark import score_run  # noqa: E402


METRIC_ROWS = (
    ("scenario_total", "场景总数"),
    ("high_risk_total", "预埋高风险总数"),
    ("verdict_correct", "总体判断正确数"),
    ("verdict_accuracy", "总体判断准确率"),
    ("strict_correct", "严格口径正确数（判断+候选ID）"),
    ("strict_accuracy", "严格口径准确率"),
    ("evidence_paragraph_correct", "证据段落回溯正确数"),
    ("high_risk_found", "高风险找到数"),
    ("high_risk_recall", "高风险召回率"),
    ("high_risk_false_positives", "高风险误报数"),
    ("produced_total", "模型实际产出的判断数"),
)


def _unique_dir(root: Path, label: str) -> Path:
    """同标签多次打分不覆盖历史结果。"""

    candidate = root / label
    if not candidate.exists():
        candidate.mkdir(parents=True)
        return candidate
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = root / f"{label}-{stamp}"
    candidate.mkdir(parents=True)
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description="对一次模型运行打分")
    parser.add_argument("run_dir")
    parser.add_argument("--label", default="run", help="运行标签，例如 no-skill / with-skill")
    parser.add_argument("--ground-truth", default=str(ROOT / "eval" / "ground-truth.json"))
    parser.add_argument("--output-dir", default=str(ROOT / "eval" / "runs"))
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    ground_truth = read_json(Path(args.ground_truth))

    errors = validate_run(run_dir)
    status = "valid" if not errors else "invalid"
    metrics = score_run(run_dir, ground_truth) if not errors else None

    payload = {
        "label": args.label,
        "run_dir": str(run_dir),
        "ground_truth": str(Path(args.ground_truth).resolve()),
        "scored_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "validation_status": status,
        "validation_errors": errors,
        "metrics": metrics,
    }
    destination = _unique_dir(Path(args.output_dir), args.label) / "score.json"
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"标签：{args.label}")
    print(f"运行目录：{run_dir}")
    print(f"验证状态：{status}")
    if errors:
        print(f"验证错误 {len(errors)} 条，未产生分数：")
        for error in errors:
            print(f"  - {error}")
        print(f"记录：{destination}")
        return 2

    print("")
    for key, label in METRIC_ROWS:
        print(f"  {label}：{metrics[key]}")
    if metrics["high_risk_missed"]:
        print("  漏报的高风险：")
        for item in metrics["high_risk_missed"]:
            print(f"    - {item}")
    if metrics["high_risk_false_positive_items"]:
        print("  高风险误报：")
        for item in metrics["high_risk_false_positive_items"]:
            print(f"    - {item}")
    print(f"\n记录：{destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

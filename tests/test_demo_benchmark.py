"""公开Demo、冻结标准答案与评分脚本的一致性。"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from paper_proof_checker.io_utils import read_json
from paper_proof_checker.report import build_report
from paper_proof_checker.validator import validate_run
from tools.benchmark import resolve_ground_truth, score_run
from tools.demo_data import build_demo_project
from tests.helpers import build_project, prepare, write_standard_reviews


REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = REPO_ROOT / "examples" / "quick-demo"
GROUND_TRUTH_PATH = REPO_ROOT / "eval" / "ground-truth.json"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DemoBenchmarkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "project"
        build_project(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_committed_demo_contains_every_declared_artifact(self) -> None:
        expected = [
            "manuscript.docx",
            "supplement.docx",
            "reference-map.json",
            "README.md",
            "references/Smith_2022.pdf",
            "references/Brown_2021.pdf",
            "references/archive/Jones_2023.pdf",
            "references/archive/Chen_2020.pdf",
            "expected/numeric-reviews.json",
            "expected/citation-reviews.json",
            "expected/paper-proof-report.md",
            "expected/reference-mapping.md",
            "expected/run-summary.json",
        ]
        for relative in expected:
            self.assertTrue((DEMO_ROOT / relative).is_file(), relative)
        # 故意缺失的参考文献不能出现PDF。
        self.assertFalse((DEMO_ROOT / "references" / "Miller_2019.pdf").exists())

    def test_standard_answers_pass_validation_and_render_report(self) -> None:
        run_dir = prepare(self.root)
        write_standard_reviews(run_dir)
        self.assertEqual(validate_run(run_dir), [])
        report = build_report(run_dir)
        self.assertTrue(report.exists())

    def test_regenerated_demo_matches_frozen_ground_truth_ids(self) -> None:
        """Demo必须可重复生成，且check_id与冻结标准答案一一对应。"""

        run_dir = prepare(self.root)
        fresh = resolve_ground_truth(run_dir)
        frozen = read_json(GROUND_TRUTH_PATH)
        self.assertEqual(fresh["scenario_total"], frozen["scenario_total"])
        self.assertEqual(fresh["high_risk_total"], frozen["high_risk_total"])
        fresh_ids = [(item["kind"], item.get("check_id") or item["batch_id"]) for item in fresh["checks"]]
        frozen_ids = [
            (item["kind"], item.get("check_id") or item["batch_id"]) for item in frozen["checks"]
        ]
        self.assertEqual(fresh_ids, frozen_ids)
        for fresh_item, frozen_item in zip(fresh["checks"], frozen["checks"]):
            self.assertEqual(fresh_item["expected_verdict"], frozen_item["expected_verdict"])
            self.assertEqual(
                fresh_item["expected_candidate_number_id"],
                frozen_item["expected_candidate_number_id"],
            )

    def test_committed_ground_truth_is_byte_reproducible(self) -> None:
        """冻结标准答案必须完全确定：重新生成的结果与提交文件逐字节一致。

        这是"标准答案先于模型运行冻结"这一主张的机器可验证形式：
        只要本用例通过，就说明 ground-truth.json 里没有任何随运行时间或机器变化的内容。
        """

        run_dir = prepare(self.root)
        fresh = resolve_ground_truth(run_dir)
        fresh["frozen_note"] = read_json(GROUND_TRUTH_PATH)["frozen_note"]
        rendered = json.dumps(fresh, ensure_ascii=False, indent=2) + "\n"
        self.assertEqual(rendered, GROUND_TRUTH_PATH.read_text(encoding="utf-8"))

    def test_ground_truth_covers_fourteen_scenarios_and_seven_high_risks(self) -> None:
        frozen = read_json(GROUND_TRUTH_PATH)
        self.assertEqual(frozen["scenario_total"], 14)
        self.assertEqual(len(frozen["checks"]), 14)
        self.assertEqual(frozen["high_risk_total"], 7)
        self.assertEqual(sum(1 for item in frozen["checks"] if item["high_risk"]), 7)
        self.assertEqual(len(frozen["mapping_checks"]), 3)

    def test_mapping_scenario_is_satisfied_by_the_frozen_run(self) -> None:
        run_dir = prepare(self.root)
        references = {
            item["reference_id"]: item
            for item in read_json(run_dir / "references.json")["references"]
        }
        for check in read_json(GROUND_TRUTH_PATH)["mapping_checks"]:
            reference = references[check["reference_id"]]
            self.assertEqual(reference["match_status"], check["expected_match_status"])
            self.assertEqual(reference.get("match_method"), check["expected_match_method"])

    def test_scoring_standard_answers_reaches_full_marks(self) -> None:
        run_dir = prepare(self.root)
        write_standard_reviews(run_dir)
        self.assertEqual(validate_run(run_dir), [])
        metrics = score_run(run_dir, read_json(GROUND_TRUTH_PATH))
        self.assertEqual(metrics["verdict_correct"], 14)
        self.assertEqual(metrics["verdict_accuracy"], 1.0)
        self.assertEqual(metrics["strict_correct"], 14)
        self.assertEqual(metrics["high_risk_found"], 7)
        self.assertEqual(metrics["high_risk_recall"], 1.0)
        self.assertEqual(metrics["high_risk_false_positives"], 0)
        self.assertEqual(metrics["missing_items"], [])

    def test_scoring_detects_a_deliberately_wrong_verdict(self) -> None:
        run_dir = prepare(self.root)
        write_standard_reviews(run_dir)
        payload = read_json(run_dir / "reviews" / "numeric-reviews.json")
        target = next(
            item for item in payload["reviews"] if item["check_id"] == "number-check-00006"
        )
        target["verdict"] = "ambiguous"
        (run_dir / "reviews" / "numeric-reviews.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.assertEqual(validate_run(run_dir), [])
        metrics = score_run(run_dir, read_json(GROUND_TRUTH_PATH))
        self.assertEqual(metrics["verdict_correct"], 13)
        self.assertEqual(metrics["high_risk_found"], 6)
        self.assertTrue(metrics["high_risk_missed"])

    def test_demo_generation_is_deterministic(self) -> None:
        first = build_demo_project(self.root / "first")
        second = build_demo_project(self.root / "second")
        for key in ("manuscript", "supplement"):
            self.assertEqual(_digest(first[key]), _digest(second[key]), key)
        first_pdfs = {path.relative_to(first["reference_dir"]).as_posix(): _digest(path) for path in first["pdfs"]}
        second_pdfs = {path.relative_to(second["reference_dir"]).as_posix(): _digest(path) for path in second["pdfs"]}
        self.assertEqual(first_pdfs, second_pdfs)

    def test_regenerating_inside_a_temp_dir_yields_identical_run_shape(self) -> None:
        run_dir = prepare(self.root)
        manifest = read_json(run_dir / "manifest.json")
        demo_summary = read_json(DEMO_ROOT / "expected" / "run-summary.json")
        self.assertEqual(manifest["counts"], demo_summary["counts"])


if __name__ == "__main__":
    unittest.main()

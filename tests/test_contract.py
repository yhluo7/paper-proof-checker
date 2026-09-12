"""结构化审核的回溯契约：候选数值、正文原文、段落级证据与可用性一致性。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from paper_proof_checker.validator import validate_run
from tests.helpers import build_project, load_reviews, prepare, save_reviews, write_standard_reviews


class ContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        build_project(self.root)
        self.run_dir = prepare(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _reset(self) -> None:
        write_standard_reviews(self.run_dir)

    def _numeric(self) -> dict:
        return load_reviews(self.run_dir, "numeric-reviews.json")

    def _citation(self) -> dict:
        return load_reviews(self.run_dir, "citation-reviews.json")

    def _expect_error(self, fragment: str) -> list[str]:
        errors = validate_run(self.run_dir)
        self.assertTrue(
            any(fragment in error for error in errors),
            f"未出现期望的错误片段[{fragment}]，实际：{errors}",
        )
        return errors

    def test_standard_answers_validate_cleanly(self) -> None:
        self._reset()
        self.assertEqual(validate_run(self.run_dir), [])
        self.assertTrue((self.run_dir / "result-trace.json").exists())
        self.assertTrue((self.run_dir / "citation-evidence.json").exists())

    def test_candidate_number_id_must_belong_to_current_check(self) -> None:
        self._reset()
        payload = self._numeric()
        exact = next(item for item in payload["reviews"] if item["check_id"] == "number-check-00002")
        exact["candidate_number_id"] = "num-00015"
        save_reviews(self.run_dir, "numeric-reviews.json", payload)
        self._expect_error("不属于当前检查返回的候选列表")

    def test_match_verdict_requires_a_candidate(self) -> None:
        self._reset()
        payload = self._numeric()
        exact = next(item for item in payload["reviews"] if item["check_id"] == "number-check-00002")
        exact["candidate_number_id"] = None
        save_reviews(self.run_dir, "numeric-reviews.json", payload)
        self._expect_error("必须提供candidate_number_id")

    def test_missing_source_must_not_fake_a_candidate(self) -> None:
        self._reset()
        payload = self._numeric()
        conflict = next(
            item for item in payload["reviews"] if item["check_id"] == "number-check-00006"
        )
        conflict["verdict"] = "source_not_found"
        save_reviews(self.run_dir, "numeric-reviews.json", payload)
        self._expect_error("不得提供候选数值")

    def test_needs_human_review_must_be_boolean(self) -> None:
        self._reset()
        payload = self._numeric()
        payload["reviews"][0]["needs_human_review"] = "yes"
        save_reviews(self.run_dir, "numeric-reviews.json", payload)
        self._expect_error("needs_human_review必须是布尔值")

    def test_unknown_check_id_is_rejected(self) -> None:
        self._reset()
        payload = self._numeric()
        payload["reviews"][0]["check_id"] = "number-check-99999"
        save_reviews(self.run_dir, "numeric-reviews.json", payload)
        self._expect_error("未知check_id")

    def test_source_quote_must_appear_verbatim_in_the_source_block(self) -> None:
        self._reset()
        payload = self._citation()
        payload["reviews"][0]["source_quote"] = "Treatment lowers death in everyone."
        save_reviews(self.run_dir, "citation-reviews.json", payload)
        self._expect_error("source_quote无法在对应正文块中逐字定位")

    def test_missing_source_quote_is_rejected(self) -> None:
        self._reset()
        payload = self._citation()
        payload["reviews"][0].pop("source_quote")
        save_reviews(self.run_dir, "citation-reviews.json", payload)
        self._expect_error("缺少正文原文source_quote")

    def test_evidence_paragraph_id_must_exist(self) -> None:
        self._reset()
        payload = self._citation()
        payload["reviews"][0]["evidence"][0]["paragraph_id"] = "p9999-b001"
        save_reviews(self.run_dir, "citation-reviews.json", payload)
        self._expect_error("paragraph_id不属于参考文献")

    def test_evidence_page_must_match_its_paragraph(self) -> None:
        self._reset()
        payload = self._citation()
        payload["reviews"][0]["evidence"][0]["page"] = 99
        save_reviews(self.run_dir, "citation-reviews.json", payload)
        self._expect_error("证据页码与段落")

    def test_quote_must_live_inside_the_claimed_paragraph(self) -> None:
        """同一页其他段落的原文不得充当该段落的证据。"""

        self._reset()
        payload = self._citation()
        payload["reviews"][0]["evidence"][0]["quote"] = (
            "We randomly assigned adults admitted with severe disease to the intervention or to usual care."
        )
        save_reviews(self.run_dir, "citation-reviews.json", payload)
        self._expect_error("证据原文无法在段落")

    def test_evidence_not_found_requires_parsed_full_text(self) -> None:
        self._reset()
        payload = self._citation()
        unavailable = next(
            item for item in payload["reviews"] if item["reference_id"] == 5
        )
        unavailable["verdict"] = "evidence_not_found"
        save_reviews(self.run_dir, "citation-reviews.json", payload)
        self._expect_error("不得使用evidence_not_found")

    def test_full_text_unavailable_must_not_carry_evidence(self) -> None:
        self._reset()
        payload = self._citation()
        unavailable = next(item for item in payload["reviews"] if item["reference_id"] == 5)
        unavailable["evidence"] = [
            {"paragraph_id": "p0001-b001", "page": 1, "section": "", "quote": "Anything."}
        ]
        save_reviews(self.run_dir, "citation-reviews.json", payload)
        self._expect_error("不得附带证据原文")

    def test_support_verdict_requires_evidence(self) -> None:
        self._reset()
        payload = self._citation()
        supported = next(item for item in payload["reviews"] if item["reference_id"] == 1)
        supported["evidence"] = []
        save_reviews(self.run_dir, "citation-reviews.json", payload)
        self._expect_error("必须附证据原文")

    def test_claim_id_must_be_unique_and_non_empty(self) -> None:
        self._reset()
        payload = self._citation()
        payload["reviews"][1]["claim_id"] = payload["reviews"][0]["claim_id"]
        save_reviews(self.run_dir, "citation-reviews.json", payload)
        self._expect_error("claim_id必须非空且唯一")

    def test_reference_id_must_match_the_batch(self) -> None:
        self._reset()
        payload = self._citation()
        payload["reviews"][0]["reference_id"] = 9
        save_reviews(self.run_dir, "citation-reviews.json", payload)
        self._expect_error("reference_id与审核批次不一致")

    def test_missing_reviews_are_reported_as_coverage_errors(self) -> None:
        self._reset()
        payload = self._citation()
        payload["reviews"] = payload["reviews"][:-1]
        save_reviews(self.run_dir, "citation-reviews.json", payload)
        self._expect_error("至少需要一条原子主张审核结果")

    def test_validation_errors_block_formal_results(self) -> None:
        self._reset()
        payload = self._numeric()
        payload["reviews"][0]["verdict"] = "made_up"
        save_reviews(self.run_dir, "numeric-reviews.json", payload)
        errors = validate_run(self.run_dir)
        self.assertTrue(errors)
        self.assertTrue((self.run_dir / "validation-errors.json").exists())
        self.assertFalse((self.run_dir / "result-trace.json").exists())
        self.assertFalse((self.run_dir / "citation-evidence.json").exists())

    def test_input_modification_blocks_validation(self) -> None:
        self._reset()
        target = self.root / "manuscript.docx"
        target.write_bytes(target.read_bytes() + b" ")
        self._expect_error("在prepare之后被修改")


if __name__ == "__main__":
    unittest.main()

"""三种检查模式的输入要求、manifest字段与旧规则版本拒绝。"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from paper_proof_checker.cli import prepare_project
from paper_proof_checker.io_utils import read_json
from paper_proof_checker.validator import RULES_VERSION, validate_run
from tests.helpers import build_project, prepare, write_standard_reviews


class CheckModeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "project"
        build_project(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _prepare(self, checks: str, reference_map: str | None = None) -> Path:
        import argparse

        namespace = argparse.Namespace(
            project=str(self.root),
            manuscript="manuscript.docx",
            supplement="supplement.docx",
            references="references",
            checks=checks,
            reference_map=reference_map,
            output="paper-proof-output",
        )
        with contextlib.redirect_stdout(io.StringIO()):
            prepare_project(namespace)
        return sorted(
            path for path in (self.root / "paper-proof-output").iterdir() if path.is_dir()
        )[-1]

    def test_numbers_mode_succeeds_without_reference_directory(self) -> None:
        shutil.rmtree(self.root / "references")
        run_dir = self._prepare("numbers")
        self.assertTrue((run_dir / "batches" / "numeric.json").exists())
        self.assertFalse((run_dir / "batches" / "citation.json").exists())
        self.assertFalse((run_dir / "references.json").exists())
        manifest = read_json(run_dir / "manifest.json")
        self.assertEqual(manifest["enabled_checks"], ["numbers"])
        self.assertIsNone(manifest["references_dir"])

    def test_citations_mode_requires_reference_directory(self) -> None:
        shutil.rmtree(self.root / "references")
        with self.assertRaises(ValueError) as context:
            self._prepare("citations")
        self.assertIn("需要参考文献目录", str(context.exception))

    def test_all_mode_requires_reference_directory(self) -> None:
        shutil.rmtree(self.root / "references")
        with self.assertRaises(ValueError):
            self._prepare("all")

    def test_citations_mode_skips_numeric_batch(self) -> None:
        run_dir = self._prepare("citations")
        self.assertTrue((run_dir / "batches" / "citation.json").exists())
        self.assertFalse((run_dir / "batches" / "numeric.json").exists())

    def test_manifest_records_rules_version_and_enabled_checks(self) -> None:
        run_dir = self._prepare("all")
        manifest = read_json(run_dir / "manifest.json")
        self.assertEqual(manifest["rules_version"], RULES_VERSION)
        self.assertEqual(manifest["enabled_checks"], ["numbers", "citations"])
        self.assertEqual(manifest["counts"]["number_checks"], 9)
        self.assertEqual(manifest["counts"]["citation_checks"], 5)
        self.assertIn("batches/numeric.json", manifest["files"]["batches"])
        self.assertIn("reviews/citation-reviews.json", manifest["files"]["reviews"])

    def test_numbers_mode_validation_and_report_skip_citation_files(self) -> None:
        from paper_proof_checker.report import build_report

        run_dir = self._prepare("numbers")
        write_standard_reviews(run_dir)
        self.assertEqual(validate_run(run_dir), [])
        self.assertFalse((run_dir / "citation-evidence.json").exists())
        report = build_report(run_dir).read_text(encoding="utf-8")
        self.assertIn("数值冲突与缺失来源", report)
        self.assertNotIn("完整引用证据矩阵", report)

    def test_validator_rejects_old_rules_version(self) -> None:
        run_dir = prepare(self.root)
        manifest = read_json(run_dir / "manifest.json")
        manifest["rules_version"] = 1
        (run_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        errors = validate_run(run_dir)
        self.assertTrue(any("旧规则版本" in error for error in errors))
        self.assertTrue(any("重新执行prepare" in error for error in errors))

    def test_validator_rejects_missing_manifest(self) -> None:
        empty = Path(self.temporary.name) / "empty-run"
        empty.mkdir()
        errors = validate_run(empty)
        self.assertTrue(any("manifest.json" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

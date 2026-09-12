"""报告内容、相对路径、重复运行、中文/空格路径与CLI的UTF-8输出。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from paper_proof_checker.report import build_report
from tests.helpers import build_project, prepare, prepare_valid_run


REPO_ROOT = Path(__file__).resolve().parents[1]


class ReportAndCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "project"
        build_project(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _valid_run(self, project: Path | None = None, checks: str = "all") -> Path:
        """准备一个已通过validate的运行目录：report只接受验证通过的数据。"""

        target = project or self.root
        return prepare_valid_run(target, checks=checks)

    def test_report_uses_project_relative_paths_only(self) -> None:
        run_dir = self._valid_run()
        report = build_report(run_dir).read_text(encoding="utf-8")
        self.assertIn("`manuscript.docx`", report)
        self.assertNotIn(str(self.root), report)
        self.assertNotIn(str(run_dir), report)

    def test_report_contains_action_summary_and_coverage(self) -> None:
        run_dir = self._valid_run()
        report = build_report(run_dir).read_text(encoding="utf-8")
        self.assertIn("作者行动摘要", report)
        self.assertIn("输入文件与检查覆盖率", report)
        self.assertIn("明确未覆盖内容", report)
        self.assertIn("已匹配本地全文：4/5", report)

    def test_report_is_blocked_after_input_modification(self) -> None:
        run_dir = self._valid_run()
        target = self.root / "manuscript.docx"
        target.write_bytes(target.read_bytes() + b" ")
        with self.assertRaises(ValueError) as context:
            build_report(run_dir)
        self.assertIn("在prepare之后发生变化", str(context.exception))

    def test_report_requires_successful_validation(self) -> None:
        run_dir = prepare(self.root)
        with self.assertRaises(ValueError) as context:
            build_report(run_dir)
        self.assertIn("尚未通过validate", str(context.exception))

    def test_repeated_runs_never_overwrite_history(self) -> None:
        first = prepare(self.root, checks="numbers")
        second = prepare(self.root, checks="numbers")
        self.assertNotEqual(first, second)
        self.assertTrue((first / "manifest.json").exists())
        self.assertTrue((second / "manifest.json").exists())

    def test_chinese_and_space_paths_work_end_to_end(self) -> None:
        project = Path(self.temporary.name) / "论文 项目 2026"
        build_project(project)
        run_dir = prepare_valid_run(project)
        report = build_report(run_dir)
        self.assertTrue(report.exists())
        self.assertIn("论文", str(report))

    def test_cli_writes_utf8_json_on_stdout_for_chinese_path(self) -> None:
        project = Path(self.temporary.name) / "中文 目录"
        build_project(project)
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(REPO_ROOT / "src")
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "paper_proof_checker.cli",
                "prepare",
                str(project),
                "--checks",
                "numbers",
            ],
            capture_output=True,
            cwd=str(REPO_ROOT),
            env=environment,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        text = completed.stdout.decode("utf-8")
        payload = json.loads(text)
        self.assertEqual(payload["status"], "prepared")
        self.assertIn("中文 目录", payload["run_dir"])

    def test_cli_reports_errors_on_stderr_with_exit_code_two(self) -> None:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(REPO_ROOT / "src")
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "paper_proof_checker.cli",
                "prepare",
                str(Path(self.temporary.name) / "不存在的项目"),
                "--checks",
                "numbers",
            ],
            capture_output=True,
            cwd=str(REPO_ROOT),
            env=environment,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("错误", completed.stderr.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()

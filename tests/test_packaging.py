"""打包与Skill安装：wheel内容完整性、安装不覆盖既有Skill。"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from paper_proof_checker.cli import install_skill, _skill_source


REPO_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_SKILL_FILES = {
    "SKILL.md",
    "agents/openai.yaml",
    "references/result-check-rules.md",
    "references/citation-check-rules.md",
    "references/output-schema.md",
    "references/manuscript-input-rules.md",
}


class PackagingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_skill_source_contains_every_published_file(self) -> None:
        source = _skill_source()
        for relative in EXPECTED_SKILL_FILES:
            self.assertTrue((source / relative).is_file(), relative)

    def test_install_skill_does_not_overwrite_and_supports_both_targets(self) -> None:
        codex_home = self.root / "codex-home"
        claude_home = self.root / "claude-home"
        args = argparse.Namespace(target="both", force=False)
        with patch.dict(
            os.environ,
            {"CODEX_HOME": str(codex_home), "HOME": str(self.root), "USERPROFILE": str(self.root)},
        ):
            with patch("paper_proof_checker.cli.Path.home", return_value=claude_home):
                self.assertEqual(install_skill(args), 0)
                codex_skill = codex_home / "skills" / "paper-proof-checker"
                claude_skill = claude_home / ".claude" / "skills" / "paper-proof-checker"
                for skill in (codex_skill, claude_skill):
                    for relative in EXPECTED_SKILL_FILES:
                        self.assertTrue((skill / relative).is_file(), relative)
                with self.assertRaises(ValueError):
                    install_skill(args)
                self.assertEqual(
                    install_skill(argparse.Namespace(target="codex", force=True)), 0
                )

    def test_wheel_contains_complete_skill_and_references(self) -> None:
        """构建wheel并检查Skill文件随包发布。"""

        try:
            import build  # noqa: F401
        except Exception:  # pragma: no cover - 环境缺少build模块时跳过
            self.skipTest("未安装build模块，跳过wheel构建")

        output = self.root / "dist"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                str(output),
            ],
            capture_output=True,
            cwd=str(REPO_ROOT),
            timeout=300,
        )
        if completed.returncode != 0:
            self.fail(completed.stderr.decode("utf-8", errors="replace")[-2000:])
        wheels = list(output.glob("*.whl"))
        self.assertEqual(len(wheels), 1)
        with zipfile.ZipFile(wheels[0]) as archive:
            names = set(archive.namelist())
        share_prefix = "paper_proof_checker-0.2.0.data/data/share/paper-proof-checker/"
        for relative in EXPECTED_SKILL_FILES:
            self.assertIn(share_prefix + relative, names)
        self.assertIn("paper_proof_checker/cli.py", names)
        self.assertIn("paper_proof_checker/pdf_parser.py", names)


if __name__ == "__main__":
    unittest.main()

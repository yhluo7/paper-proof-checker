"""测试公用的项目构造与准备逻辑。"""

from __future__ import annotations

import argparse
import contextlib
import io
from pathlib import Path

from paper_proof_checker.cli import prepare_project
from paper_proof_checker.io_utils import read_json, write_json
from paper_proof_checker.validator import validate_run
from tools.benchmark import build_expected_reviews, resolve_ground_truth
from tools.demo_data import build_demo_project


def build_project(root: Path) -> dict:
    """用与公开Demo完全相同的生成逻辑构造一个合成项目。"""

    return build_demo_project(root)


def prepare(
    project: Path,
    checks: str = "all",
    reference_map: str | None = "reference-map.json",
    supplement: str | None = "supplement.docx",
) -> Path:
    """调用真实prepare入口并返回新运行目录。"""

    namespace = argparse.Namespace(
        project=str(project),
        manuscript="manuscript.docx",
        supplement=supplement,
        references="references",
        checks=checks,
        reference_map=reference_map,
        output="paper-proof-output",
    )
    with contextlib.redirect_stdout(io.StringIO()):
        prepare_project(namespace)
    return sorted(path for path in (project / "paper-proof-output").iterdir() if path.is_dir())[-1]


def write_standard_reviews(run_dir: Path) -> dict:
    """按冻结标准答案写入可通过验证的参考审核JSON，返回标准答案。

    只写入已启用模块对应的文件，因此对 --checks numbers 的运行目录同样适用。
    """

    enabled = read_json(run_dir / "manifest.json")["enabled_checks"]
    kinds = tuple(
        kind
        for kind, module in (("number", "numbers"), ("citation", "citations"))
        if module in enabled
    )
    ground_truth = resolve_ground_truth(run_dir, kinds=kinds)
    numeric, citation = build_expected_reviews(run_dir, ground_truth)
    if "numbers" in enabled:
        write_json(run_dir / "reviews" / "numeric-reviews.json", numeric)
    if "citations" in enabled:
        write_json(run_dir / "reviews" / "citation-reviews.json", citation)
    return ground_truth


def prepare_valid_run(
    project: Path,
    checks: str = "all",
    reference_map: str | None = "reference-map.json",
) -> Path:
    """准备一个已经写入标准答案并通过验证的运行目录。"""

    run_dir = prepare(project, checks=checks, reference_map=reference_map)
    write_standard_reviews(run_dir)
    errors = validate_run(run_dir)
    if errors:
        raise AssertionError(f"标准答案未通过验证：{errors}")
    return run_dir


def load_reviews(run_dir: Path, name: str) -> dict:
    return read_json(run_dir / "reviews" / name)


def save_reviews(run_dir: Path, name: str, payload: dict) -> None:
    write_json(run_dir / "reviews" / name, payload)

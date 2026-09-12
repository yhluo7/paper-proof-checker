"""paper-proof命令行入口。

0.2 变更：
- prepare 增加 --checks（all|numbers|citations）与 --reference-map。
- numbers模式不要求参考文献目录；citations与all模式要求。
- manifest 增加 enabled_checks 与 rules_version=2。
- 启动时统一把标准输出与标准错误配置为UTF-8，避免Windows中文乱码。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .docx_parser import parse_docx
from .evidence_search import build_citation_batch, search_pdf_text
from .io_utils import read_json, sha256_file, write_json
from .number_extractor import build_number_batch
from .reference_mapper import (
    build_reference_index,
    build_reference_mapping_markdown,
    load_reference_map,
)
from .report import build_report
from .validator import RULES_VERSION, validate_run


CHECK_MODES = ("all", "numbers", "citations")


def _configure_utf8_streams() -> None:
    """把标准输出与标准错误统一为UTF-8，保证中文与★类字符不报错。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # 部分被重定向的流不支持reconfigure。
            pass


def _new_run_dir(output_root: Path) -> Path:
    """创建不覆盖历史结果的时间戳目录。"""

    stem = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = output_root / stem
    suffix = 1
    while candidate.exists():
        candidate = output_root / f"{stem}-{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True)
    (candidate / "batches").mkdir()
    (candidate / "reviews").mkdir()
    return candidate


def _input_record(path: Path) -> dict:
    """记录绝对路径和哈希，不复制用户原文件。"""

    return {"path": str(path.resolve()), "sha256": sha256_file(path)}


def _relative_to_project(path: Path, project: Path) -> str:
    """尽量给出项目相对路径，失败时退回文件名。"""

    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        return path.name


def prepare_project(args: argparse.Namespace) -> int:
    """完成所有确定性解析并生成模型审核批次。"""

    project = Path(args.project).resolve()
    checks = args.checks
    want_numbers = checks in {"all", "numbers"}
    want_citations = checks in {"all", "citations"}

    manuscript = project / args.manuscript
    supplement = project / args.supplement if args.supplement else None
    if supplement and not supplement.exists():
        supplement = None
    references_dir = project / args.references if args.references else None

    if not manuscript.is_file():
        raise ValueError(f"主文不存在：{manuscript}")
    if want_citations:
        if references_dir is None or not references_dir.is_dir():
            raise ValueError(
                f"{checks}模式需要参考文献目录，但不存在：{references_dir}。"
                "如只想检查数值，请改用 --checks numbers。"
            )
    else:
        # numbers模式不读取参考文献目录，manifest也不应记录它。
        references_dir = None

    run_dir = _new_run_dir(project / args.output)
    main = parse_docx(manuscript, "manuscript", require_vancouver=want_citations)
    documents = [main]
    if supplement:
        documents.append(parse_docx(supplement, "supplement"))
    combined = {
        "blocks": [block for document in documents for block in document["blocks"]],
        "citations": [citation for document in documents for citation in document["citations"]],
        "references": main["references"],
        "sources": [document["source_path"] for document in documents],
    }
    write_json(run_dir / "document.json", combined)

    references: list[dict] = []
    reference_map_record = None
    manual_map: dict[int, Path] = {}
    if want_citations and references_dir is not None:
        if args.reference_map:
            map_path = Path(args.reference_map)
            if not map_path.is_absolute():
                map_path = project / map_path
            manual_map = load_reference_map(map_path, references_dir)
            reference_map_record = {
                "path": _relative_to_project(map_path, project),
                "entries": {
                    str(reference_id): _relative_to_project(path, references_dir)
                    for reference_id, path in sorted(manual_map.items())
                },
            }
        references = build_reference_index(
            main["references"], references_dir, run_dir, manual_map
        )
        write_json(run_dir / "references.json", {"references": references})
        (run_dir / "reference-mapping.md").write_text(
            build_reference_mapping_markdown(references, len(manual_map)), encoding="utf-8"
        )

    number_batch: list[dict] = []
    citation_batch: list[dict] = []
    if want_numbers:
        number_batch = build_number_batch(combined["blocks"])
        write_json(run_dir / "batches" / "numeric.json", {"checks": number_batch})
    if want_citations:
        citation_batch = build_citation_batch(combined, references)
        write_json(run_dir / "batches" / "citation.json", {"checks": citation_batch})

    inputs = {"manuscript": _input_record(manuscript)}
    if supplement:
        inputs["supplement"] = _input_record(supplement)
    enabled_checks = []
    if want_numbers:
        enabled_checks.append("numbers")
    if want_citations:
        enabled_checks.append("citations")
    manifest = {
        "tool": "paper-proof-checker",
        "version": __version__,
        "rules_version": RULES_VERSION,
        "enabled_checks": enabled_checks,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "project_dir": str(project),
        "inputs": inputs,
        "references_dir": str(references_dir.resolve()) if references_dir else None,
        "reference_map": reference_map_record,
        "counts": {
            "blocks": len(combined["blocks"]),
            "references": len(references),
            "number_checks": len(number_batch),
            "citation_checks": len(citation_batch),
        },
    }
    manifest["files"] = {
        "batches": [
            name
            for name, enabled in (
                ("batches/numeric.json", want_numbers),
                ("batches/citation.json", want_citations),
            )
            if enabled
        ],
        "reviews": [
            name
            for name, enabled in (
                ("reviews/numeric-reviews.json", want_numbers),
                ("reviews/citation-reviews.json", want_citations),
            )
            if enabled
        ],
    }
    write_json(run_dir / "manifest.json", manifest)

    print(json.dumps({"run_dir": str(run_dir), "status": "prepared"}, ensure_ascii=False))
    return 0


def search_evidence_command(args: argparse.Namespace) -> int:
    """在指定参考文献全文内执行补充检索。"""

    run_dir = Path(args.run_dir).resolve()
    references = read_json(run_dir / "references.json")["references"]
    reference = next((item for item in references if item["reference_id"] == args.reference), None)
    if not reference:
        raise ValueError(f"不存在参考文献编号：{args.reference}")
    if reference["match_status"] != "matched":
        raise ValueError(f"参考文献{args.reference}没有可检索全文：{reference['match_status']}")
    results = search_pdf_text(Path(reference["text_path"]), args.query, args.limit)
    print(json.dumps({"reference_id": args.reference, "results": results}, ensure_ascii=False, indent=2))
    return 0


def validate_command(args: argparse.Namespace) -> int:
    """验证模型审核JSON；失败时返回非零退出码。"""

    run_dir = Path(args.run_dir).resolve()
    errors = validate_run(run_dir)
    if errors:
        print(json.dumps({"status": "invalid", "errors": errors}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"status": "valid", "run_dir": str(run_dir)}, ensure_ascii=False))
    return 0


def report_command(args: argparse.Namespace) -> int:
    """生成正式Markdown报告。"""

    report_path = build_report(Path(args.run_dir).resolve())
    print(json.dumps({"status": "reported", "report": str(report_path)}, ensure_ascii=False))
    return 0


def _skill_source() -> Path:
    """兼容源码安装和构建后的pipx环境。"""

    installed = Path(sys.prefix) / "share" / "paper-proof-checker"
    if (installed / "SKILL.md").exists():
        return installed
    source = Path(__file__).resolve().parents[2] / "skill" / "paper-proof-checker"
    if (source / "SKILL.md").exists():
        return source
    raise ValueError("找不到随包发布的Skill源码，请重新安装paper-proof-checker。")


def install_skill(args: argparse.Namespace) -> int:
    """把同一份Skill复制到Codex、Claude或两者的个人目录。"""

    source = _skill_source()
    targets = []
    if args.target in {"codex", "both"}:
        codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        targets.append(("codex", codex_home / "skills" / "paper-proof-checker"))
    if args.target in {"claude", "both"}:
        targets.append(("claude", Path.home() / ".claude" / "skills" / "paper-proof-checker"))

    installed = []
    for name, destination in targets:
        if destination.exists():
            if not args.force:
                raise ValueError(f"{name} Skill已存在，不会覆盖：{destination}。确认后可使用--force。")
            # 目标由固定个人Skill目录和固定名称组成，避免删除任意用户路径。
            if destination.name != "paper-proof-checker" or destination.parent.name != "skills":
                raise ValueError(f"拒绝清理非标准Skill目录：{destination}")
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        installed.append({"target": name, "path": str(destination)})
    print(json.dumps({"status": "installed", "skills": installed}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """集中声明稳定的命令行接口。"""

    parser = argparse.ArgumentParser(prog="paper-proof", description="本地论文终审检查工具")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="解析输入并生成审核批次")
    prepare.add_argument("project")
    prepare.add_argument("--manuscript", default="manuscript.docx")
    prepare.add_argument("--supplement", default="supplement.docx")
    prepare.add_argument("--references", default="references")
    prepare.add_argument(
        "--checks",
        choices=CHECK_MODES,
        default="all",
        help="all=数值与引用；numbers=只检查数值且不需要参考文献目录；citations=只检查引用",
    )
    prepare.add_argument(
        "--reference-map",
        default=None,
        help="手工映射文件，形如 {\"1\": \"Smith_2022.pdf\"}，优先于自动匹配",
    )
    prepare.add_argument("--output", default="paper-proof-output")
    prepare.set_defaults(handler=prepare_project)

    search = subparsers.add_parser("search-evidence", help="在一篇被引PDF中补充检索")
    search.add_argument("run_dir")
    search.add_argument("--reference", type=int, required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=8)
    search.set_defaults(handler=search_evidence_command)

    validate = subparsers.add_parser("validate", help="验证模型审核JSON")
    validate.add_argument("run_dir")
    validate.set_defaults(handler=validate_command)

    report = subparsers.add_parser("report", help="生成正式Markdown报告")
    report.add_argument("run_dir")
    report.set_defaults(handler=report_command)

    install = subparsers.add_parser("install-skill", help="安装Codex或Claude Skill")
    install.add_argument("--target", choices=["codex", "claude", "both"], required=True)
    install.add_argument("--force", action="store_true", help="明确覆盖同名Skill")
    install.set_defaults(handler=install_skill)
    return parser


def main() -> int:
    """把可预期错误转换成简洁退出信息。"""

    _configure_utf8_streams()
    args = build_parser().parse_args()
    try:
        return int(args.handler(args))
    except (ValueError, FileNotFoundError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

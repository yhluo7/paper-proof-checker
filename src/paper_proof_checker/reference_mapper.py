"""把文末参考文献条目与本地PDF建立可解释、可复核的对应关系。

0.2 变更：
- 递归发现大小写不同的PDF扩展名，不再只扫描顶层。
- 支持手工映射文件，且手工映射优先于自动匹配。
- 对成功匹配的PDF记录SHA-256，供验证与报告阶段复查文件未发生变化。
- 额外生成便于人工阅读的 reference-mapping.md。
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

from .io_utils import normalize_space, sha256_file, write_json
from .pdf_parser import DOI_PATTERN, PMID_PATTERN, parse_pdf


YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
PDF_SUFFIX = ".pdf"


def discover_pdfs(reference_dir: Path) -> list[Path]:
    """递归发现参考文献目录下所有PDF，扩展名大小写不敏感。"""

    return sorted(
        path
        for path in reference_dir.rglob("*")
        if path.is_file() and path.suffix.lower() == PDF_SUFFIX
    )


def load_reference_map(map_path: Path, reference_dir: Path) -> dict[int, Path]:
    """读取并校验手工映射文件，返回 reference_id -> 绝对路径。

    拒绝规则：条目不是对象、编号非正整数、路径为空、文件不存在、不是PDF、
    路径逃离参考文献目录、同一个文件被分配给多个编号。
    """

    if not map_path.exists():
        raise ValueError(f"映射文件不存在：{map_path}")
    import json

    try:
        payload = json.loads(map_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"映射文件不是有效JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("映射文件顶层必须是JSON对象，形如 {\"1\": \"Smith_2022.pdf\"}。")

    root = reference_dir.resolve()
    mapping: dict[int, Path] = {}
    owners: dict[Path, int] = {}
    for raw_id, raw_path in payload.items():
        if not isinstance(raw_id, str) or not raw_id.strip().isdigit():
            raise ValueError(f"映射文件编号必须是正整数字符串：{raw_id!r}")
        reference_id = int(raw_id)
        if reference_id <= 0:
            raise ValueError(f"映射文件编号必须大于0：{reference_id}")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(f"参考文献{reference_id}的映射路径为空。")
        resolved = (root / raw_path.strip()).resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"参考文献{reference_id}的映射路径逃离参考文献目录：{raw_path}"
            ) from exc
        if resolved.suffix.lower() != PDF_SUFFIX:
            raise ValueError(f"参考文献{reference_id}的映射目标不是PDF：{raw_path}")
        if not resolved.is_file():
            raise ValueError(f"参考文献{reference_id}的映射文件不存在：{raw_path}")
        if resolved in owners:
            raise ValueError(
                f"同一文件被重复分配：参考文献{owners[resolved]}与{reference_id}都指向{relative.as_posix()}"
            )
        owners[resolved] = reference_id
        mapping[reference_id] = resolved
    return mapping


def _normalized_title(text: str) -> str:
    """去除标点和常见参考文献尾部信息，供模糊匹配使用。"""

    text = DOI_PATTERN.sub("", text)
    text = PMID_PATTERN.sub("", text)
    words = re.findall(r"[a-z0-9]+", text.lower())
    return " ".join(words[:40])


def _entry_metadata(entry: dict) -> dict:
    """从参考文献原始条目提取用于匹配的最少元数据。"""

    raw = entry["raw_entry"]
    doi = DOI_PATTERN.search(raw)
    pmid = PMID_PATTERN.search(raw)
    year = YEAR_PATTERN.search(raw)
    first_author = re.split(r"[,.;\s]", raw.strip(), maxsplit=1)[0].lower()
    return {
        "doi": doi.group(0).rstrip(".,;)").lower() if doi else None,
        "pmid": pmid.group(1) if pmid else None,
        "year": year.group(0) if year else None,
        "first_author": first_author,
        "title_key": _normalized_title(raw),
    }


def _parse_reference_pdfs(reference_dir: Path, run_dir: Path) -> list[dict]:
    """逐个解析PDF并把全文另存，控制主索引文件大小。"""

    pdf_text_dir = run_dir / "pdf_text"
    pdf_text_dir.mkdir(parents=True, exist_ok=True)
    root = reference_dir.resolve()
    parsed_pdfs = []
    for pdf_index, pdf_path in enumerate(discover_pdfs(reference_dir), start=1):
        parsed = parse_pdf(pdf_path)
        text_path = pdf_text_dir / f"pdf-{pdf_index:04d}.json"
        write_json(text_path, parsed)
        metadata = parsed.get("metadata", {})
        parsed_pdfs.append(
            {
                "pdf_path": str(pdf_path.resolve()),
                "relative_path": pdf_path.resolve().relative_to(root).as_posix(),
                "file_key": _normalized_title(pdf_path.stem),
                "text_path": str(text_path.resolve()),
                "status": parsed["status"],
                "error": parsed.get("error"),
                "doi": (metadata.get("doi") or "").lower() or None,
                "pmid": metadata.get("pmid"),
                "title": metadata.get("title", ""),
                "title_key": _normalized_title(metadata.get("title", "")),
                "author": metadata.get("author", "").lower(),
            }
        )
    return parsed_pdfs


def _auto_match(meta: dict, parsed_pdfs: list[dict]) -> list[tuple[float, str, dict]]:
    """按DOI、PMID、标题、作者年份的顺序自动匹配，不做唯一性裁决。"""

    candidates: list[tuple[float, str, dict]] = []
    for pdf in parsed_pdfs:
        if pdf["status"] != "parsed":
            continue
        if meta["doi"] and pdf["doi"] == meta["doi"]:
            candidates.append((1.0, "doi", pdf))
            continue
        if meta["pmid"] and pdf["pmid"] == meta["pmid"]:
            candidates.append((1.0, "pmid", pdf))
            continue
        score = SequenceMatcher(None, meta["title_key"], pdf["title_key"]).ratio()
        if score >= 0.82:
            candidates.append((score, "title", pdf))
            continue
        author_year = bool(
            meta["first_author"]
            and meta["first_author"] in pdf["author"]
            and (not meta["year"] or meta["year"] in pdf["title_key"])
        )
        if author_year and score >= 0.55:
            candidates.append((score, "author_year_title", pdf))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates


def build_reference_index(
    entries: list[dict],
    reference_dir: Path,
    run_dir: Path,
    manual_map: dict[int, Path] | None = None,
) -> list[dict]:
    """逐个匹配参考文献条目与本地PDF全文。"""

    manual_map = manual_map or {}
    parsed_pdfs = _parse_reference_pdfs(reference_dir, run_dir)
    by_path = {Path(pdf["pdf_path"]): pdf for pdf in parsed_pdfs}

    results = []
    for entry in entries:
        meta = _entry_metadata(entry)
        base = {**entry, **meta}
        mapped_path = manual_map.get(entry["reference_id"])
        if mapped_path is not None:
            # 手工映射优先于自动匹配，解析失败也按失败状态如实报告。
            pdf = by_path.get(mapped_path.resolve())
            if pdf is None:
                results.append(
                    {
                        **base,
                        "pdf_path": str(mapped_path.resolve()),
                        "relative_path": None,
                        "text_path": None,
                        "match_status": "parse_failed",
                        "match_method": "manual_map",
                        "match_score": None,
                        "sha256": None,
                        "error": "映射文件指向的PDF未被解析。",
                    }
                )
                continue
            if pdf["status"] != "parsed":
                results.append(
                    {
                        **base,
                        "pdf_path": pdf["pdf_path"],
                        "relative_path": pdf["relative_path"],
                        "text_path": pdf["text_path"],
                        "match_status": "parse_failed",
                        "match_method": "manual_map",
                        "match_score": None,
                        "sha256": sha256_file(Path(pdf["pdf_path"])),
                        "error": pdf["error"],
                    }
                )
                continue
            results.append(
                {
                    **base,
                    "pdf_path": pdf["pdf_path"],
                    "relative_path": pdf["relative_path"],
                    "text_path": pdf["text_path"],
                    "match_status": "matched",
                    "match_method": "manual_map",
                    "match_score": None,
                    "sha256": sha256_file(Path(pdf["pdf_path"])),
                }
            )
            continue

        candidates = _auto_match(meta, parsed_pdfs)
        if not candidates:
            failed_candidates = [
                pdf
                for pdf in parsed_pdfs
                if pdf["status"] == "parse_failed"
                and meta["first_author"] in pdf["file_key"]
                and (not meta["year"] or meta["year"] in pdf["file_key"])
            ]
            # 单条参考文献配单个失败PDF时也可以安全确认对应关系。
            if not failed_candidates and len(entries) == 1 and len(parsed_pdfs) == 1:
                only_pdf = parsed_pdfs[0]
                failed_candidates = [only_pdf] if only_pdf["status"] == "parse_failed" else []
            if len(failed_candidates) == 1:
                failed_pdf = failed_candidates[0]
                results.append(
                    {
                        **base,
                        "pdf_path": failed_pdf["pdf_path"],
                        "relative_path": failed_pdf["relative_path"],
                        "text_path": failed_pdf["text_path"],
                        "match_status": "parse_failed",
                        "match_method": "filename_or_single_file",
                        "match_score": None,
                        "sha256": sha256_file(Path(failed_pdf["pdf_path"])),
                        "error": failed_pdf["error"],
                    }
                )
                continue
            results.append(
                {
                    **base,
                    "pdf_path": None,
                    "relative_path": None,
                    "text_path": None,
                    "match_status": "missing_pdf",
                    "match_method": None,
                    "match_score": None,
                    "sha256": None,
                }
            )
            continue

        top_score, method, top_pdf = candidates[0]
        if len(candidates) > 1 and top_score - candidates[1][0] < 0.05:
            results.append(
                {
                    **base,
                    "pdf_path": None,
                    "relative_path": None,
                    "text_path": None,
                    "match_status": "ambiguous",
                    "match_method": method,
                    "match_score": round(top_score, 4),
                    "sha256": None,
                    "candidate_pdf_paths": [item[2]["pdf_path"] for item in candidates[:3]],
                }
            )
            continue
        results.append(
            {
                **base,
                "pdf_path": top_pdf["pdf_path"],
                "relative_path": top_pdf["relative_path"],
                "text_path": top_pdf["text_path"],
                "match_status": "matched",
                "match_method": method,
                "match_score": round(top_score, 4),
                "sha256": sha256_file(Path(top_pdf["pdf_path"])),
            }
        )
    return results


def build_reference_mapping_markdown(references: list[dict], manual_map_size: int) -> str:
    """生成人工可读的参考文献映射表。"""

    lines = [
        "# 参考文献与PDF映射",
        "",
        f"- 参考文献条目数：{len(references)}",
        f"- 手工映射条目数：{manual_map_size}",
        "- 手工映射优先于自动匹配；标记为 `manual_map` 的条目由映射文件决定。",
        "",
        "| 编号 | 状态 | 匹配方式 | 匹配得分 | PDF文件 | 参考文献条目 |",
        "|---:|---|---|---:|---|---|",
    ]
    for reference in references:
        entry = normalize_space(reference.get("raw_entry", ""))
        if len(entry) > 120:
            entry = entry[:117] + "..."
        lines.append(
            "| {id} | {status} | {method} | {score} | {pdf} | {entry} |".format(
                id=reference["reference_id"],
                status=reference["match_status"],
                method=reference.get("match_method") or "—",
                score=(
                    reference["match_score"]
                    if reference.get("match_score") is not None
                    else "—"
                ),
                pdf=reference.get("relative_path") or "—",
                entry=entry.replace("|", "\\|"),
            )
        )
    lines.append("")
    return "\n".join(lines)

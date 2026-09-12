"""验证模型审核结果，阻止无法回溯的内容进入正式报告。

0.2 变更：
- 数值审核必须精确指向当前检查实际返回的候选数值（candidate_number_id）。
- 引用审核必须给出正文原文（source_quote），并让证据落在具体段落（paragraph_id + page + quote）。
- needs_human_review 必须是布尔值。
- verdict 与参考文献可用性必须一致：没有全文不得声称"未找到证据"。
- 按 manifest 的 enabled_checks 只校验已启用模块。
- 正式结果生成前重新核对输入文件与已匹配PDF的哈希。
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .io_utils import normalized_contains, read_json, sha256_file, write_json


RULES_VERSION = 2

NUMBER_VERDICTS = {
    "exact_match",
    "converted_match",
    "rounded_match",
    "threshold_compatible",
    "ambiguous",
    "conflict",
    "source_not_found",
    "manual_figure_check",
    "not_a_result",
}
CITATION_VERDICTS = {
    "direct_support",
    "inference_support",
    "partial_support",
    "background_only",
    "secondary_support",
    "conflict",
    "evidence_not_found",
    "full_text_unavailable",
    "parse_failed",
    "manual_review",
}
CONFIDENCE_VALUES = {"high", "medium", "low"}

# 选择这些判断时必须给出候选数值；这些判断不得伪造候选来源。
MATCH_VERDICTS = {"exact_match", "converted_match", "rounded_match", "threshold_compatible"}
CANDIDATE_REQUIRED = MATCH_VERDICTS | {"conflict"}
CANDIDATE_FORBIDDEN = {"source_not_found", "not_a_result", "manual_figure_check"}
# 这些判断必须附带证据原文。
EVIDENCE_REQUIRED = {
    "direct_support",
    "inference_support",
    "partial_support",
    "background_only",
    "secondary_support",
    "conflict",
}
# 这些判断不得附带证据原文（否则等于伪造全文）。
EVIDENCE_FORBIDDEN = {"evidence_not_found", "full_text_unavailable", "parse_failed"}
MAX_EVIDENCE_ITEMS = 3


def verify_hashes(manifest: dict, references: list[dict] | None = None) -> list[str]:
    """重新核对主文、补充材料和已匹配PDF是否在prepare之后被修改。"""

    errors: list[str] = []
    for name, record in (manifest.get("inputs") or {}).items():
        path = Path(str(record.get("path", "")))
        if not path.is_file():
            errors.append(f"输入文件已不存在：{name} -> {path}")
            continue
        if record.get("sha256") and sha256_file(path) != record["sha256"]:
            errors.append(
                f"输入文件{name}在prepare之后被修改，禁止生成结果；请重新执行prepare。"
            )
    for reference in references or []:
        if reference.get("match_status") != "matched" or not reference.get("sha256"):
            continue
        path = Path(str(reference.get("pdf_path", "")))
        if not path.is_file():
            errors.append(
                f"参考文献{reference['reference_id']}的PDF已不存在："
                f"{reference.get('relative_path') or path.name}"
            )
            continue
        if sha256_file(path) != reference["sha256"]:
            errors.append(
                f"参考文献{reference['reference_id']}的PDF在prepare之后被修改，"
                "禁止生成结果；请重新执行prepare。"
            )
    return errors


def load_manifest(run_dir: Path) -> tuple[dict | None, list[str]]:
    """读取运行清单，并拒绝旧规则版本的运行目录。"""

    path = run_dir / "manifest.json"
    if not path.exists():
        return None, [f"缺少准备阶段文件：{path}。请重新执行prepare。"]
    try:
        manifest = read_json(path)
    except Exception as exc:
        return None, [f"manifest.json不是有效JSON：{exc}"]
    if not isinstance(manifest, dict):
        return None, ["manifest.json顶层必须是JSON对象。"]
    if manifest.get("rules_version") != RULES_VERSION:
        return None, [
            "运行目录使用的是旧规则版本"
            f"（rules_version={manifest.get('rules_version')!r}），"
            f"0.2验证器只接受rules_version={RULES_VERSION}。请重新执行prepare。"
        ]
    enabled = manifest.get("enabled_checks")
    if not isinstance(enabled, list) or not enabled:
        return None, ["manifest.json缺少有效的enabled_checks。请重新执行prepare。"]
    unknown = [item for item in enabled if item not in {"numbers", "citations"}]
    if unknown:
        return None, [f"manifest.json包含未知检查模块：{unknown}"]
    return manifest, []


def _load_reviews(path: Path, label: str, errors: list[str]) -> list[dict]:
    """读取统一的reviews数组，并把格式错误转成用户可读信息。"""

    if not path.exists():
        errors.append(f"缺少{label}审核文件：{path}")
        return []
    try:
        payload = read_json(path)
    except Exception as exc:
        errors.append(f"{label}审核文件不是有效JSON：{exc}")
        return []
    reviews = payload.get("reviews") if isinstance(payload, dict) else None
    if not isinstance(reviews, list):
        errors.append(f"{label}审核文件必须包含reviews数组。")
        return []
    return reviews


def _validate_numeric(run_dir: Path, errors: list[str]) -> list[dict]:
    """验证数值审核的覆盖率、枚举值，以及候选数值是否属于当前检查。"""

    batch_path = run_dir / "batches" / "numeric.json"
    if not batch_path.exists():
        errors.append(f"缺少数值审核批次：{batch_path}")
        return []
    batch = read_json(batch_path).get("checks", [])
    batch_map = {item["check_id"]: item for item in batch}
    candidate_ids = {
        check_id: {candidate["number_id"] for candidate in item.get("candidates", [])}
        for check_id, item in batch_map.items()
    }
    reviews = _load_reviews(run_dir / "reviews" / "numeric-reviews.json", "数值", errors)
    seen = Counter(item.get("check_id") for item in reviews)

    for check_id in batch_map:
        if seen[check_id] != 1:
            errors.append(f"数值检查{check_id}必须且只能有一条审核结果。")

    for review in reviews:
        check_id = review.get("check_id")
        if check_id not in batch_map:
            errors.append(f"数值审核引用未知check_id：{check_id}")
            continue
        verdict = review.get("verdict")
        if verdict not in NUMBER_VERDICTS:
            errors.append(f"数值检查{check_id}使用了无效verdict：{verdict}")
        if review.get("confidence") not in CONFIDENCE_VALUES:
            errors.append(f"数值检查{check_id}缺少有效confidence。")
        if not isinstance(review.get("needs_human_review"), bool):
            errors.append(f"数值检查{check_id}的needs_human_review必须是布尔值。")
        if not isinstance(review.get("reason"), str) or not review["reason"].strip():
            errors.append(f"数值检查{check_id}缺少判断理由。")

        candidate = review.get("candidate_number_id")
        if candidate is not None:
            allowed = candidate_ids.get(check_id, set())
            if not isinstance(candidate, str) or candidate not in allowed:
                errors.append(
                    f"数值检查{check_id}的candidate_number_id不属于当前检查返回的候选列表：{candidate}"
                )
            elif verdict in CANDIDATE_FORBIDDEN:
                errors.append(f"数值检查{check_id}判定为{verdict}时不得提供候选数值。")
        elif verdict in CANDIDATE_REQUIRED:
            errors.append(f"数值检查{check_id}判定为{verdict}时必须提供candidate_number_id。")
    return reviews


def _paragraph_index(reference: dict | None, cache: dict[int, dict[str, dict]]) -> dict[str, dict]:
    """按paragraph_id索引一篇参考文献的段落，避免重复读盘。"""

    if not reference or not reference.get("text_path"):
        return {}
    reference_id = reference["reference_id"]
    if reference_id not in cache:
        parsed = read_json(Path(reference["text_path"]))
        index: dict[str, dict] = {}
        for page in parsed.get("pages", []):
            for paragraph in page.get("paragraphs", []):
                index[paragraph["paragraph_id"]] = paragraph
        cache[reference_id] = index
    return cache[reference_id]


def _validate_citations(
    run_dir: Path, references: list[dict], errors: list[str]
) -> list[dict]:
    """验证引用审核的覆盖率、正文原文定位与段落级证据回溯。"""

    batch_path = run_dir / "batches" / "citation.json"
    if not batch_path.exists():
        errors.append(f"缺少引用审核批次：{batch_path}")
        return []
    batch = read_json(batch_path).get("checks", [])
    batch_map = {item["batch_id"]: item for item in batch}
    reference_map = {item["reference_id"]: item for item in references}
    reviews = _load_reviews(run_dir / "reviews" / "citation-reviews.json", "引用", errors)
    seen = Counter(item.get("batch_id") for item in reviews)

    for batch_id in batch_map:
        if seen[batch_id] < 1:
            errors.append(f"引用检查{batch_id}至少需要一条原子主张审核结果。")

    claim_ids = Counter(item.get("claim_id") for item in reviews)
    for claim_id, count in claim_ids.items():
        if not claim_id or count != 1:
            errors.append(f"claim_id必须非空且唯一：{claim_id}")

    index_cache: dict[int, dict[str, dict]] = {}
    for review in reviews:
        batch_id = review.get("batch_id")
        batch_item = batch_map.get(batch_id)
        if not batch_item:
            errors.append(f"引用审核引用未知batch_id：{batch_id}")
            continue
        reference_id = review.get("reference_id")
        if reference_id != batch_item["reference_id"]:
            errors.append(f"引用检查{batch_id}的reference_id与审核批次不一致。")
        verdict = review.get("verdict")
        if verdict not in CITATION_VERDICTS:
            errors.append(f"引用检查{batch_id}使用了无效verdict：{verdict}")
        if review.get("confidence") not in CONFIDENCE_VALUES:
            errors.append(f"引用检查{batch_id}缺少有效confidence。")
        if not isinstance(review.get("needs_human_review"), bool):
            errors.append(f"引用检查{batch_id}的needs_human_review必须是布尔值。")
        if not isinstance(review.get("claim_text"), str) or not review["claim_text"].strip():
            errors.append(f"引用检查{batch_id}缺少原子主张。")
        if not isinstance(review.get("reason"), str) or not review["reason"].strip():
            errors.append(f"引用检查{batch_id}缺少判断理由。")

        source_quote = review.get("source_quote")
        if not isinstance(source_quote, str) or not source_quote.strip():
            errors.append(f"引用检查{batch_id}缺少正文原文source_quote。")
        elif not normalized_contains(batch_item.get("source_text", ""), source_quote):
            errors.append(
                f"引用检查{batch_id}的source_quote无法在对应正文块中逐字定位。"
            )

        reference = reference_map.get(reference_id)
        availability = (reference or {}).get("match_status") or batch_item.get("availability")
        if verdict == "parse_failed" and availability != "parse_failed":
            errors.append(f"引用检查{batch_id}在全文可解析时不得使用parse_failed。")
        elif verdict == "evidence_not_found" and availability != "matched":
            errors.append(
                f"引用检查{batch_id}在参考文献{reference_id}没有成功解析全文时"
                "不得使用evidence_not_found，应使用full_text_unavailable或parse_failed。"
            )
        elif verdict not in {"parse_failed", "evidence_not_found", "full_text_unavailable"}:
            if availability != "matched":
                errors.append(
                    f"引用检查{batch_id}的参考文献{reference_id}没有可用全文"
                    f"（{availability}），不得输出支持性判断。"
                )

        evidence = review.get("evidence", [])
        if evidence is None:
            evidence = []
        if not isinstance(evidence, list) or len(evidence) > MAX_EVIDENCE_ITEMS:
            errors.append(
                f"引用检查{batch_id}的evidence必须是最多{MAX_EVIDENCE_ITEMS}项的数组。"
            )
            continue
        if verdict in EVIDENCE_REQUIRED and not evidence:
            errors.append(f"引用检查{batch_id}的{verdict}判断必须附证据原文。")
        if verdict in EVIDENCE_FORBIDDEN and evidence:
            errors.append(f"引用检查{batch_id}的{verdict}判断不得附带证据原文。")

        paragraphs = _paragraph_index(reference, index_cache)
        for item in evidence:
            if not isinstance(item, dict):
                errors.append(f"引用检查{batch_id}的evidence项必须是对象。")
                continue
            paragraph_id = item.get("paragraph_id")
            page_number = item.get("page")
            quote = item.get("quote", "")
            paragraph = paragraphs.get(paragraph_id) if isinstance(paragraph_id, str) else None
            if paragraph is None:
                errors.append(
                    f"引用检查{batch_id}的证据paragraph_id不属于参考文献{reference_id}"
                    f"的解析结果：{paragraph_id}"
                )
                continue
            if not isinstance(page_number, int) or page_number != paragraph["page"]:
                errors.append(
                    f"引用检查{batch_id}的证据页码与段落{paragraph_id}不一致："
                    f"{page_number} != {paragraph['page']}"
                )
            if not isinstance(quote, str) or not quote.strip():
                errors.append(f"引用检查{batch_id}的证据缺少原文quote。")
            elif not normalized_contains(paragraph.get("text", ""), quote):
                errors.append(
                    f"引用检查{batch_id}的证据原文无法在段落{paragraph_id}内定位"
                    "（不能只出现在同一页的其他段落）。"
                )
    return reviews


def validate_run(run_dir: Path) -> list[str]:
    """验证整次运行；成功时写入已启用模块的正式结构化结果。"""

    errors: list[str] = []
    manifest, manifest_errors = load_manifest(run_dir)
    if manifest is None:
        write_json(run_dir / "validation-errors.json", {"errors": manifest_errors})
        return manifest_errors

    enabled = list(manifest["enabled_checks"])
    document_path = run_dir / "document.json"
    required = [document_path]
    if "numbers" in enabled:
        required.append(run_dir / "batches" / "numeric.json")
    if "citations" in enabled:
        required.append(run_dir / "batches" / "citation.json")
        required.append(run_dir / "references.json")
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        errors.extend(f"缺少准备阶段文件：{path}" for path in missing)
        write_json(run_dir / "validation-errors.json", {"errors": errors})
        return errors

    references: list[dict] = []
    if "citations" in enabled:
        references = read_json(run_dir / "references.json").get("references", [])
    errors.extend(verify_hashes(manifest, references))

    numeric_reviews: list[dict] = []
    citation_reviews: list[dict] = []
    if "numbers" in enabled:
        numeric_reviews = _validate_numeric(run_dir, errors)
    if "citations" in enabled:
        citation_reviews = _validate_citations(run_dir, references, errors)

    error_path = run_dir / "validation-errors.json"
    if errors:
        write_json(error_path, {"errors": errors})
        return errors
    if error_path.exists():
        error_path.unlink()
    if "numbers" in enabled:
        write_json(run_dir / "result-trace.json", {"reviews": numeric_reviews})
    if "citations" in enabled:
        write_json(run_dir / "citation-evidence.json", {"reviews": citation_reviews})
    return []

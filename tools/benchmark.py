"""冻结基准的实验定义、标准审核答案与评分逻辑。

使用方式：
1. 先用 tools/generate_demo.py 生成 examples/quick-demo 并冻结 eval/ground-truth.json。
2. 任何一次模型运行结束后，用 tools/score_run.py 对运行目录打分。

约束：标准答案由Demo的结构与预埋设计决定，与模型输出无关；
任何情况下都不得根据模型输出修改标准答案。
"""

from __future__ import annotations

import json
from pathlib import Path

from paper_proof_checker.io_utils import read_json


NUMBER_HIGH_RISK_VERDICTS = {"conflict", "source_not_found", "manual_figure_check"}
CITATION_HIGH_RISK_VERDICTS = {
    "conflict",
    "partial_support",
    "evidence_not_found",
    "full_text_unavailable",
    "parse_failed",
}

# 9项数值场景。anchor_raw为Demo中该数值的原始写法，用于在批处理结果里定位检查项。
NUMBER_SCENARIOS: list[dict] = [
    {
        "scenario": "非研究结果数值（软件版本）",
        "anchor_raw": "4.2",
        "expected_verdict": "not_a_result",
        "candidate": None,
        "high_risk": False,
    },
    {
        "scenario": "完全匹配",
        "anchor_raw": "32.6%",
        "expected_verdict": "exact_match",
        "candidate": {"relation": "exact_match", "raw": "32.6%", "document": "manuscript"},
        "high_risk": False,
    },
    {
        "scenario": "四舍五入兼容",
        "anchor_raw": "0.72",
        "expected_verdict": "rounded_match",
        "candidate": {"relation": "rounded_match", "raw": "0.7234"},
        "high_risk": False,
    },
    {
        "scenario": "百分比与小数换算",
        "anchor_raw": "0.458",
        "expected_verdict": "converted_match",
        "candidate": {"relation": "converted_match", "raw": "45.8%"},
        "high_risk": False,
    },
    {
        "scenario": "P值阈值兼容",
        "anchor_raw": "P<0.05",
        "expected_verdict": "threshold_compatible",
        "candidate": {"relation": "threshold_compatible", "raw": "0.032"},
        "high_risk": False,
    },
    {
        "scenario": "数值冲突",
        "anchor_raw": "41.2%",
        "expected_verdict": "conflict",
        "candidate": {
            "relation": "potential_conflict",
            "raw": "38.9%",
            "source_contains": "Usual care",
        },
        "high_risk": True,
    },
    {
        "scenario": "数值无来源",
        "anchor_raw": "6.3",
        "expected_verdict": "source_not_found",
        "candidate": None,
        "high_risk": True,
    },
    {
        "scenario": "补充材料提供来源",
        "anchor_raw": "88.4%",
        "expected_verdict": "exact_match",
        "candidate": {"relation": "exact_match", "raw": "88.4%", "document": "supplement"},
        "high_risk": False,
    },
    {
        "scenario": "图片人工检查",
        "anchor_raw": "68.4%",
        "expected_verdict": "manual_figure_check",
        "candidate": None,
        "high_risk": True,
    },
]

# 5项引用场景。claim_text同时作为source_quote（去掉句末句点后的子串一定出现在正文块中）。
CITATION_SCENARIOS: list[dict] = [
    {
        "scenario": "引用直接支撑",
        "reference_id": 1,
        "claim_text": "Treatment reduced all-cause mortality at one year in the treated group.",
        "expected_verdict": "direct_support",
        "evidence_quote": "The intervention reduced all-cause mortality at one year in the treated group.",
        "high_risk": False,
    },
    {
        "scenario": "引用部分支撑",
        "reference_id": 2,
        "claim_text": "The intervention improved survival in every prespecified subgroup.",
        "expected_verdict": "partial_support",
        "evidence_quote": "In the subgroup of patients with diabetes, the intervention improved survival at one year.",
        "high_risk": True,
    },
    {
        "scenario": "引用结论冲突",
        "reference_id": 3,
        "claim_text": "The intervention reduced mortality compared with usual care.",
        "expected_verdict": "conflict",
        "evidence_quote": "The intervention did not reduce mortality compared with usual care at one year.",
        "high_risk": True,
    },
    {
        "scenario": "已有全文但未找到证据",
        "reference_id": 4,
        "claim_text": "The intervention reduced hospital admissions at one year.",
        "expected_verdict": "evidence_not_found",
        "evidence_quote": None,
        "high_risk": True,
    },
    {
        "scenario": "参考文献全文缺失",
        "reference_id": 5,
        "claim_text": "The intervention reduced mortality in patients with severe disease.",
        "expected_verdict": "full_text_unavailable",
        "evidence_quote": None,
        "high_risk": True,
    },
]

HIGH_RISK_TOTAL = sum(1 for item in NUMBER_SCENARIOS if item["high_risk"]) + sum(
    1 for item in CITATION_SCENARIOS if item["high_risk"]
)
SCENARIO_TOTAL = len(NUMBER_SCENARIOS) + len(CITATION_SCENARIOS)


def _find_paragraph(text_path: str, quote: str) -> dict:
    """在参考文献解析结果中定位包含指定原文的段落。"""

    parsed = read_json(Path(text_path))
    for page in parsed.get("pages", []):
        for paragraph in page.get("paragraphs", []):
            if quote.lower() in paragraph["text"].lower():
                return paragraph
    raise AssertionError(f"标准答案引文未出现在参考文献全文中：{quote}")


def _pick_candidate(check: dict, rule: dict | None, block_map: dict) -> str | None:
    """按场景规则在候选列表里定位唯一候选数值ID。"""

    if rule is None:
        return None
    matches = []
    for candidate in check.get("candidates", []):
        if rule.get("relation") and candidate.get("relation") != rule["relation"]:
            continue
        if rule.get("raw") and candidate.get("raw") != rule["raw"]:
            continue
        if rule.get("source_contains") and rule["source_contains"] not in candidate.get(
            "source_text", ""
        ):
            continue
        if rule.get("document"):
            block = block_map.get(candidate.get("block_id"), {})
            if block.get("document") != rule["document"]:
                continue
        matches.append(candidate["number_id"])
    if len(matches) != 1:
        raise AssertionError(
            f"场景规则未能唯一定位候选数值：{rule} -> {matches}"
        )
    return matches[0]


def resolve_ground_truth(
    run_dir: Path, kinds: tuple[str, ...] = ("number", "citation")
) -> dict:
    """从Demo的确定性解析结果生成标准答案；不读取任何模型输出。

    kinds 用于只启用了部分模块的运行目录（例如 --checks numbers）。
    """

    document = read_json(run_dir / "document.json")
    block_map = {block["block_id"]: block for block in document["blocks"]}
    checks: list[dict] = []

    if "number" in kinds:
        numeric_batch = read_json(run_dir / "batches" / "numeric.json")["checks"]
        for scenario in NUMBER_SCENARIOS:
            matched = [
                item for item in numeric_batch if item["number"]["raw"] == scenario["anchor_raw"]
            ]
            if len(matched) != 1:
                raise AssertionError(
                    f"场景[{scenario['scenario']}]在数值批次中命中{len(matched)}项："
                    f"{scenario['anchor_raw']}"
                )
            check = matched[0]
            checks.append(
                {
                    "kind": "number",
                    "scenario": scenario["scenario"],
                    "check_id": check["check_id"],
                    "expected_verdict": scenario["expected_verdict"],
                    "expected_candidate_number_id": _pick_candidate(
                        check, scenario["candidate"], block_map
                    ),
                    "high_risk": scenario["high_risk"],
                }
            )

    mapping_checks: list[dict] = []
    if "citation" in kinds:
        citation_batch = read_json(run_dir / "batches" / "citation.json")["checks"]
        references = read_json(run_dir / "references.json")["references"]
        reference_map = {item["reference_id"]: item for item in references}
        for scenario in CITATION_SCENARIOS:
            matched = [
                item for item in citation_batch if item["reference_id"] == scenario["reference_id"]
            ]
            if len(matched) != 1:
                raise AssertionError(
                    f"场景[{scenario['scenario']}]在引用批次中命中{len(matched)}项："
                    f"reference_id={scenario['reference_id']}"
                )
            batch_item = matched[0]
            reference = reference_map[scenario["reference_id"]]
            paragraph = (
                _find_paragraph(reference["text_path"], scenario["evidence_quote"])
                if scenario["evidence_quote"]
                else None
            )
            checks.append(
                {
                    "kind": "citation",
                    "scenario": scenario["scenario"],
                    "batch_id": batch_item["batch_id"],
                    "reference_id": scenario["reference_id"],
                    "expected_verdict": scenario["expected_verdict"],
                    # 引用检查不产生候选数值ID；显式置None以保持与数值条目键集一致。
                    "expected_candidate_number_id": None,
                    "expected_evidence": (
                        {
                            "paragraph_id": paragraph["paragraph_id"],
                            "page": paragraph["page"],
                            "quote": scenario["evidence_quote"],
                        }
                        if paragraph
                        else None
                    ),
                    "high_risk": scenario["high_risk"],
                }
            )
        mapping_checks = [
            {
                "scenario": "PDF映射及页码回溯",
                "reference_id": 3,
                "expected_match_status": "matched",
                "expected_match_method": "manual_map",
                "note": "Brown_2021.pdf不写DOI且元数据标题不同，只能由reference-map.json建立唯一对应。",
            },
            {
                "scenario": "PDF映射及页码回溯",
                "reference_id": 1,
                "expected_match_status": "matched",
                "expected_match_method": "manual_map",
                "note": "手工映射优先于自动匹配。",
            },
            {
                "scenario": "PDF映射及页码回溯",
                "reference_id": 5,
                "expected_match_status": "missing_pdf",
                "expected_match_method": None,
                "note": "故意缺失的参考文献，必须被如实标记为缺少全文。",
            },
        ]

    return {
        "benchmark": "paper-proof-checker examples/quick-demo",
        "rules_version": 2,
        "kinds": list(kinds),
        "scenario_total": sum(
            len(NUMBER_SCENARIOS) if kind == "number" else len(CITATION_SCENARIOS)
            for kind in kinds
        ),
        "high_risk_total": sum(
            (sum(1 for item in NUMBER_SCENARIOS if item["high_risk"]) if kind == "number" else 0)
            + (sum(1 for item in CITATION_SCENARIOS if item["high_risk"]) if kind == "citation" else 0)
            for kind in kinds
        ),
        "checks": checks,
        "mapping_checks": mapping_checks,
    }


def build_expected_reviews(run_dir: Path, ground_truth: dict) -> tuple[dict, dict]:
    """由标准答案生成可验证的参考审核JSON。"""

    kinds = {item["kind"] for item in ground_truth["checks"]}
    numeric_batch = (
        {
            item["check_id"]: item
            for item in read_json(run_dir / "batches" / "numeric.json")["checks"]
        }
        if "number" in kinds
        else {}
    )
    citation_batch = (
        {
            item["batch_id"]: item
            for item in read_json(run_dir / "batches" / "citation.json")["checks"]
        }
        if "citation" in kinds
        else {}
    )
    numeric_reviews = []
    citation_reviews = []
    for item in ground_truth["checks"]:
        if item["kind"] == "number":
            numeric_reviews.append(
                {
                    "check_id": item["check_id"],
                    "verdict": item["expected_verdict"],
                    "candidate_number_id": item["expected_candidate_number_id"],
                    "reason": f"（标准答案）{item['scenario']}。",
                    "confidence": "high",
                    "needs_human_review": item["high_risk"],
                }
            )
        else:
            claim_text = next(
                scenario["claim_text"]
                for scenario in CITATION_SCENARIOS
                if scenario["scenario"] == item["scenario"]
            )
            evidence = []
            if item["expected_evidence"]:
                evidence.append(
                    {
                        "paragraph_id": item["expected_evidence"]["paragraph_id"],
                        "page": item["expected_evidence"]["page"],
                        "section": "",
                        "quote": item["expected_evidence"]["quote"],
                    }
                )
            citation_reviews.append(
                {
                    "batch_id": item["batch_id"],
                    "claim_id": f"{item['batch_id']}-a",
                    "source_quote": claim_text.rstrip("."),
                    "claim_text": claim_text,
                    "reference_id": item["reference_id"],
                    "verdict": item["expected_verdict"],
                    "evidence": evidence,
                    "reason": f"（标准答案）{item['scenario']}。",
                    "confidence": "high",
                    "needs_human_review": item["high_risk"],
                }
            )
    return {"reviews": numeric_reviews}, {"reviews": citation_reviews}


def _score_unit(
    kind: str,
    expected_verdict: str,
    expected_candidate: str | None,
    produced_verdict: str | None,
    produced_candidate: str | None,
) -> dict:
    """给一个被判断单元打分：严格与宽松两种口径。"""

    strict = produced_verdict == expected_verdict
    if expected_candidate is not None:
        strict = strict and produced_candidate == expected_candidate
    loose = produced_verdict == expected_verdict
    return {
        "expected_verdict": expected_verdict,
        "produced_verdict": produced_verdict,
        "expected_candidate_number_id": expected_candidate,
        "produced_candidate_number_id": produced_candidate,
        "strict_correct": strict,
        "loose_correct": loose,
        "verdict_correct": loose,
    }


def _is_false_positive(kind: str, produced_verdict: str | None, expected_verdict: str) -> bool:
    """生产出的高风险判断，但标准答案认为该项不属于高风险。"""

    if produced_verdict is None or produced_verdict == expected_verdict:
        return False
    high_risk_verdicts = (
        NUMBER_HIGH_RISK_VERDICTS if kind == "number" else CITATION_HIGH_RISK_VERDICTS
    )
    if produced_verdict not in high_risk_verdicts:
        return False
    return expected_verdict not in high_risk_verdicts


def _score_number(item: dict, produced: dict | None) -> dict:
    return _score_unit(
        "number",
        item["expected_verdict"],
        item["expected_candidate_number_id"],
        produced.get("verdict") if produced else None,
        produced.get("candidate_number_id") if produced else None,
    )


def _score_citation(item: dict, group: list[dict]) -> dict:
    """同一个batch可能被拆成多条原子主张：任一条给出期望判断即视为命中。"""

    verdicts = [entry.get("verdict") for entry in group]
    matched = [entry for entry in group if entry.get("verdict") == item["expected_verdict"]]
    chosen = matched[0] if matched else (group[0] if group else None)
    expected_evidence = item.get("expected_evidence")
    evidence_ok = None
    if expected_evidence is not None:
        evidence_ok = bool(matched) and any(
            evidence.get("paragraph_id") == expected_evidence["paragraph_id"]
            and evidence.get("page") == expected_evidence["page"]
            for evidence in chosen.get("evidence", [])
        )
    return {
        "expected_verdict": item["expected_verdict"],
        "produced_verdict": chosen.get("verdict") if chosen else None,
        "produced_verdicts": verdicts,
        "expected_candidate_number_id": None,
        "produced_candidate_number_id": None,
        "expected_evidence": expected_evidence,
        "evidence_paragraph_correct": evidence_ok,
        "strict_correct": bool(matched) and (evidence_ok is not False),
        "loose_correct": bool(matched),
        "verdict_correct": bool(matched),
    }


def score_run(run_dir: Path, ground_truth: dict) -> dict:
    """按计划文档的指标对一次运行打分。"""

    produced_numbers = {}
    if (run_dir / "result-trace.json").exists():
        produced_numbers = {
            item["check_id"]: item for item in read_json(run_dir / "result-trace.json")["reviews"]
        }
    produced_citations: dict[str, list[dict]] = {}
    if (run_dir / "citation-evidence.json").exists():
        for item in read_json(run_dir / "citation-evidence.json")["reviews"]:
            produced_citations.setdefault(item["batch_id"], []).append(item)

    details: list[dict] = []
    missing: list[str] = []
    high_risk_missed: list[str] = []
    false_positives: list[str] = []
    high_risk_found = 0

    for item in ground_truth["checks"]:
        if item["kind"] == "number":
            produced = produced_numbers.get(item["check_id"])
            scored = _score_number(item, produced)
            identifier = item["check_id"]
        else:
            group = produced_citations.get(item["batch_id"], [])
            scored = _score_citation(item, group)
            identifier = item["batch_id"]
        if scored["produced_verdict"] is None:
            missing.append(identifier)
        scored.update({"scenario": item["scenario"], "kind": item["kind"], "high_risk": item["high_risk"]})
        if item["high_risk"]:
            if scored["loose_correct"]:
                high_risk_found += 1
            else:
                high_risk_missed.append(
                    f"{item['scenario']}（期望{item['expected_verdict']}，"
                    f"实际{scored['produced_verdict']}）"
                )
        elif _is_false_positive(item["kind"], scored["produced_verdict"], item["expected_verdict"]):
            false_positives.append(
                f"{item['scenario']}（期望{item['expected_verdict']}，"
                f"实际{scored['produced_verdict']}）"
            )
        details.append(scored)

    produced_total = len(produced_numbers) + sum(
        len(value) for value in produced_citations.values()
    )
    return {
        "scenario_total": ground_truth["scenario_total"],
        "high_risk_total": ground_truth["high_risk_total"],
        "verdict_correct": sum(1 for item in details if item["loose_correct"]),
        "verdict_accuracy": round(
            sum(1 for item in details if item["loose_correct"]) / ground_truth["scenario_total"], 4
        ),
        "strict_correct": sum(1 for item in details if item["strict_correct"]),
        "strict_accuracy": round(
            sum(1 for item in details if item["strict_correct"]) / ground_truth["scenario_total"], 4
        ),
        "evidence_paragraph_correct": sum(
            1 for item in details if item.get("evidence_paragraph_correct") is True
        ),
        "high_risk_found": high_risk_found,
        "high_risk_recall": round(high_risk_found / ground_truth["high_risk_total"], 4),
        "high_risk_missed": high_risk_missed,
        "high_risk_false_positives": len(false_positives),
        "high_risk_false_positive_items": false_positives,
        "produced_total": produced_total,
        "missing_items": missing,
        "details": details,
    }


def dump_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


"""数值提取、标准化与候选关系。"""

from __future__ import annotations

import unittest

from paper_proof_checker.number_extractor import build_number_batch, compatibility, extract_numbers


def _block(text: str, block_id: str = "main-p-1", kind: str = "paragraph", **extra) -> dict:
    return {
        "block_id": block_id,
        "document": "manuscript",
        "section": "Results",
        "kind": kind,
        "text": text,
        "location": {"paragraph_index": 1},
        **extra,
    }


class NumberExtractorTest(unittest.TestCase):
    def test_percentage_and_decimal_conversion(self) -> None:
        percent = {"type": "percentage", "value": 0.326, "precision": 3, "comparator": "="}
        fraction = {"type": "number", "value": 0.326, "precision": 3, "comparator": "="}
        self.assertEqual(compatibility(percent, fraction), "converted_match")

    def test_p_value_threshold_compatibility(self) -> None:
        threshold = {"type": "p_value", "value": 0.05, "precision": 2, "comparator": "<"}
        exact = {"type": "p_value", "value": 0.032, "precision": 3, "comparator": "="}
        too_large = {"type": "p_value", "value": 0.051, "precision": 3, "comparator": "="}
        self.assertEqual(compatibility(threshold, exact), "threshold_compatible")
        self.assertIsNone(compatibility(threshold, too_large))

    def test_rounding_requires_meaningful_precision(self) -> None:
        """回归：精度为整数时，任何小数都会四舍五入到0或1，不得判为匹配。"""

        label = {"type": "number", "value": 1.0, "precision": 0, "comparator": "="}
        rounded = {"type": "number", "value": 0.72, "precision": 2, "comparator": "="}
        self.assertIsNone(compatibility(rounded, label))
        fine = {"type": "number", "value": 0.7234, "precision": 4, "comparator": "="}
        self.assertEqual(compatibility(rounded, fine), "rounded_match")

    def test_decimal_at_sentence_end_is_extracted(self) -> None:
        r"""回归：句末小数曾经被 (?![\w.]) 漏掉。"""

        records = extract_numbers(_block("The hazard ratio was 0.72."))
        self.assertEqual([record["raw"] for record in records], ["0.72"])
        self.assertEqual(records[0]["value"], 0.72)

    def test_version_chain_is_not_split_into_extra_numbers(self) -> None:
        records = extract_numbers(_block("We used package 1.2.3 for all analyses."))
        self.assertEqual([record["raw"] for record in records], [])

    def test_table_and_figure_labels_are_not_numbers(self) -> None:
        self.assertEqual(extract_numbers(_block("Figure 2 shows the forest plot.")), [])
        self.assertEqual(extract_numbers(_block("Table 1. Main outcomes", kind="table_caption")), [])
        self.assertEqual(
            [record["raw"] for record in extract_numbers(_block("The rate was 5.4 in 2021."))],
            ["5.4"],
        )

    def test_column_header_infers_p_value_type(self) -> None:
        records = extract_numbers(
            _block("0.032", block_id="main-t-1", kind="table_cell", column_header="P value")
        )
        self.assertEqual(records[0]["type"], "p_value")

    def test_different_value_with_same_context_is_a_conflict_candidate(self) -> None:
        blocks = [
            _block("Mortality was 32.6%."),
            _block(
                "31.6%",
                block_id="main-t-1-r-2-c-2",
                kind="table_cell",
                context_text="Mortality | 31.6%",
                location={"table_index": 1, "row": 1, "column": 2},
            ),
        ]
        batch = build_number_batch(blocks)
        self.assertEqual(batch[0]["candidates"][0]["relation"], "potential_conflict")

    def test_candidates_expose_number_id_for_traceability(self) -> None:
        blocks = [
            _block("Mortality was 32.6%."),
            _block(
                "32.6%",
                block_id="main-t-1-r-2-c-2",
                kind="table_cell",
                context_text="Mortality | 32.6%",
                location={"table_index": 1, "row": 1, "column": 2},
            ),
        ]
        batch = build_number_batch(blocks)
        candidate = batch[0]["candidates"][0]
        self.assertTrue(candidate["number_id"].startswith("num-"))
        self.assertEqual(candidate["relation"], "exact_match")

    def test_reference_section_numbers_are_skipped(self) -> None:
        blocks = [_block("1. Smith J. Journal of Trials. 2022. doi:10.1234/x")]
        blocks[0]["section"] = "References"
        self.assertEqual(build_number_batch(blocks), [])


if __name__ == "__main__":
    unittest.main()

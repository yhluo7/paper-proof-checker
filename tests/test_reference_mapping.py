"""参考文献与PDF映射：递归发现、手工映射优先、拒绝规则与哈希复查。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paper_proof_checker.io_utils import read_json
from paper_proof_checker.reference_mapper import discover_pdfs, load_reference_map
from paper_proof_checker.validator import validate_run
from tests.helpers import build_project, prepare, write_standard_reviews


class ReferenceMappingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        build_project(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_recursive_discovery_finds_nested_and_ignores_case(self) -> None:
        (self.root / "references" / "archive" / "Extra.PDF").write_bytes(b"not a real pdf")
        found = discover_pdfs(self.root / "references")
        names = sorted(path.name for path in found)
        self.assertIn("Jones_2023.pdf", names)
        self.assertIn("Chen_2020.pdf", names)
        self.assertIn("Extra.PDF", names)
        self.assertEqual(len(found), 5)

    def test_manual_map_takes_priority_and_is_recorded(self) -> None:
        run_dir = prepare(self.root)
        references = {item["reference_id"]: item for item in read_json(run_dir / "references.json")["references"]}
        for reference_id in (1, 2, 3, 4):
            self.assertEqual(references[reference_id]["match_status"], "matched")
            self.assertEqual(references[reference_id]["match_method"], "manual_map")
            self.assertTrue(references[reference_id]["sha256"])
        self.assertEqual(references[3]["relative_path"], "Brown_2021.pdf")
        self.assertEqual(references[2]["relative_path"], "archive/Jones_2023.pdf")
        manifest = read_json(run_dir / "manifest.json")
        self.assertEqual(manifest["reference_map"]["entries"]["3"], "Brown_2021.pdf")
        self.assertTrue((run_dir / "reference-mapping.md").exists())

    def test_without_manual_map_the_mismatched_pdf_stays_unmatched(self) -> None:
        """Brown_2021.pdf没有DOI且元数据标题不同，自动匹配不应擅自认领。"""

        run_dir = prepare(self.root, reference_map=None)
        references = {item["reference_id"]: item for item in read_json(run_dir / "references.json")["references"]}
        self.assertEqual(references[3]["match_status"], "missing_pdf")
        self.assertIsNone(references[3]["pdf_path"])
        # 有DOI的条目仍然可以自动匹配成功。
        self.assertEqual(references[1]["match_status"], "matched")
        self.assertEqual(references[1]["match_method"], "doi")

    def test_missing_reference_pdf_is_reported_not_invented(self) -> None:
        run_dir = prepare(self.root)
        references = {item["reference_id"]: item for item in read_json(run_dir / "references.json")["references"]}
        self.assertEqual(references[5]["match_status"], "missing_pdf")
        self.assertIsNone(references[5]["sha256"])

    def test_map_rejects_missing_non_pdf_duplicate_and_escaping_paths(self) -> None:
        reference_dir = self.root / "references"
        cases = {
            "missing": {"1": "NoSuchFile.pdf"},
            "not_pdf": {"1": "Smith_2022.txt"},
            "escaping": {"1": "../outside.pdf"},
            "duplicate": {"1": "Smith_2022.pdf", "2": "Smith_2022.pdf"},
            "bad_id": {"one": "Smith_2022.pdf"},
            "not_object": ["Smith_2022.pdf"],
        }
        (self.root / "outside.pdf").write_bytes(b"%PDF-1.4\n")
        for name, payload in cases.items():
            path = self.root / f"map-{name}.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError, msg=name):
                load_reference_map(path, reference_dir)

    def test_map_rejects_invalid_json_and_missing_file(self) -> None:
        bad = self.root / "broken.json"
        bad.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_reference_map(bad, self.root / "references")
        with self.assertRaises(ValueError):
            load_reference_map(self.root / "absent.json", self.root / "references")

    def test_reference_map_accepts_nested_english_paths(self) -> None:
        path = self.root / "map-ok.json"
        path.write_text(
            json.dumps({"1": "Smith_2022.pdf", "2": "archive/Jones_2023.pdf"}), encoding="utf-8"
        )
        mapping = load_reference_map(path, self.root / "references")
        self.assertEqual(sorted(mapping), [1, 2])
        self.assertEqual(mapping[2].name, "Jones_2023.pdf")

    def test_modified_reference_pdf_blocks_validation(self) -> None:
        run_dir = prepare(self.root)
        write_standard_reviews(run_dir)
        target = self.root / "references" / "Smith_2022.pdf"
        target.write_bytes(target.read_bytes() + b"% trailing change")
        errors = validate_run(run_dir)
        self.assertTrue(any("在prepare之后被修改" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

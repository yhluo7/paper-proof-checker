"""PDF解析：正常、多页、损坏、加密、无文本层与回退。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PageObject

from paper_proof_checker.pdf_parser import MAX_PARAGRAPH_CHARS, parse_pdf
from tools.synth_pdf import build_blank_pdf, build_corrupt_pdf, build_text_pdf


class PdfParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _sample(self, name: str = "sample.pdf", **kwargs) -> Path:
        return build_text_pdf(
            self.root / name,
            [
                "Effects of the intervention on one-year mortality",
                "doi:10.1234/demo.1",
                "Results",
                "The intervention reduced all-cause mortality at one year.",
            ],
            **kwargs,
        )

    def test_normal_pdf_is_parsed_with_sections_and_doi(self) -> None:
        parsed = parse_pdf(self._sample())
        self.assertEqual(parsed["status"], "parsed")
        self.assertEqual(parsed["metadata"]["doi"], "10.1234/demo.1")
        paragraphs = parsed["pages"][0]["paragraphs"]
        texts = [item["text"] for item in paragraphs]
        self.assertIn("The intervention reduced all-cause mortality at one year.", texts)
        # 标题行短且无句末标点，被推断为章节标题，后续段落继承该章节。
        self.assertEqual(
            paragraphs[1]["section"], "Effects of the intervention on one-year mortality"
        )
        # 遇到"Results"标题后，结果段落归入Results章节。
        self.assertEqual(paragraphs[-1]["section"], "Results")

    def test_paragraph_ids_are_stable_and_page_scoped(self) -> None:
        parsed = parse_pdf(self._sample())
        for page in parsed["pages"]:
            for index, paragraph in enumerate(page["paragraphs"], start=1):
                self.assertEqual(
                    paragraph["paragraph_id"], f"p{page['page']:04d}-b{index:03d}"
                )
                self.assertEqual(paragraph["page"], page["page"])

    def test_multi_page_pdf_keeps_real_page_numbers(self) -> None:
        paragraphs = [f"Paragraph {index} of the appendix with detailed results." for index in range(120)]
        path = build_text_pdf(self.root / "long.pdf", paragraphs)
        parsed = parse_pdf(path)
        self.assertEqual(parsed["status"], "parsed")
        self.assertGreater(parsed["metadata"]["page_count"], 1)
        pages = [page["page"] for page in parsed["pages"]]
        self.assertEqual(pages, list(range(1, len(pages) + 1)))
        self.assertEqual(parsed["pages"][-1]["paragraphs"][-1]["page"], len(pages))

    def test_corrupt_pdf_returns_parse_failed(self) -> None:
        parsed = parse_pdf(build_corrupt_pdf(self.root / "corrupt.pdf"))
        self.assertEqual(parsed["status"], "parse_failed")
        self.assertTrue(parsed["error"])

    def test_encrypted_pdf_returns_parse_failed(self) -> None:
        parsed = parse_pdf(self._sample("encrypted.pdf", password="secret"))
        self.assertEqual(parsed["status"], "parse_failed")
        self.assertEqual(parsed["error"], "PDF已加密")

    def test_pdf_without_text_layer_returns_parse_failed(self) -> None:
        parsed = parse_pdf(build_blank_pdf(self.root / "scanned.pdf"))
        self.assertEqual(parsed["status"], "parse_failed")
        self.assertIn("没有可提取文本", parsed["error"])

    def test_plain_mode_fallback_when_layout_extraction_fails(self) -> None:
        path = self._sample()
        original = PageObject.extract_text

        def flaky(self, *args, **kwargs):  # noqa: ANN001
            if "extraction_mode" in kwargs:
                raise RuntimeError("layout模式不可用")
            return original(self, *args, **kwargs)

        with patch.object(PageObject, "extract_text", flaky):
            parsed = parse_pdf(path)
        self.assertEqual(parsed["status"], "parsed")
        joined = " ".join(
            paragraph["text"]
            for page in parsed["pages"]
            for paragraph in page["paragraphs"]
        )
        self.assertIn("reduced all-cause mortality", joined)

    def test_long_paragraph_is_split_into_sentence_windows(self) -> None:
        sentence = "The intervention reduced mortality in the treated group. "
        paragraph = (sentence * 40).strip()
        self.assertGreater(len(paragraph), MAX_PARAGRAPH_CHARS)
        path = build_text_pdf(self.root / "dense.pdf", [paragraph])
        parsed = parse_pdf(path)
        self.assertEqual(parsed["status"], "parsed")
        texts = [item["text"] for item in parsed["pages"][0]["paragraphs"]]
        self.assertGreater(len(texts), 1)
        for text in texts:
            self.assertLessEqual(len(text), MAX_PARAGRAPH_CHARS + 1)


if __name__ == "__main__":
    unittest.main()

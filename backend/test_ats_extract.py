from __future__ import annotations

import unittest

import fitz

from ats.import_service import (
    _usable_extracted_text,
    extract_file_bytes_to_text,
)


def _digital_pdf_bytes() -> bytes:
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Kalpanarani Nalwade Software Engineer Python FastAPI")
    data = pdf.tobytes()
    pdf.close()
    return data


class AtsFileExtractTests(unittest.TestCase):
    def test_pdf_bytes_are_not_treated_as_utf8_text(self) -> None:
        pdf = _digital_pdf_bytes()
        decoded = pdf.decode("utf-8", errors="ignore")
        self.assertEqual(
            _usable_extracted_text(decoded, mime="application/pdf", filename="resume.pdf"),
            "",
        )

    def test_extracts_text_from_pdf_like_bulk_upload(self) -> None:
        text = extract_file_bytes_to_text(
            _digital_pdf_bytes(),
            filename="Kalpanarani_Nalwade.pdf",
            mime="application/octet-stream",
        )
        self.assertIn("Kalpanarani", text)
        self.assertGreaterEqual(len(text), 50)

    def test_plain_text_passthrough(self) -> None:
        raw = b"Candidate with more than fifty characters of resume text for the wizard."
        text = extract_file_bytes_to_text(raw, filename="cv.txt", mime="text/plain")
        self.assertIn("fifty characters", text)


if __name__ == "__main__":
    unittest.main()

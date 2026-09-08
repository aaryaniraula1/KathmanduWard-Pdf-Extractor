from pathlib import Path

import pymupdf


def open_pdf(pdf_path: Path):
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file: {pdf_path}")

    return pymupdf.open(pdf_path)
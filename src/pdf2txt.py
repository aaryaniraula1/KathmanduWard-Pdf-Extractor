from pathlib import Path

from lipi.converter.convert import Pdf2Txt
from lipi.converter.ocr import OcrPdf


PROJECT_DIR = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_DIR / "input" / "Bharatpur_Budget.pdf"
OUTPUT_DIR = PROJECT_DIR / "output" / "pdf2txt"
PAGE_NUMBER = 19


def main():
    if not INPUT_FILE.is_file():
        raise FileNotFoundError(f"PDF not found: {INPUT_FILE}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    direct_file = OUTPUT_DIR / "page19_direct.txt"
    ocr_file = OUTPUT_DIR / "page19_ocr_nepali.txt"

    Pdf2Txt(
        input_file=str(INPUT_FILE),
        output_file=str(direct_file),
        pages=str(PAGE_NUMBER),
    ).extract()

    ocr = OcrPdf(
        input_file=str(INPUT_FILE),
        output_file=str(ocr_file),
        pages=str(PAGE_NUMBER),
        lang="nep",
        sharpen_images=False,
    )
    ocr.extract(format="text")

    if not ocr_file.read_text(encoding="utf-8").strip():
        raise RuntimeError("OCR returned no text.")

    print(f"Direct text: {direct_file}")
    print(f"Nepali OCR: {ocr_file}")


if __name__ == "__main__":
    main()
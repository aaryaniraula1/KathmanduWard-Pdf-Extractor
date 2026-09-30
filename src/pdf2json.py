import csv
import json
import re
import shutil
from collections import Counter
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytesseract
from camelot.backends.pdfium_backend import PdfiumBackend
from lipi.converter.convert import Pdf2Json
from PIL import Image


PROJECT_DIR = Path(__file__).resolve().parent.parent
PDF_PATH = PROJECT_DIR / "input" / "Bharatpur_Budget.pdf"
OUTPUT_DIR = PROJECT_DIR / "output" / "pdf2json"

PAGE_NUMBER = 19
RENDER_SCALE = 4
EXPECTED_SERIALS = set(range(1, 18))
DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

COLUMNS = [
    "serial_no",
    "activity",
    "expenditure_code",
    "allocation",
    "internal_source",
    "nepal_government",
    "province_government",
    "public_participation",
    "development_goal_no",
]


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def extract_serial(text):
    match = re.match(r"^([०-९0-9]{1,3})(?:\s+|$)", clean_text(text))
    return int(match[1].translate(DIGITS)) if match else None


def render_pdf_safely(self, pdf_path, png_path, resolution=300):
    # Close the temporary PDF before Camelot attempts Windows cleanup.
    with pymupdf.open(pdf_path) as document:
        document[0].get_pixmap(
            dpi=resolution, alpha=False
        ).save(png_path)


def check_environment():
    if not PDF_PATH.is_file():
        raise FileNotFoundError(f"PDF not found: {PDF_PATH}")

    if version("camelot-py") != "1.0.9":
        raise RuntimeError(
            "This Lipi integration requires camelot-py==1.0.9."
        )

    if not shutil.which("tesseract"):
        windows_path = Path(
            r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        )
        if not windows_path.is_file():
            raise RuntimeError("Install Tesseract and add it to PATH.")

        pytesseract.pytesseract.tesseract_cmd = str(windows_path)

    if "nep" not in pytesseract.get_languages(config=""):
        raise RuntimeError(
            "Install nep.traineddata in Tesseract's tessdata folder."
        )


def read_table():
    raw_path = OUTPUT_DIR / "bharatpur_page19_lipi_raw.json"

    extractor = Pdf2Json(
        input_file=str(PDF_PATH),
        output_file=str(raw_path),
        options={
            "pages": str(PAGE_NUMBER),
            "type": "lattice",
        },
    )

    with patch.object(PdfiumBackend, "convert", render_pdf_safely):
        extractor.extract()

    tables = extractor.tables_data

    if len(tables) != 1:
        raise RuntimeError(f"Expected one table, found {len(tables)}.")

    table = tables[0]["table"]

    if table.df.shape[1] != len(COLUMNS):
        raise RuntimeError(
            f"Expected 9 columns, found {table.df.shape[1]}."
        )

    return table


def read_activity(page, image, cell):
    scale_x = image.width / page.rect.width
    scale_y = image.height / page.rect.height

    box = (
        max(0, int((cell.x1 - 2) * scale_x)),
        max(0, int((page.rect.height - cell.y2 - 2) * scale_y)),
        min(image.width, int((cell.x2 + 2) * scale_x)),
        min(image.height, int((page.rect.height - cell.y1 + 2) * scale_y)),
    )

    if box[2] <= box[0] or box[3] <= box[1]:
        raise RuntimeError("Invalid activity cell coordinates.")

    with image.crop(box) as cropped:
        text = pytesseract.image_to_string(
            cropped,
            lang="nep",
            config="--psm 6",
        )

    return re.sub(r"^[०-९0-9]{1,3}\s+", "", clean_text(text))


def extract_records(table):
    records = []
    audit = []

    with pymupdf.open(PDF_PATH) as document:
        page = document[PAGE_NUMBER - 1]
        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(RENDER_SCALE, RENDER_SCALE),
            alpha=False,
        )
        pixmap.save(OUTPUT_DIR / "page19_rendered.png")

        with Image.frombytes(
            "RGB", (pixmap.width, pixmap.height), pixmap.samples
        ) as image:
            for row_index, row in table.df.iterrows():
                values = [clean_text(value) for value in row]

                serial = extract_serial(values[0])
                if serial is None:
                    serial = extract_serial(values[1])
                if serial is None:
                    continue

                activity = read_activity(
                    page, image, table.cells[row_index][1]
                )

                if not activity:
                    raise RuntimeError(
                        f"Nepali OCR returned no text for serial {serial}."
                    )

                records.append(
                    dict(zip(COLUMNS, [serial, activity, *values[2:]]))
                )

                audit.append({
                    "serial_no": serial,
                    "pdf_text": values[1],
                    "ocr_text": activity,
                })

    records.sort(key=lambda item: item["serial_no"])
    return records, audit


def validate_records(records):
    serials = [row["serial_no"] for row in records]
    duplicates = sorted(
        number
        for number, count in Counter(serials).items()
        if count > 1
    )
    missing = sorted(EXPECTED_SERIALS - set(serials))
    unexpected = sorted(set(serials) - EXPECTED_SERIALS)

    if missing or duplicates or unexpected or len(records) != 17:
        raise RuntimeError(
            f"Row validation failed: missing={missing}, "
            f"duplicates={duplicates}, unexpected={unexpected}, "
            f"count={len(records)}"
        )

    return {
        "rows_extracted": len(records),
        "serial_numbers": serials,
        "duplicate_serial_numbers": duplicates,
        "missing_serial_numbers": missing,
        "serial_numbers_valid": True,
        "text_accuracy_verified": False,
    }


def main():
    check_environment()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    table = read_table()
    records, audit = extract_records(table)
    validation = validate_records(records)

    validation.update({
        "tables_detected": 1,
        "physical_rows_detected": len(table.df),
        "columns_detected": len(table.df.columns),
    })

    result = {
        "source_file": PDF_PATH.name,
        "page": PAGE_NUMBER,
        "printed_page": 17,
        "amount_unit": "thousand NPR",
        "columns": COLUMNS,
        "extraction_method": {
            "table_structure": "Lipi Pdf2Json with Camelot Lattice",
            "activity_text": "Tesseract Nepali OCR",
            "numeric_cells": "PDF text",
            "pdf_rendering": "PyMuPDF",
        },
        "validation": validation,
        "rows": records,
    }

    json_path = OUTPUT_DIR / "bharatpur_page19_clean.json"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    csv_path = OUTPUT_DIR / "bharatpur_page19_clean.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(records)

    audit_path = OUTPUT_DIR / "page19_cell_ocr.json"
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Lipi Pdf2Json + lattice: 1 table, 9 columns, 17 numbered records.")
    print(f"Raw JSON: {OUTPUT_DIR / 'bharatpur_page19_lipi_raw.json'}")
    print(f"Clean JSON: {json_path}")
    print(f"CSV: {csv_path}")
    print("Check OCR wording and amounts against the PDF before using the data.")


if __name__ == "__main__":
    main()
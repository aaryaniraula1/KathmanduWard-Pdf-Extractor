import json
import re
from pathlib import Path

import camelot
import pandas as pd
import pymupdf
import pytesseract
from PIL import Image


PROJECT_DIR = Path(__file__).resolve().parent.parent

PDF_PATH = PROJECT_DIR / "input" / "Bharatpur_Budget.pdf"
OUTPUT_DIR = PROJECT_DIR / "output"

PAGE_NUMBER = 19

OUTPUT_JSON = OUTPUT_DIR / "bharatpur_page19_clean.json"
OUTPUT_CSV = OUTPUT_DIR / "bharatpur_page19_clean.csv"
OUTPUT_OCR = OUTPUT_DIR / "page19_cell_ocr.txt"
OUTPUT_IMAGE = OUTPUT_DIR / "page19_rendered.png"

OCR_LANGUAGE = "nep"
RENDER_SCALE = 4

NEPALI_DIGITS = str.maketrans(
    "०१२३४५६७८९",
    "0123456789"
)


def convert_nepali_digits(value):
    return str(value).translate(NEPALI_DIGITS)


def clean_text(text):
    if text is None:
        return ""

    text = re.sub(r"[\r\n\t]+", " ", str(text))
    return re.sub(r"\s+", " ", text).strip()


def extract_serial_number(text):
    if not text:
        return None

    text = clean_text(text)

    match = re.match(
        r"^([०-९0-9]{1,3})(?:\s+|$)",
        text
    )

    if not match:
        return None

    try:
        return int(
            convert_nepali_digits(match.group(1))
        )
    except ValueError:
        return None


def remove_leading_serial(text):
    if not text:
        return ""

    return re.sub(
        r"^[०-९0-9]{1,3}\s+",
        "",
        clean_text(text)
    ).strip()


def crop_pdf_cell(page, page_image, cell, padding=2):
    page_width = page.rect.width
    page_height = page.rect.height

    x1 = max(0, cell.x1 - padding)
    y1 = max(0, cell.y1 - padding)
    x2 = min(page_width, cell.x2 + padding)
    y2 = min(page_height, cell.y2 + padding)

    left = int(x1 * RENDER_SCALE)
    right = int(x2 * RENDER_SCALE)

    top = int(
        (page_height - y2) * RENDER_SCALE
    )

    bottom = int(
        (page_height - y1) * RENDER_SCALE
    )

    left = max(0, min(left, page_image.width))
    right = max(0, min(right, page_image.width))
    top = max(0, min(top, page_image.height))
    bottom = max(0, min(bottom, page_image.height))

    if right <= left or bottom <= top:
        return None

    return page_image.crop(
        (left, top, right, bottom)
    )


def ocr_cell(page, page_image, cell):
    cropped = crop_pdf_cell(
        page,
        page_image,
        cell
    )

    if cropped is None:
        return ""

    text = pytesseract.image_to_string(
        cropped,
        lang=OCR_LANGUAGE,
        config="--psm 6"
    )

    return clean_text(text)


def main():

    if not PDF_PATH.exists():
        raise FileNotFoundError(
            f"PDF not found: {PDF_PATH}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    tables = camelot.read_pdf(
        str(PDF_PATH),
        pages=str(PAGE_NUMBER),
        flavor="lattice"
    )

    if len(tables) == 0:
        raise RuntimeError(
            "No table detected by Camelot Lattice."
        )

    table = tables[0]
    raw_df = table.df.copy()

    document = pymupdf.open(
        str(PDF_PATH)
    )

    try:

        page = document[PAGE_NUMBER - 1]

        matrix = pymupdf.Matrix(
            RENDER_SCALE,
            RENDER_SCALE
        )

        pixmap = page.get_pixmap(
            matrix=matrix,
            alpha=False
        )

        pixmap.save(
            str(OUTPUT_IMAGE)
        )

        page_image = Image.open(
            OUTPUT_IMAGE
        ).convert("RGB")

        records = []
        ocr_log = []

        for row_index, row in raw_df.iterrows():

            cells = table.cells[row_index]

            cell_values = [
                clean_text(value)
                for value in row.tolist()
            ]

            serial = extract_serial_number(
                cell_values[0]
            )

            serial_source = "column_1"

            if serial is None and len(cell_values) > 1:

                serial = extract_serial_number(
                    cell_values[1]
                )

                if serial is not None:
                    serial_source = "activity_cell"

            if serial is None:
                continue

            original_activity = (
                cell_values[1]
                if len(cell_values) > 1
                else ""
            )

            ocr_activity = ""

            if len(cells) > 1:

                ocr_activity = ocr_cell(
                    page,
                    page_image,
                    cells[1]
                )

                ocr_activity = remove_leading_serial(
                    ocr_activity
                )

            activity = (
                ocr_activity
                if ocr_activity
                else remove_leading_serial(
                    original_activity
                )
            )

            activity_source = (
                "tesseract_nepali_ocr"
                if ocr_activity
                else "pdf_text"
            )

            values = []

            for index, value in enumerate(cell_values):

                value = clean_text(value)

                if index == 0:
                    value = ""

                elif index == 1:
                    value = activity

                values.append(value)

            record = {
                "serial_no": serial,
                "activity": (
                    values[1]
                    if len(values) > 1
                    else ""
                ),
                "expenditure_code": (
                    values[2]
                    if len(values) > 2
                    else ""
                ),
                "column_4": (
                    values[3]
                    if len(values) > 3
                    else ""
                ),
                "column_5": (
                    values[4]
                    if len(values) > 4
                    else ""
                ),
                "column_6": (
                    values[5]
                    if len(values) > 5
                    else ""
                ),
                "column_7": (
                    values[6]
                    if len(values) > 6
                    else ""
                ),
                "column_8": (
                    values[7]
                    if len(values) > 7
                    else ""
                ),
                "development_goal_no": (
                    values[8]
                    if len(values) > 8
                    else ""
                )
            }

            records.append(record)

            ocr_log.append({
                "serial_no": serial,
                "serial_source": serial_source,
                "source": activity_source,
                "pdf_text": original_activity,
                "ocr_text": ocr_activity
            })

        records.sort(
            key=lambda item: item["serial_no"]
        )

        serial_numbers = [
            item["serial_no"]
            for item in records
        ]

        duplicate_serials = sorted({
            number
            for number in serial_numbers
            if serial_numbers.count(number) > 1
        })

        missing_serials = []

        if serial_numbers:

            expected_serials = set(
                range(
                    min(serial_numbers),
                    max(serial_numbers) + 1
                )
            )

            missing_serials = sorted(
                expected_serials -
                set(serial_numbers)
            )

        serial_numbers_valid = (
            len(duplicate_serials) == 0
            and len(missing_serials) == 0
        )

        result = {
            "source_file": PDF_PATH.name,
            "page": PAGE_NUMBER,
            "columns": [
                "serial_no",
                "activity",
                "expenditure_code",
                "column_4",
                "column_5",
                "column_6",
                "column_7",
                "column_8",
                "development_goal_no"
            ],
            "extraction_method": {
                "table_structure": "Camelot Lattice",
                "activity_text": "Tesseract Nepali OCR",
                "pdf_rendering": "PyMuPDF"
            },
            "validation": {
                "tables_detected": len(tables),
                "physical_rows_detected": len(raw_df),
                "columns_detected": len(raw_df.columns),
                "rows_extracted": len(records),
                "serial_numbers": serial_numbers,
                "duplicate_serial_numbers": duplicate_serials,
                "missing_serial_numbers": missing_serials,
                "serial_numbers_valid": serial_numbers_valid
            },
            "rows": records
        }

        with open(
            OUTPUT_JSON,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                result,
                file,
                ensure_ascii=False,
                indent=2
            )

        pd.DataFrame(records).to_csv(
            OUTPUT_CSV,
            index=False,
            encoding="utf-8-sig"
        )

        with open(
            OUTPUT_OCR,
            "w",
            encoding="utf-8"
        ) as file:

            for item in ocr_log:

                file.write(
                    f"Serial: {item['serial_no']}\n"
                )

                file.write(
                    f"Serial source: {item['serial_source']}\n"
                )

                file.write(
                    f"Source: {item['source']}\n"
                )

                file.write(
                    f"PDF text: {item['pdf_text']}\n"
                )

                file.write(
                    f"OCR text: {item['ocr_text']}\n"
                )

                file.write(
                    "-" * 60 + "\n"
                )

        print(f"Tables detected: {len(tables)}")
        print(f"Rows detected: {len(raw_df)}")
        print(f"Columns detected: {len(raw_df.columns)}")
        print(f"Rows extracted: {len(records)}")
        print(f"Serial numbers: {serial_numbers}")
        print(f"Duplicate serials: {duplicate_serials}")
        print(f"Missing serials: {missing_serials}")
        print(f"Serial check: {serial_numbers_valid}")
        print(f"JSON: {OUTPUT_JSON}")
        print(f"CSV: {OUTPUT_CSV}")
        print(f"OCR log: {OUTPUT_OCR}")
        print(f"Rendered page: {OUTPUT_IMAGE}")

    finally:
        document.close()


if __name__ == "__main__":
    main()
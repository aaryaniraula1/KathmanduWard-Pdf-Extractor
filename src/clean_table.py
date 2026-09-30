import json
import re
from pathlib import Path

import pandas as pd
from lipi.converter.pdf2df.clean_wrapper import clean_wrapper


PROJECT_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_DIR / "output" / "pdf2json"
OUTPUT_DIR = PROJECT_DIR / "output" / "cleaning"

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

DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
EXPECTED_SERIALS = set(range(1, 18))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def get_serial(row):
    for value in row.iloc[:2]:
        match = re.match(
            r"^([०-९0-9]{1,3})(?:\s+|$)",
            str(value).strip(),
        )
        if match:
            return int(match[1].translate(DIGITS))
    return None


def read_ocr():
    entries = read_json(INPUT_DIR / "page19_cell_ocr.json")
    activities = {}

    for entry in entries:
        serial = int(entry["serial_no"])
        text = re.sub(r"\s+", " ", entry["ocr_text"]).strip()

        if serial in activities:
            raise ValueError(f"Duplicate OCR serial: {serial}")
        if not text:
            raise ValueError(f"Empty OCR text for serial: {serial}")

        activities[serial] = text

    if set(activities) != EXPECTED_SERIALS:
        raise ValueError("OCR must contain exactly serials 1–17.")

    return activities


def main():
    raw = read_json(INPUT_DIR / "bharatpur_page19_lipi_raw.json")
    table = pd.DataFrame(raw["table"])

    table = table.loc[
        sorted(table.index, key=int),
        sorted(table.columns, key=int),
    ].reset_index(drop=True)

    if len(table.columns) != len(COLUMNS):
        raise ValueError("Expected 9 columns.")

    serials = table.apply(get_serial, axis=1)
    rows_to_remove = table.index[serials.isna()].tolist()
    retained_serials = serials.dropna().astype(int).tolist()

    if sorted(retained_serials) != sorted(EXPECTED_SERIALS):
        raise ValueError("Expected exactly one record for each serial 1–17.")

    original_numbers = (
        table.drop(index=rows_to_remove)
        .iloc[:, 2:]
        .fillna("")
        .reset_index(drop=True)
    )
    original_numbers.columns = COLUMNS[2:]

    result = clean_wrapper(
        {"table": table.copy()},
        [
            {"operator": "header", "value": COLUMNS},
            {"operator": "remove_row", "value": rows_to_remove},
            {"operator": "fill_null", "value": ""},
        ],
    )

    cleaned = result["table"].copy()
    cleaned["serial_no"] = retained_serials
    cleaned["activity"] = cleaned["serial_no"].map(read_ocr())

    if not cleaned[COLUMNS[2:]].equals(original_numbers):
        raise ValueError("Numeric fields changed during cleaning.")

    cleaned = cleaned.sort_values("serial_no").reset_index(drop=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    cleaned.to_csv(
        OUTPUT_DIR / "page19_table.csv",
        index=False,
        encoding="utf-8-sig",
    )

    (OUTPUT_DIR / "page19_table.json").write_text(
        json.dumps(
            cleaned.to_dict(orient="records"),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Before cleaning: {len(table)} rows")
    print(f"Removed header/section rows: {len(rows_to_remove)}")
    print(f"After cleaning: {len(cleaned)} rows")
    print("Serials 1–17 verified; numeric fields unchanged.")
    print("OCR wording still requires visual verification.")
    print(f"Saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
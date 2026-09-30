import json
from pathlib import Path

import pandas as pd
from lipi.converter.pdf2df.validate import validate
from lipi.errors import ValidationError


PROJECT_DIR = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_DIR / "output" / "cleaning" / "page19_table.json"
OUTPUT_DIR = PROJECT_DIR / "output" / "validation"

TEXT_COLUMNS = [
    "activity",
    "expenditure_code",
    "allocation",
    "internal_source",
    "nepal_government",
    "province_government",
    "public_participation",
    "development_goal_no",
]

SCHEMA = {
    "columns": {
        "serial_no": {
            "dtype": "int64",
            "nullable": False,
            "required": True,
            "unique": True,
            "checks": {
                "greater_than_or_equal_to": 1,
                "less_than_or_equal_to": 17,
            },
        },
        **{
            name: {
                "dtype": "object",
                "nullable": False,
                "required": True,
            }
            for name in TEXT_COLUMNS
        },
    },
    "strict": True,
    "coerce": False,
}


def main():
    records = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    table = pd.DataFrame(records, dtype=object)
    table["serial_no"] = pd.Series(
        [row["serial_no"] for row in records]
    )

    checked = validate(table, SCHEMA)

    if len(checked) != 17:
        raise ValueError("Expected 17 records.")

    for column in TEXT_COLUMNS:
        if not checked[column].map(
            lambda value: isinstance(value, str) and bool(value.strip())
        ).all():
            raise ValueError(f"Empty or non-text value in {column}.")

    invalid_sample = table.copy()
    invalid_sample.loc[1, "serial_no"] = invalid_sample.loc[0, "serial_no"]

    try:
        validate(invalid_sample, SCHEMA)
    except ValidationError:
        duplicate_rejected = True
    else:
        raise RuntimeError("The duplicate serial was not rejected.")

    report = {
        "input_file": INPUT_FILE.name,
        "schema_passed": True,
        "rows": len(checked),
        "columns": len(checked.columns),
        "nonempty_text_fields": True,
        "duplicate_test_rejected": duplicate_rejected,
        "pdf_content_accuracy_verified": False,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_file = OUTPUT_DIR / "report.json"
    report_file.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("Lipi schema validation passed.")
    print("Duplicate serial correctly rejected in a test copy.")
    print(f"Report: {report_file}")


if __name__ == "__main__":
    main()
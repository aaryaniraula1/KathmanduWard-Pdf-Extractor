from pathlib import Path

from src.exporter import export_csv, export_json
from src.pdf_reader import open_pdf
from src.table_parser import parse_services


BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = (
    BASE_DIR
    / "input"
    / "filesKathmandu.pdf"
)

OUTPUT_DIR = BASE_DIR / "output"

JSON_OUTPUT = (
    OUTPUT_DIR
    / "kathmandu_ward_services.json"
)

CSV_OUTPUT = (
    OUTPUT_DIR
    / "kathmandu_ward_services.csv"
)


def main() -> None:

    print(
        f"Processing: {INPUT_FILE.name}"
    )

    with open_pdf(INPUT_FILE) as document:

        print(
            f"Pages: {len(document)}"
        )

        services = parse_services(
            document
        )

    print(
        f"Services extracted: "
        f"{len(services)}"
    )

    export_json(
        services,
        JSON_OUTPUT,
    )

    export_csv(
        services,
        CSV_OUTPUT,
    )

    print(
        f"JSON saved: {JSON_OUTPUT}"
    )

    print(
        f"CSV saved: {CSV_OUTPUT}"
    )

    print("Done.")


if __name__ == "__main__":
    main()
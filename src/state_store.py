from pathlib import Path

from lipi.db_utils import DBHelper, get_db_enq


PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_DIR / "output" / "state"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    db = DBHelper(
        get_db_enq(
            backend="file",
            path=str(OUTPUT_DIR / "state.json"),
        )
    )

    document_id = "bharatpur-page19"

    db.set(document_id, {"status": "processing", "page": "19"})
    print("Initial state:", db.get(document_id))

    db.set(document_id, {"status": "completed", "page": "19"})
    print("Updated state:", db.get(document_id))


if __name__ == "__main__":
    main()
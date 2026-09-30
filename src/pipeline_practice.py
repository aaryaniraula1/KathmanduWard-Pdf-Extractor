import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from loguru import logger

from lipi.pipeline.pipeline import Pipeline
from lipi.pipeline_helpers import get_state


PROJECT_DIR = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_DIR / "input" / "Bharatpur_Budget.pdf"
OUTPUT_DIR = PROJECT_DIR / "output" / "pipeline"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory() as temporary:
        temporary_dir = Path(temporary)
        source = temporary_dir / "source.pdf"
        shutil.copy2(INPUT_FILE, source)

        config = {
            "input": {"type": "file", "value": str(source)},
            "trial": True,
            "partial": False,
            "pipeline": [
                {"operator": "savefile"},
                {
                    "operator": "ocr2pdf",
                    "options": {
                        "pages": "19",
                        "lang": "nep",
                        "sharpen": False,
                    },
                },
                {
                    "operator": "pdf2txt",
                    "options": {"pages": "1"},
                },
            ],
        }

        pipeline = Pipeline(
            state=get_state("bharatpur-page19"),
            config=config,
            input_dir=str(temporary_dir / "input"),
            output_dir=str(OUTPUT_DIR),
        )
        with logger.contextualize(pipeline_id=pipeline.state["id"]):
           state = pipeline.process()

        (OUTPUT_DIR / "state.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        if state["status"] != "completed":
            raise RuntimeError(f"Pipeline failed: {state['error']}")

        for filename in state["output"][1:]:
            if not Path(filename).is_file():
                raise RuntimeError(f"Missing output: {filename}")
            print(f"Saved: {filename}")

    print("Pipeline completed. State saved in output/pipeline/state.json.")


if __name__ == "__main__":
    main()
import json
from pathlib import Path

import pandas as pd


def export_json(
    services: list[dict],
    output_path: Path,
) -> None:

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            services,
            file,
            ensure_ascii=False,
            indent=2,
        )


def export_csv(
    services: list[dict],
    output_path: Path,
) -> None:

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    dataframe = pd.DataFrame(
        services
    )

    dataframe.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig",
    )
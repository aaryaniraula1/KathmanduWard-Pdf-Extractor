import re
import unicodedata


def clean_text(value: str | None) -> str:
    if not value:
        return ""

    text = unicodedata.normalize(
        "NFC",
        value,
    )

    text = text.replace("\u00a0", " ")

    # Normalize horizontal whitespace.
    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    # Normalize line spacing.
    text = re.sub(
        r"\s*\n\s*",
        "\n",
        text,
    )

    lines = []

    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        # Remove obvious isolated OCR artifacts.
        if re.fullmatch(
            r"[-|_=~]+",
            line,
        ):
            continue

        lines.append(line)

    return "\n".join(lines).strip()
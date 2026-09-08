from io import BytesIO

import pymupdf
import pytesseract
from PIL import Image, ImageOps


DEFAULT_DPI = 400


def render_cell(page, cell_bbox, dpi: int = DEFAULT_DPI) -> Image.Image:
    clip = pymupdf.Rect(cell_bbox)

    if clip.is_empty:
        raise ValueError("Empty cell bounding box")

    zoom = dpi / 72
    matrix = pymupdf.Matrix(zoom, zoom)

    pixmap = page.get_pixmap(
        matrix=matrix,
        clip=clip,
        alpha=False,
    )

    image = Image.open(
        BytesIO(pixmap.tobytes("png"))
    )

    image = ImageOps.grayscale(image)
    image = ImageOps.autocontrast(image)

    return image


def ocr_cell(
    page,
    cell_bbox,
    language: str = "nep",
) -> str:
    if cell_bbox is None:
        return ""

    image = render_cell(
        page,
        cell_bbox,
    )

    text = pytesseract.image_to_string(
        image,
        lang=language,
        config="--psm 6",
    )

    return text.strip()
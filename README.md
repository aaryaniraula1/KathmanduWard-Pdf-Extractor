# Bharatpur PDF Table Extraction

Extracts PDF page 19 (printed page 17) using Lipi's Pdf2Json
with Camelot lattice. Tesseract Nepali OCR improves activity
names, while numeric values come from PDF text extraction.

## Requirements

Ankamala Lipi, the packages in requirements.txt, and Tesseract
with the Nepali language model. Camelot is pinned to 1.0.9.

## Run

Place the PDF at input/Bharatpur_Budget.pdf.
Run using the Python environment where the dependencies are installed:

python src/extract_bharatpur.py

## Output

The output folder contains raw Lipi JSON, cleaned JSON and CSV,
an OCR comparison log, and the rendered page.

The extraction returns 17 numbered records and 9 columns.

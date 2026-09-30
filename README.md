# Bharatpur PDF Table Extraction

Extracts the table from Bharatpur's annual development plan, PDF page 19
(printed page 17), using Lipi's `Pdf2Json` with Camelot lattice.

Tesseract Nepali OCR reads activity names from individual table cells.
Numeric values are retained from PDF text extraction.

## Setup

Requires Python, the private Ankamala Lipi repository cloned locally,
and Tesseract with the Nepali (`nep`) language model.

Create a virtual environment and install dependencies in PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install "PATH\TO\YOUR\lipi" -r requirements.txt
```

Replace `PATH\TO\YOUR\lipi` with the clone folder containing `pyproject.toml`.

Keep `camelot-py==1.0.9` for compatibility with this Lipi integration.

## Run

Place the source PDF at `input/Bharatpur_Budget.pdf`, then run
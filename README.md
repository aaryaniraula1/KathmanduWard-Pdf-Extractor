# Lipi Practice

PDF extraction and processing exercises using Ankamala's Lipi library.

## Practices

- `pdf2json.py`: table extraction using Lipi's Pdf2Json with Camelot lattice and cell-level Nepali OCR.
- `pdf2txt.py`: compare direct text extraction with Lipi's Nepali OCR.
- `clean_table.py`: use Lipi's cleaning operators and match existing OCR text to table records.
- `state_store.py`: save and retrieve document status using Lipi's file backend.
- `pipeline_practice.py`: create a searchable PDF and extract its text through Lipi's pipeline.
- `validate_table.py`: validate table structure and test duplicate-serial rejection.

## Requirements

Ankamala Lipi, packages in requirements.txt, Poppler, and Tesseract
with the Nepali language model. Camelot is pinned to 1.0.9.

## Run

Place Bharatpur_Budget.pdf in input/.
Run scripts from the project folder using Python with the dependencies installed:

```powershell
python -X utf8 src/pdf2json.py
python -X utf8 src/pdf2txt.py
python -X utf8 src/clean_table.py
python -X utf8 src/state_store.py
python -X utf8 src/pipeline_practice.py
python -X utf8 src/validate_table.py
```

Run pdf2json before clean_table, and clean_table before validate_table.

## Results

Outputs are saved in separate folders under output/.
The table exercise extracts 17 numbered records and 9 columns
from PDF page 19, printed page 17.

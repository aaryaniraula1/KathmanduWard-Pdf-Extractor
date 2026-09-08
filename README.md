# Kathmandu Ward PDF Extractor

Python project for extracting structured service information from a Kathmandu Metropolitan City ward PDF.

## Extracted Data

- Service number
- Service name
- Required documents
- Fee
- Processing time
- Responsible person
- Start page
- End page

## Tech

- PyMuPDF
- Tesseract OCR
- Pandas

PyMuPDF is used for table structure and selected native text. Tesseract OCR is used where Nepali text extraction is unclear.

## Run

```powershell
pip install -r requirements.txt
python main.py
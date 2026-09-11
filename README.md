# Ankamala Site Testing

This repository contains automated tests and audit scripts for checking selected functionality and data quality on [ankamala.org](https://ankamala.org/).

The project currently focuses on three areas:

1. Site and API testing
2. Government hierarchy audit testing (`/gov`)
3. Document and source audit testing (`/docs`)

---

## 1. Site and API Testing

The `tests/` folder contains automated tests for basic Ankamala functionality.

Main test files:

```text
tests/
├── test_smoke.py
├── test_government.py
└── test_indicators.py
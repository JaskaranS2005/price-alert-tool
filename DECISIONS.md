# Decisions

- Prices, thresholds, and averages use `Decimal`; floats are never used by the CLI.
- Each instrument is sorted independently by its own trading dates. Missing calendar dates are not filled.
- A level alert requires a strict move to the requested side; equality alone never fires it.
- For a duplicate `(date, instrument)`, the last CSV occurrence wins and a warning is emitted.
- Invalid price rows and invalid individual rules are warned about and skipped. A malformed CSV header or JSON document is a whole-file error.
- Output is sorted by date then rule id. Threshold text is preserved from the JSON input.

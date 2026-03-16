# Test Protocol For Demo

## Goal

Show that the solution is not only functional, but also tested on a small realistic set of documents.

## Recommended Test Set

- 3 PDF files
- 3 DOCX files
- 3 image scans or screenshots
- 1 ZIP archive with mixed formats
- 1 English-language document for Qwen or fallback check

## What To Measure

1. Detection coverage
- Count how many expected sensitive fragments were present in the source document.
- Count how many of them were detected by the system.
- Formula: `coverage = detected / expected`.

2. False positives
- Count how many safe fragments were marked by mistake.
- Mention that the second review step allows the user to uncheck them before export.

3. Processing time
- Measure time for:
  - small file (1-2 pages),
  - medium file (5-10 pages),
  - image scan.

## Minimal Table For Presentation

| File | Format | Expected sensitive fragments | Detected | Coverage | Time |
|---|---|---:|---:|---:|---:|
| Contract-01 | PDF | 9 | 9 | 100% | 2.1 sec |
| Memo-02 | DOCX | 7 | 7 | 100% | 0.8 sec |
| Scan-03 | PNG | 8 | 7 | 87.5% | 3.4 sec |

## What To Say Out Loud

- We tested not only demo files, but a small mixed-format batch close to real user scenarios.
- OCR cases are naturally noisier than text-layer documents, which is why we kept the human confirmation step.
- The product is intentionally built around safe review before export, not blind automatic deletion.

## Strong Closing Line

This is not just a detector. It is a controlled release workflow for documents leaving the company perimeter.

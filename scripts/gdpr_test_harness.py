from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Sequence, Tuple
from zipfile import ZIP_DEFLATED, ZipFile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.core import OCR_AVAILABLE, analyze_file, build_redacted_zip, expand_archives
from scripts.synthetic_test_harness import (
    _print_summary,
    _render_eval_markdown,
    _resolve_font_path,
    _write_docx,
    _write_image,
    _write_image_pdf,
    _write_markdown,
    _write_pdf,
    _write_text,
)


TEST_DIR = ROOT_DIR / "test"
GDPR_DIR = TEST_DIR / "gdpr_corpus"
GDPR_MANIFEST_PATH = GDPR_DIR / "manifest.json"
GDPR_REPORT_JSON = TEST_DIR / "gdpr_eval_report.json"
GDPR_REPORT_MD = TEST_DIR / "gdpr_eval_report.md"
GDPR_SMOKE_ZIP = TEST_DIR / "gdpr_redaction_smoke.zip"

GDPR_CATEGORIES = {"PER", "ORG", "EMAIL", "PHONE", "MONEY", "PASSPORT", "ACCOUNT", "INN"}


def _case(filename: str, expected_hits: Sequence[Tuple[str, str]], **extra: object) -> Dict[str, object]:
    payload = {
        "filename": filename,
        "expected_hits": [{"label": label, "text": text} for label, text in expected_hits],
    }
    payload.update(extra)
    return payload


def _fold_ocr_alnum(value: str) -> str:
    folded = value.upper()
    folded = folded.translate(
        str.maketrans(
            {
                "O": "0",
                "Q": "0",
                "D": "0",
                "B": "8",
                "I": "1",
                "L": "1",
                "Z": "2",
                "S": "5",
                "Î": "0",
                "І": "0",
                "|": "1",
            }
        )
    )
    return "".join(char for char in folded if char.isalnum())


def _normalize_gdpr_text(label: str, text: str) -> str:
    raw = text.lower().replace("ё", "е").replace("\n", " ").replace("\t", " ").strip()

    if label == "EMAIL":
        compact = raw.replace("î", "0").replace("і", "0")
        compact = re.sub(r"([a-z0-9._%+\-]+(?:\s+[a-z0-9._%+\-]+)+)(?=\s*@)", lambda match: match.group(1).replace(" ", "."), compact)
        compact = re.sub(r"(@[a-z0-9.\-]+)\s+([a-z]{2,24})\b", r"\1.\2", compact)
        compact = compact.replace(" ", "").replace(".@", "@")
        return re.sub(r"[^a-z0-9@.]+", "", compact)

    if label == "PHONE":
        compact = raw.replace(" ", "")
        compact = compact.translate(str.maketrans({"o": "0", "о": "0", "î": "0", "і": "0"}))
        return re.sub(r"\D", "", compact)

    if label in {"ACCOUNT", "INN", "PASSPORT"}:
        return _fold_ocr_alnum(raw)

    if label == "MONEY":
        compact = raw.replace(" ", "").translate(str.maketrans({"o": "0", "î": "0", "і": "0"}))
        return re.sub(r"[^a-z0-9$€£]+", "", compact)

    return re.sub(r"[\W_]+", " ", raw, flags=re.UNICODE).strip()


def _is_gdpr_match(expected: Dict[str, str], found: Dict[str, object]) -> bool:
    if expected["label"] != found["label"]:
        return False

    expected_norm = _normalize_gdpr_text(expected["label"], expected["text"])
    found_norm = _normalize_gdpr_text(str(found["label"]), str(found["text"]))

    if not expected_norm or not found_norm:
        return False

    if expected["label"] in {"EMAIL", "PHONE", "ACCOUNT", "INN", "PASSPORT", "MONEY"}:
        return expected_norm == found_norm

    return expected_norm == found_norm or expected_norm in found_norm or found_norm in expected_norm


def _compare_gdpr_case(
    display_name: str,
    expected_hits: Sequence[Dict[str, str]],
    found_hits: Sequence[Dict[str, object]],
    engine: str,
) -> Dict[str, object]:
    unmatched_found = list(found_hits)
    matched_expected: List[Dict[str, str]] = []
    missed_expected: List[Dict[str, str]] = []

    for expected in expected_hits:
        match_index = next((index for index, found in enumerate(unmatched_found) if _is_gdpr_match(expected, found)), None)
        if match_index is None:
            missed_expected.append(dict(expected))
            continue
        matched_expected.append(dict(expected))
        unmatched_found.pop(match_index)

    expected_by_label = Counter(item["label"] for item in expected_hits)
    found_by_label = Counter(str(item["label"]) for item in found_hits)
    matched_by_label = Counter(item["label"] for item in matched_expected)

    expected_count = len(expected_hits)
    found_count = len(found_hits)
    matched_count = len(matched_expected)
    recall = round((matched_count / expected_count) * 100, 2) if expected_count else 100.0
    precision = round((matched_count / found_count) * 100, 2) if found_count else 100.0

    return {
        "file": display_name,
        "engine": engine,
        "expected_count": expected_count,
        "found_count": found_count,
        "matched_count": matched_count,
        "recall_percent": recall,
        "precision_percent": precision,
        "expected_by_label": dict(expected_by_label),
        "found_by_label": dict(found_by_label),
        "matched_by_label": dict(matched_by_label),
        "missed": missed_expected,
        "unexpected": [
            {
                "label": str(hit["label"]),
                "text": str(hit["text"]),
                "page": hit.get("page"),
                "method": hit.get("method"),
            }
            for hit in unmatched_found
        ],
    }


def _render_gdpr_markdown(report: Dict[str, object]) -> str:
    body = _render_eval_markdown(report)
    notes = [
        "# GDPR evaluation report",
        "",
        f"- OCR available in current environment: {report['summary']['ocr_available']}",
        f"- Files skipped because OCR is unavailable: {report['summary']['files_skipped']}",
    ]
    if report.get("skipped"):
        notes.append("")
        notes.append("## Skipped files")
        notes.append("")
        for item in report["skipped"]:
            notes.append(f"- {item}")
    return "\n".join(notes) + "\n\n" + body


def build_gdpr_specs() -> List[Dict[str, object]]:
    return [
        _case(
            "01_data_transfer_request.txt",
            [
                ("PER", "Jane Doe"),
                ("ORG", "Contoso Ltd"),
                ("EMAIL", "jane.doe@contoso.com"),
                ("PHONE", "+44 20 7946 0958"),
                ("PASSPORT", "XH1234567"),
                ("ACCOUNT", "DE44500105175407324931"),
                ("INN", "DE123456789"),
                ("MONEY", "EUR 18,500.00"),
            ],
            kind="file",
            writer="text",
            content="""
Data Transfer Request

Prepared by: Jane Doe
Organization: Contoso Ltd
Email: jane.doe@contoso.com
Phone: +44 20 7946 0958
Passport No: XH1234567
Bank account: DE44500105175407324931
Tax ID: DE123456789
Amount: EUR 18,500.00
""",
        ),
        _case(
            "02_vendor_onboarding.md",
            [
                ("PER", "Michael Reed"),
                ("ORG", "Northwind GmbH"),
                ("EMAIL", "m.reed@northwind.eu"),
                ("PHONE", "+1 (415) 555-0187"),
                ("ACCOUNT", "NL91ABNA0417164300"),
                ("INN", "NL123456789B01"),
                ("MONEY", "USD 9,250.00"),
            ],
            kind="file",
            writer="text",
            content="""
# Vendor onboarding

Contact person: Michael Reed  
Company: Northwind GmbH  
Email: m.reed@northwind.eu  
Phone: +1 (415) 555-0187  
IBAN: NL91ABNA0417164300  
VAT ID: NL123456789B01  
Amount due: USD 9,250.00
""",
        ),
        _case(
            "03_retention_notice.docx",
            [
                ("PER", "Sarah Connor"),
                ("ORG", "Fabrikam Inc."),
                ("EMAIL", "sarah.connor@fabrikam.com"),
                ("PHONE", "+353 1 531 4000"),
                ("ACCOUNT", "GB29NWBK60161331926819"),
                ("INN", "IE6388047V"),
                ("MONEY", "GBP 12,400.00"),
            ],
            kind="file",
            writer="docx",
            content="""
Retention notice

Prepared by: Sarah Connor.
Organization: Fabrikam Inc.
Email: sarah.connor@fabrikam.com.
Phone: +353 1 531 4000.
Bank account: GB29NWBK60161331926819.
Tax ID: IE6388047V.
Amount: GBP 12,400.00.
""",
        ),
        _case(
            "04_processing_agreement.pdf",
            [
                ("PER", "Olivia Brown"),
                ("ORG", "Alpine AG"),
                ("EMAIL", "olivia.brown@alpine.eu"),
                ("PHONE", "+49 30 12345678"),
                ("ACCOUNT", "CH9300762011623852957"),
                ("MONEY", "EUR 4,700.00"),
            ],
            kind="file",
            writer="pdf",
            content="""
Processing agreement

Contact person: Olivia Brown.
Company: Alpine AG.
Email: olivia.brown@alpine.eu.
Phone: +49 30 12345678.
IBAN: CH9300762011623852957.
Service fee: EUR 4,700.00.
""",
        ),
        _case(
            "05_scan_notice.png",
            [
                ("PER", "Emily Carter"),
                ("ORG", "Blue Yonder LLC"),
                ("EMAIL", "emily.carter@blueyonder.com"),
                ("PHONE", "+44 161 496 0000"),
                ("ACCOUNT", "GB82WEST12345698765432"),
                ("MONEY", "GBP 6,300.00"),
            ],
            kind="file",
            writer="image",
            image_format="PNG",
            lines=[
                "STRICTLY CONFIDENTIAL",
                "",
                "Prepared by: Emily Carter",
                "Company: Blue Yonder LLC",
                "Email: emily.carter@blueyonder.com",
                "Phone: +44 161 496 0000",
                "IBAN: GB82WEST12345698765432",
                "Amount: GBP 6,300.00",
            ],
        ),
        _case(
            "06_image_only_pdf.pdf",
            [
                ("PER", "Emily Carter"),
                ("ORG", "Blue Yonder LLC"),
                ("EMAIL", "emily.carter@blueyonder.com"),
                ("PHONE", "+44 161 496 0000"),
                ("ACCOUNT", "GB82WEST12345698765432"),
                ("MONEY", "GBP 6,300.00"),
            ],
            kind="file",
            writer="image_pdf",
            source_image="05_scan_notice.png",
        ),
        _case(
            "07_clean_policy.txt",
            [],
            kind="file",
            writer="text",
            content="""
Privacy policy summary

This page explains the retention process and security controls.
It does not contain personal contacts, bank details, passports, or tax identifiers.
""",
        ),
        {
            "filename": "08_bundle.zip",
            "kind": "zip",
            "members": [
                _case(
                    "bundle_email.txt",
                    [
                        ("PER", "Daniel Moore"),
                        ("ORG", "Woodgrove PLC"),
                        ("EMAIL", "daniel.moore@woodgrove.co.uk"),
                        ("PHONE", "+44 113 496 0999"),
                    ],
                    writer="text",
                    content="""
Transfer memo

Prepared by: Daniel Moore.
Organization: Woodgrove PLC.
Email: daniel.moore@woodgrove.co.uk.
Phone: +44 113 496 0999.
""",
                ),
                _case(
                    "bundle_scan.jpg",
                    [
                        ("ORG", "Fourth Coffee BV"),
                        ("ACCOUNT", "NL20INGB0001234567"),
                        ("INN", "NL998877665B01"),
                        ("MONEY", "EUR 1,250.00"),
                    ],
                    writer="image",
                    image_format="JPEG",
                    lines=[
                        "Fourth Coffee BV",
                        "IBAN: NL20INGB0001234567",
                        "VAT ID: NL998877665B01",
                        "Amount: EUR 1,250.00",
                    ],
                ),
            ],
        },
    ]


def _materialize_spec(base_dir: Path, spec: Dict[str, object], font_path: Path | None) -> Path:
    path = base_dir / str(spec["filename"])
    writer = str(spec["writer"])

    if writer == "text":
        _write_text(path, str(spec["content"]))
    elif writer == "docx":
        _write_docx(path, str(spec["content"]))
    elif writer == "pdf":
        _write_pdf(path, str(spec["content"]), font_path)
    elif writer == "image":
        _write_image(path, list(spec["lines"]), font_path, str(spec["image_format"]))
    elif writer == "image_pdf":
        source_image = base_dir / str(spec["source_image"])
        if not source_image.exists():
            raise FileNotFoundError(f"Source image for image-PDF not found: {source_image}")
        _write_image_pdf(path, source_image)
    else:
        raise ValueError(f"Unknown writer: {writer}")

    return path


def generate_gdpr_corpus(target_dir: Path = GDPR_DIR) -> Dict[str, object]:
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    font_path = _resolve_font_path()
    manifest_cases: List[Dict[str, object]] = []

    for spec in build_gdpr_specs():
        if spec["kind"] == "file":
            _materialize_spec(target_dir, spec, font_path)
            manifest_cases.append(
                {
                    "filename": spec["filename"],
                    "kind": "file",
                    "ocr_required": bool(spec.get("writer") in {"image", "image_pdf"}),
                    "expected_hits": spec["expected_hits"],
                }
            )
            continue

        zip_path = target_dir / str(spec["filename"])
        temp_dir = target_dir / f"_{zip_path.stem}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        members_manifest: List[Dict[str, object]] = []

        with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
            for member in spec["members"]:
                member_path = _materialize_spec(temp_dir, member, font_path)
                archive.write(member_path, arcname=member_path.name)
                members_manifest.append(
                    {
                        "filename": member["filename"],
                        "ocr_required": bool(member.get("writer") in {"image", "image_pdf"}),
                        "expected_hits": member["expected_hits"],
                    }
                )

        shutil.rmtree(temp_dir, ignore_errors=True)
        manifest_cases.append(
            {
                "filename": spec["filename"],
                "kind": "zip",
                "members": members_manifest,
            }
        )

    manifest = {"categories": sorted(GDPR_CATEGORIES), "cases": manifest_cases}
    GDPR_MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def evaluate_gdpr_corpus(
    manifest_path: Path = GDPR_MANIFEST_PATH,
    report_json_path: Path = GDPR_REPORT_JSON,
    report_md_path: Path = GDPR_REPORT_MD,
    smoke_zip_path: Path = GDPR_SMOKE_ZIP,
) -> Dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    categories = set(manifest.get("categories", sorted(GDPR_CATEGORIES)))
    corpus_dir = manifest_path.parent

    file_reports: List[Dict[str, object]] = []
    file_states: List[Dict[str, object]] = []
    summary = Counter()
    file_counter = 0
    skipped: List[str] = []

    for case in manifest["cases"]:
        case_path = corpus_dir / str(case["filename"])
        if case["kind"] == "file":
            if case.get("ocr_required") and not OCR_AVAILABLE:
                skipped.append(case_path.name)
                continue
            file_counter += 1
            analysis, state = analyze_file(
                file_id=f"g{file_counter}",
                filename=case_path.name,
                data=case_path.read_bytes(),
                categories=categories,
                custom_words=[],
                use_ocr=True,
                engine_preference="auto",
            )
            file_states.append(state)
            file_reports.append(
                _compare_gdpr_case(
                    display_name=case_path.name,
                    expected_hits=case["expected_hits"],
                    found_hits=analysis["hits"],
                    engine=str(analysis.get("engine_used", analysis.get("engine", "unknown"))),
                )
            )
            continue

        expanded = expand_archives([(case_path.name, case_path.read_bytes())])
        expected_members = {str(member["filename"]): member["expected_hits"] for member in case["members"]}
        expected_ocr_flags = {str(member["filename"]): bool(member.get("ocr_required")) for member in case["members"]}
        for member_name, member_bytes in expanded:
            if expected_ocr_flags.get(member_name) and not OCR_AVAILABLE:
                skipped.append(f"{case_path.name}::{member_name}")
                continue
            file_counter += 1
            analysis, state = analyze_file(
                file_id=f"g{file_counter}",
                filename=member_name,
                data=member_bytes,
                categories=categories,
                custom_words=[],
                use_ocr=True,
                engine_preference="auto",
            )
            file_states.append(state)
            file_reports.append(
                _compare_gdpr_case(
                    display_name=f"{case_path.name}::{member_name}",
                    expected_hits=expected_members.get(member_name, []),
                    found_hits=analysis["hits"],
                    engine=str(analysis.get("engine_used", analysis.get("engine", "unknown"))),
                )
            )

    label_stats: Dict[str, Counter] = {}
    for item in file_reports:
        summary["files_checked"] += 1
        summary["expected_hits"] += item["expected_count"]
        summary["found_hits"] += item["found_count"]
        summary["matched_hits"] += item["matched_count"]
        summary["missed_hits"] += len(item["missed"])
        summary["unexpected_hits"] += len(item["unexpected"])

        for label in set(item["expected_by_label"]) | set(item["found_by_label"]) | set(item["matched_by_label"]):
            stats = label_stats.setdefault(label, Counter())
            stats["expected"] += item["expected_by_label"].get(label, 0)
            stats["found"] += item["found_by_label"].get(label, 0)
            stats["matched"] += item["matched_by_label"].get(label, 0)

    for stats in label_stats.values():
        stats["missed"] = stats["expected"] - stats["matched"]
        stats["unexpected"] = stats["found"] - stats["matched"]

    recall = round((summary["matched_hits"] / summary["expected_hits"]) * 100, 2) if summary["expected_hits"] else 100.0
    precision = round((summary["matched_hits"] / summary["found_hits"]) * 100, 2) if summary["found_hits"] else 100.0

    redaction_smoke_ok = False
    redaction_error = None
    try:
        analysis_state = {
            "categories": sorted(categories),
            "custom_words": [],
            "use_ocr": True,
            "engine": "auto",
            "files": file_states,
        }
        selected = {str(item["file_id"]): [str(hit["id"]) for hit in item["hits"]] for item in file_states}
        archive_bytes, redaction_report = build_redacted_zip(
            analysis_state=analysis_state,
            selected_hit_ids_by_file=selected,
            redaction_style="black",
            include_original=True,
            include_markdown=True,
            include_docx=True,
        )
        smoke_zip_path.write_bytes(archive_bytes)
        redaction_smoke_ok = len(archive_bytes) > 0 and bool(redaction_report)
    except Exception as error:  # pragma: no cover
        redaction_error = str(error)

    report = {
        "summary": {
            "files_checked": summary["files_checked"],
            "files_skipped": len(skipped),
            "expected_hits": summary["expected_hits"],
            "found_hits": summary["found_hits"],
            "matched_hits": summary["matched_hits"],
            "missed_hits": summary["missed_hits"],
            "unexpected_hits": summary["unexpected_hits"],
            "recall_percent": recall,
            "precision_percent": precision,
            "redaction_smoke_ok": redaction_smoke_ok,
            "redaction_error": redaction_error,
            "ocr_available": OCR_AVAILABLE,
        },
        "labels": {label: dict(stats) for label, stats in sorted(label_stats.items())},
        "files": file_reports,
        "skipped": skipped,
    }

    report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(report_md_path, _render_gdpr_markdown(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="GDPR-focused English corpus generator and evaluator.")
    parser.add_argument("command", choices=["generate", "evaluate", "full"], nargs="?", default="full")
    args = parser.parse_args()

    if args.command in {"generate", "full"}:
        generate_gdpr_corpus()
        print(f"GDPR corpus generated: {GDPR_DIR}")

    if args.command in {"evaluate", "full"}:
        report = evaluate_gdpr_corpus()
        _print_summary(report, "GDPR evaluation")


if __name__ == "__main__":
    main()

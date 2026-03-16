from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import textwrap
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Sequence, Tuple
from zipfile import ZIP_DEFLATED, ZipFile

import fitz
from docx import Document
from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.core import analyze_file, build_redacted_zip, expand_archives


TEST_DIR = ROOT_DIR / "test"
SYNTHETIC_DIR = TEST_DIR / "synthetic_corpus"
MANIFEST_PATH = SYNTHETIC_DIR / "manifest.json"
SYNTHETIC_REPORT_JSON = TEST_DIR / "synthetic_eval_report.json"
SYNTHETIC_REPORT_MD = TEST_DIR / "synthetic_eval_report.md"
SYNTHETIC_SMOKE_ZIP = TEST_DIR / "synthetic_redaction_smoke.zip"
SCAN_REPORT_JSON = TEST_DIR / "existing_docs_scan.json"
SCAN_REPORT_MD = TEST_DIR / "existing_docs_scan.md"

DEFAULT_CATEGORIES = {
    "PER",
    "ORG",
    "EMAIL",
    "PHONE",
    "MONEY",
    "PASSPORT",
    "ACCOUNT",
    "INN",
}

IGNORED_SCAN_NAMES = {
    SYNTHETIC_REPORT_JSON.name,
    SYNTHETIC_REPORT_MD.name,
    SYNTHETIC_SMOKE_ZIP.name,
    SCAN_REPORT_JSON.name,
    SCAN_REPORT_MD.name,
}


def _font_candidates() -> List[Path]:
    return [
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    ]


def _resolve_font_path() -> Path | None:
    for path in _font_candidates():
        if path.exists():
            return path
    return None


def _write_text(path: Path, content: str) -> None:
    path.write_text(content.strip() + "\n", encoding="utf-8")


def _write_docx(path: Path, content: str) -> None:
    doc = Document()
    for paragraph in content.strip().split("\n\n"):
        doc.add_paragraph(paragraph.strip())
    doc.save(path)


def _write_pdf(path: Path, content: str, font_path: Path | None) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    if font_path is not None:
        page.insert_font(fontname="custom_font", fontfile=str(font_path))
        font_name = "custom_font"
    else:
        font_name = "helv"

    rect = fitz.Rect(48, 48, 547, 794)
    page.insert_textbox(rect, content.strip(), fontsize=12, fontname=font_name, lineheight=1.4)
    doc.save(path)
    doc.close()


def _wrap_lines(lines: Sequence[str], width: int = 44) -> str:
    wrapped: List[str] = []
    for line in lines:
        if not line.strip():
            wrapped.append("")
            continue
        wrapped.extend(
            textwrap.wrap(
                line,
                width=width,
                break_long_words=False,
                break_on_hyphens=False,
            )
        )
    return "\n".join(wrapped)


def _write_image(path: Path, lines: Sequence[str], font_path: Path | None, image_format: str) -> None:
    text = _wrap_lines(lines)
    font = ImageFont.truetype(str(font_path), 42) if font_path is not None else ImageFont.load_default()

    scratch = Image.new("RGB", (1600, 2000), "white")
    scratch_draw = ImageDraw.Draw(scratch)
    bbox = scratch_draw.multiline_textbbox((0, 0), text, font=font, spacing=16)
    width = max(1280, bbox[2] - bbox[0] + 120)
    height = max(900, bbox[3] - bbox[1] + 120)

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.multiline_text((60, 60), text, fill=(16, 35, 63), font=font, spacing=16)

    if image_format.upper() == "JPEG":
        image.save(path, format="JPEG", quality=90, optimize=True)
    else:
        image.save(path, format="PNG")


def _write_image_pdf(path: Path, image_path: Path) -> None:
    with Image.open(image_path) as image:
        width, height = image.size

    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    page.insert_image(fitz.Rect(0, 0, width, height), stream=image_path.read_bytes())
    doc.save(path)
    doc.close()


def _case(filename: str, expected_hits: Sequence[Tuple[str, str]], **extra: object) -> Dict[str, object]:
    payload = {
        "filename": filename,
        "expected_hits": [{"label": label, "text": text} for label, text in expected_hits],
    }
    payload.update(extra)
    return payload


def build_synthetic_specs() -> List[Dict[str, object]]:
    return [
        _case(
            "01_memo.txt",
            [
                ("PER", "Иванов Иван Иванович"),
                ("ORG", "ООО Навикон"),
                ("EMAIL", "ivanov.i@navicon.ru"),
                ("PHONE", "+7 (495) 123-45-67"),
                ("ACCOUNT", "40702810900000001234"),
                ("INN", "7701234567"),
                ("MONEY", "1 250 000 руб."),
                ("PASSPORT", "45 18 123456"),
            ],
            kind="file",
            writer="text",
            content="""
СЛУЖЕБНАЯ ЗАПИСКА

Ответственный: Иванов Иван Иванович.
Организация: ООО Навикон.
Контактный email: ivanov.i@navicon.ru.
Телефон для связи: +7 (495) 123-45-67.
Расчетный счет: 40702810900000001234.
ИНН контрагента: 7701234567.
Сумма договора: 1 250 000 руб.
Паспорт: 45 18 123456.
""",
        ),
        _case(
            "02_status_report.md",
            [
                ("PER", "Петрова Анна Сергеевна"),
                ("ORG", "ПАО Газпром"),
                ("EMAIL", "petrova.a@gazprom.ru"),
                ("PHONE", "8 926 000 11 22"),
                ("ACCOUNT", "40817810099910004321"),
                ("MONEY", "3 450 000 руб."),
            ],
            kind="file",
            writer="text",
            content="""
# Статус согласования

Исполнитель: Петрова Анна Сергеевна  
Организация: ПАО Газпром  
Email: petrova.a@gazprom.ru  
Телефон: 8 926 000 11 22  
Счет: 40817810099910004321  
Сумма платежа: 3 450 000 руб.
""",
        ),
        _case(
            "03_service_note.docx",
            [
                ("PER", "Смирнов Алексей Владимирович"),
                ("ORG", "ООО Инвест-Строй"),
                ("EMAIL", "smirnov.a@invest.ru"),
                ("PHONE", "+7 903 555 77 66"),
                ("ACCOUNT", "40702810900000007777"),
                ("INN", "7812456789"),
                ("MONEY", "980 000 руб."),
                ("PASSPORT", "45 18 987654"),
            ],
            kind="file",
            writer="docx",
            content="""
Служебная записка

Отправитель: Смирнов Алексей Владимирович.
Организация: ООО Инвест-Строй.
Паспорт: 45 18 987654.
Email: smirnov.a@invest.ru.
Телефон: +7 903 555 77 66.
Расчетный счет: 40702810900000007777.
ИНН: 7812456789.
Сумма: 980 000 руб.
""",
        ),
        _case(
            "04_contract_text.pdf",
            [
                ("PER", "Орлова Мария Ивановна"),
                ("ORG", "АО Север"),
                ("EMAIL", "orlova.m@sever.ru"),
                ("PHONE", "+7 (812) 222-33-44"),
                ("ACCOUNT", "40702810655000000055"),
                ("INN", "7809876543"),
                ("MONEY", "250 000 руб."),
            ],
            kind="file",
            writer="pdf",
            content="""
Договор сопровождения

Куратор: Орлова Мария Ивановна.
Организация: АО Север.
Email: orlova.m@sever.ru.
Телефон: +7 (812) 222-33-44.
Расчетный счет: 40702810655000000055.
ИНН: 7809876543.
Стоимость работ: 250 000 руб.
""",
        ),
        _case(
            "05_scan_note.png",
            [
                ("ORG", "ООО Навикон"),
                ("EMAIL", "audit.scan@navicon.ru"),
                ("PHONE", "+7 (495) 111-22-33"),
                ("ACCOUNT", "40702810900000001111"),
                ("MONEY", "150 000 руб."),
                ("PASSPORT", "45 18 555444"),
            ],
            kind="file",
            writer="image",
            image_format="PNG",
            lines=[
                "СТРОГО КОНФИДЕНЦИАЛЬНО",
                "",
                "ООО Навикон",
                "Email: audit.scan@navicon.ru",
                "Телефон: +7 (495) 111-22-33",
                "Счет: 40702810900000001111",
                "Сумма: 150 000 руб.",
                "Паспорт: 45 18 555444",
            ],
        ),
        _case(
            "06_scan_invoice.jpg",
            [
                ("ORG", "ПАО Газпром"),
                ("EMAIL", "billing.scan@gazprom.ru"),
                ("PHONE", "8 926 777 44 11"),
                ("ACCOUNT", "40702810900000009999"),
                ("MONEY", "510 000 руб."),
            ],
            kind="file",
            writer="image",
            image_format="JPEG",
            lines=[
                "АКТ ОПЛАТЫ",
                "",
                "ПАО Газпром",
                "billing.scan@gazprom.ru",
                "8 926 777 44 11",
                "Р/с 40702810900000009999",
                "Итого: 510 000 руб.",
            ],
        ),
        _case(
            "07_scanned_pdf.pdf",
            [
                ("ORG", "ООО Навикон"),
                ("EMAIL", "audit.scan@navicon.ru"),
                ("PHONE", "+7 (495) 111-22-33"),
                ("ACCOUNT", "40702810900000001111"),
                ("MONEY", "150 000 руб."),
                ("PASSPORT", "45 18 555444"),
            ],
            kind="file",
            writer="image_pdf",
            source_image="05_scan_note.png",
        ),
        _case(
            "08_clean_text.txt",
            [],
            kind="file",
            writer="text",
            content="""
Открытая памятка

В этом документе нет персональных данных, счетов, паспортов и email.
Это тест на лишние срабатывания.
""",
        ),
        {
            "filename": "09_bundle.zip",
            "kind": "zip",
            "members": [
                _case(
                    "bundle_letter.txt",
                    [
                        ("PER", "Соколова Ирина Андреевна"),
                        ("EMAIL", "sokolova.i@navicon.ru"),
                        ("PHONE", "+7 916 555 12 12"),
                    ],
                    writer="text",
                    content="""
Сопроводительное письмо

Контакт: Соколова Ирина Андреевна.
Email: sokolova.i@navicon.ru.
Телефон: +7 916 555 12 12.
""",
                ),
                _case(
                    "bundle_scan.png",
                    [
                        ("ORG", "АО Север"),
                        ("ACCOUNT", "40702810900000005555"),
                        ("MONEY", "275 000 руб."),
                    ],
                    writer="image",
                    image_format="PNG",
                    lines=[
                        "АО Север",
                        "Счет: 40702810900000005555",
                        "Сумма: 275 000 руб.",
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
            raise FileNotFoundError(f"Не найден исходный image-файл для PDF: {source_image}")
        _write_image_pdf(path, source_image)
    else:
        raise ValueError(f"Неизвестный writer: {writer}")

    return path


def generate_synthetic_corpus(target_dir: Path = SYNTHETIC_DIR) -> Dict[str, object]:
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    font_path = _resolve_font_path()
    specs = build_synthetic_specs()
    manifest_cases: List[Dict[str, object]] = []

    for spec in specs:
        if spec["kind"] == "file":
            _materialize_spec(target_dir, spec, font_path)
            manifest_cases.append(
                {
                    "filename": spec["filename"],
                    "kind": "file",
                    "expected_hits": spec["expected_hits"],
                }
            )
            continue

        zip_path = target_dir / str(spec["filename"])
        temp_dir = target_dir / f"_{zip_path.stem}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        member_manifest: List[Dict[str, object]] = []
        with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
            for member in spec["members"]:
                member_path = _materialize_spec(temp_dir, member, font_path)
                archive.write(member_path, arcname=member_path.name)
                member_manifest.append(
                    {
                        "filename": member["filename"],
                        "expected_hits": member["expected_hits"],
                    }
                )

        shutil.rmtree(temp_dir, ignore_errors=True)
        manifest_cases.append(
            {
                "filename": spec["filename"],
                "kind": "zip",
                "members": member_manifest,
            }
        )

    manifest = {
        "categories": sorted(DEFAULT_CATEGORIES),
        "cases": manifest_cases,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _normalize_text(label: str, text: str) -> str:
    raw = text.lower().replace("ё", "е").replace("\n", " ").replace("\t", " ").strip()

    if label in {"PHONE", "ACCOUNT", "PASSPORT", "INN", "MONEY"}:
        raw = re.sub(r"(?<=\d)[OoОо](?=\d)", "0", raw)
        raw = re.sub(r"(?<=\d)[OoОо](?=[\s\-\)])", "0", raw)
        raw = re.sub(r"(?<=[\s\-\(])[OoОо](?=\d)", "0", raw)
        return re.sub(r"\D", "", raw)
    if label == "EMAIL":
        compact = raw.replace(" ", "")
        return re.sub(r"[^a-z0-9@]+", "", compact)
    return re.sub(r"[\W_]+", " ", raw, flags=re.UNICODE).strip()


def _is_match(expected: Dict[str, str], found: Dict[str, object]) -> bool:
    if expected["label"] != found["label"]:
        return False

    expected_norm = _normalize_text(expected["label"], expected["text"])
    found_norm = _normalize_text(str(found["label"]), str(found["text"]))

    if not expected_norm or not found_norm:
        return False

    if expected["label"] in {"PHONE", "ACCOUNT", "PASSPORT", "INN", "MONEY", "EMAIL"}:
        return expected_norm == found_norm

    return (
        expected_norm == found_norm
        or expected_norm in found_norm
        or found_norm in expected_norm
    )


def _compare_case(
    display_name: str,
    expected_hits: Sequence[Dict[str, str]],
    found_hits: Sequence[Dict[str, object]],
    engine: str,
) -> Dict[str, object]:
    unmatched_found = list(found_hits)
    matched_expected: List[Dict[str, str]] = []
    missed_expected: List[Dict[str, str]] = []

    for expected in expected_hits:
        match_index = next(
            (index for index, found in enumerate(unmatched_found) if _is_match(expected, found)),
            None,
        )
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


def _write_markdown(path: Path, content: str) -> None:
    path.write_text(content.strip() + "\n", encoding="utf-8")


def _render_eval_markdown(report: Dict[str, object]) -> str:
    lines = [
        "# Synthetic evaluation report",
        "",
        f"- Files checked: {report['summary']['files_checked']}",
        f"- Expected hits: {report['summary']['expected_hits']}",
        f"- Found hits: {report['summary']['found_hits']}",
        f"- Matched hits: {report['summary']['matched_hits']}",
        f"- Missed hits: {report['summary']['missed_hits']}",
        f"- Unexpected hits: {report['summary']['unexpected_hits']}",
        f"- Recall: {report['summary']['recall_percent']}%",
        f"- Precision: {report['summary']['precision_percent']}%",
        f"- Redaction smoke: {'OK' if report['summary']['redaction_smoke_ok'] else 'FAILED'}",
        "",
        "## By label",
        "",
        "| Label | Expected | Found | Matched | Missed | Unexpected |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    for label, stats in sorted(report["labels"].items()):
        lines.append(
            f"| {label} | {stats['expected']} | {stats['found']} | {stats['matched']} | {stats['missed']} | {stats['unexpected']} |"
        )

    lines.extend(["", "## By file", ""])
    for file_report in report["files"]:
        lines.append(f"### {file_report['file']}")
        lines.append(f"- Engine: {file_report['engine']}")
        lines.append(f"- Recall: {file_report['recall_percent']}%")
        lines.append(f"- Precision: {file_report['precision_percent']}%")
        if file_report["missed"]:
            lines.append("- Missed:")
            for item in file_report["missed"]:
                lines.append(f"  - {item['label']}: {item['text']}")
        if file_report["unexpected"]:
            lines.append("- Unexpected:")
            for item in file_report["unexpected"]:
                lines.append(f"  - {item['label']}: {item['text']}")
        lines.append("")

    return "\n".join(lines)


def evaluate_synthetic_corpus(
    manifest_path: Path = MANIFEST_PATH,
    report_json_path: Path = SYNTHETIC_REPORT_JSON,
    report_md_path: Path = SYNTHETIC_REPORT_MD,
    smoke_zip_path: Path = SYNTHETIC_SMOKE_ZIP,
) -> Dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    categories = set(manifest.get("categories", sorted(DEFAULT_CATEGORIES)))
    corpus_dir = manifest_path.parent

    file_reports: List[Dict[str, object]] = []
    label_stats: Dict[str, Counter] = defaultdict(Counter)
    file_states: List[Dict[str, object]] = []
    file_counter = 0

    for case in manifest["cases"]:
        case_path = corpus_dir / str(case["filename"])
        if case["kind"] == "file":
            file_counter += 1
            analysis, state = analyze_file(
                file_id=f"s{file_counter}",
                filename=case_path.name,
                data=case_path.read_bytes(),
                categories=categories,
                custom_words=[],
                use_ocr=True,
                engine_preference="auto",
            )
            file_states.append(state)
            file_reports.append(
                _compare_case(
                    display_name=case_path.name,
                    expected_hits=case["expected_hits"],
                    found_hits=analysis["hits"],
                    engine=str(analysis.get("engine_used", analysis.get("engine", "unknown"))),
                )
            )
            continue

        expanded = expand_archives([(case_path.name, case_path.read_bytes())])
        expected_members = {
            str(member["filename"]): member["expected_hits"]
            for member in case["members"]
        }

        for member_name, member_bytes in expanded:
            file_counter += 1
            analysis, state = analyze_file(
                file_id=f"s{file_counter}",
                filename=member_name,
                data=member_bytes,
                categories=categories,
                custom_words=[],
                use_ocr=True,
                engine_preference="auto",
            )
            file_states.append(state)
            file_reports.append(
                _compare_case(
                    display_name=f"{case_path.name}::{member_name}",
                    expected_hits=expected_members.get(member_name, []),
                    found_hits=analysis["hits"],
                    engine=str(analysis.get("engine_used", analysis.get("engine", "unknown"))),
                )
            )

    summary = Counter()
    for item in file_reports:
        summary["files_checked"] += 1
        summary["expected_hits"] += item["expected_count"]
        summary["found_hits"] += item["found_count"]
        summary["matched_hits"] += item["matched_count"]
        summary["missed_hits"] += len(item["missed"])
        summary["unexpected_hits"] += len(item["unexpected"])

        all_labels = set(item["expected_by_label"]) | set(item["found_by_label"]) | set(item["matched_by_label"])
        for label in all_labels:
            label_stats[label]["expected"] += item["expected_by_label"].get(label, 0)
            label_stats[label]["found"] += item["found_by_label"].get(label, 0)
            label_stats[label]["matched"] += item["matched_by_label"].get(label, 0)

    for label, stats in label_stats.items():
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
        selected = {
            str(item["file_id"]): [str(hit["id"]) for hit in item["hits"]]
            for item in file_states
        }
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
            "expected_hits": summary["expected_hits"],
            "found_hits": summary["found_hits"],
            "matched_hits": summary["matched_hits"],
            "missed_hits": summary["missed_hits"],
            "unexpected_hits": summary["unexpected_hits"],
            "recall_percent": recall,
            "precision_percent": precision,
            "redaction_smoke_ok": redaction_smoke_ok,
            "redaction_error": redaction_error,
        },
        "labels": {label: dict(stats) for label, stats in sorted(label_stats.items())},
        "files": file_reports,
    }

    report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(report_md_path, _render_eval_markdown(report))
    return report


def _render_scan_markdown(report: Dict[str, object]) -> str:
    lines = [
        "# Existing docs scan",
        "",
        f"- Files scanned: {report['summary']['files_scanned']}",
        f"- Expanded members: {report['summary']['expanded_members']}",
        f"- Total hits: {report['summary']['total_hits']}",
        "",
        "| File | Engine | Hits | Labels |",
        "| --- | --- | ---: | --- |",
    ]
    for item in report["files"]:
        labels = ", ".join(f"{label}: {count}" for label, count in sorted(item["summary"].items()))
        lines.append(f"| {item['file']} | {item['engine']} | {item['hits']} | {labels or '-'} |")
    return "\n".join(lines)


def scan_existing_folder(
    folder: Path = TEST_DIR,
    report_json_path: Path = SCAN_REPORT_JSON,
    report_md_path: Path = SCAN_REPORT_MD,
) -> Dict[str, object]:
    files_report: List[Dict[str, object]] = []
    summary = Counter()
    file_counter = 0

    supported = {ext for ext in {"pdf", "docx", "txt", "md", "png", "jpg", "jpeg", "zip"}}
    candidates = sorted(folder.iterdir(), key=lambda item: item.name.lower())
    for path in candidates:
        if path.is_dir():
            if path.name == SYNTHETIC_DIR.name:
                continue
            continue

        if path.name in IGNORED_SCAN_NAMES:
            continue

        extension = path.suffix.lower().lstrip(".")
        if extension not in supported:
            continue

        if extension == "zip":
            expanded = expand_archives([(path.name, path.read_bytes())])
            for member_name, member_bytes in expanded:
                file_counter += 1
                analysis, _ = analyze_file(
                    file_id=f"r{file_counter}",
                    filename=member_name,
                    data=member_bytes,
                    categories=DEFAULT_CATEGORIES,
                    custom_words=[],
                    use_ocr=True,
                    engine_preference="auto",
                )
                files_report.append(
                    {
                        "file": f"{path.name}::{member_name}",
                        "engine": str(analysis.get("engine_used", analysis.get("engine", "unknown"))),
                        "hits": len(analysis["hits"]),
                        "summary": analysis.get("summary", {}),
                    }
                )
                summary["expanded_members"] += 1
                summary["total_hits"] += len(analysis["hits"])
            summary["files_scanned"] += 1
            continue

        file_counter += 1
        analysis, _ = analyze_file(
            file_id=f"r{file_counter}",
            filename=path.name,
            data=path.read_bytes(),
            categories=DEFAULT_CATEGORIES,
            custom_words=[],
            use_ocr=True,
            engine_preference="auto",
        )
        files_report.append(
            {
                "file": path.name,
                "engine": str(analysis.get("engine_used", analysis.get("engine", "unknown"))),
                "hits": len(analysis["hits"]),
                "summary": analysis.get("summary", {}),
            }
        )
        summary["files_scanned"] += 1
        summary["total_hits"] += len(analysis["hits"])

    report = {
        "summary": {
            "files_scanned": summary["files_scanned"],
            "expanded_members": summary["expanded_members"],
            "total_hits": summary["total_hits"],
        },
        "files": files_report,
    }
    report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(report_md_path, _render_scan_markdown(report))
    return report


def _print_summary(report: Dict[str, object], title: str) -> None:
    print(f"\n[{title}]")
    for key, value in report["summary"].items():
        print(f"- {key}: {value}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic corpus generator and evaluator for Navicon Sanitizer.")
    parser.add_argument(
        "command",
        choices=["generate", "evaluate", "scan", "full"],
        nargs="?",
        default="full",
    )
    args = parser.parse_args()

    if args.command in {"generate", "full"}:
        generate_synthetic_corpus()
        print(f"Synthetic corpus generated: {SYNTHETIC_DIR}")

    if args.command in {"evaluate", "full"}:
        report = evaluate_synthetic_corpus()
        _print_summary(report, "Synthetic evaluation")

    if args.command in {"scan", "full"}:
        report = scan_existing_folder()
        _print_summary(report, "Existing docs scan")


if __name__ == "__main__":
    main()

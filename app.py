from __future__ import annotations

import json
import os
import re
from typing import Dict, List

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

DEFAULT_BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

CATEGORY_OPTIONS = [
    ("PER", "Full Name", True),
    ("ORG", "Organizations", True),
    ("LOC", "Locations", False),
    ("EMAIL", "Email", True),
    ("PHONE", "Phone Numbers", True),
    ("MONEY", "Amounts", True),
    ("PASSPORT", "Passports", True),
    ("ACCOUNT", "Accounts", True),
    ("INN", "Tax ID", True),
    ("CUSTOM", "Custom Dictionary", False),
]

LABEL_TITLES = {
    "PER": "Full Name",
    "ORG": "Organization",
    "LOC": "Location",
    "EMAIL": "Email",
    "PHONE": "Phone",
    "MONEY": "Amount",
    "PASSPORT": "Passport",
    "ACCOUNT": "Account",
    "INN": "Tax ID",
    "CUSTOM": "Custom",
    "MANUAL": "Manual",
}

ENGINE_OPTIONS = {
    "Automatic": "auto",
    "Natasha (Russian documents)": "natasha",
    "Qwen (LLM)": "qwen",
}

TABLE_COL_DELETE = "Delete"
TABLE_COL_TYPE = "Type"
TABLE_COL_SNIPPET = "Snippet"
TABLE_COL_PAGE = "Page"

LEGACY_TABLE_COLUMNS = {
    "Удалять": TABLE_COL_DELETE,
    "Delete": TABLE_COL_DELETE,
    "Тип": TABLE_COL_TYPE,
    "Type": TABLE_COL_TYPE,
    "Фрагмент": TABLE_COL_SNIPPET,
    "Text": TABLE_COL_SNIPPET,
    "Snippet": TABLE_COL_SNIPPET,
    "Страница": TABLE_COL_PAGE,
    "Page": TABLE_COL_PAGE,
}

VERDICT_TRANSLATIONS = {
    "Нельзя передавать без обезличивания": "Cannot be transferred without redaction",
    "Можно передавать": "Safe to transfer",
    "Cannot transfer without anonymization": "Cannot be transferred without redaction",
    "Cannot be transferred without anonymization": "Cannot be transferred without redaction",
    "Safe to transfer": "Safe to transfer",
}

PREVIEW_TAG_TRANSLATIONS = {
    "ФИО": "Full Name",
    "Организация": "Organization",
    "Локация": "Location",
    "Email": "Email",
    "Телефон": "Phone",
    "Сумма": "Amount",
    "Паспорт": "Passport",
    "Счет": "Account",
    "ИНН": "Tax ID",
    "Словарь": "Custom",
    "Вручную": "Manual",
}


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ink: #10233f;
            --muted: #52637a;
            --paper: #ffffff;
            --panel: #f4f8fd;
            --line: rgba(16, 35, 63, 0.1);
            --accent: #0f62fe;
            --accent-2: #0f766e;
            --accent-3: #1d4ed8;
            --shadow: 0 18px 40px rgba(99, 122, 155, 0.16);
        }

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(15, 98, 254, 0.12), transparent 30%),
                radial-gradient(circle at top right, rgba(15, 118, 110, 0.1), transparent 24%),
                linear-gradient(180deg, #f7faff 0%, #eef5ff 48%, #f8fbff 100%);
            color: var(--ink);
            font-family: "Segoe UI", "Aptos", sans-serif;
        }

        header[data-testid="stHeader"] {
            background: transparent;
            border: 0;
        }

        [data-testid="stToolbar"] {
            background: transparent;
        }

        [data-testid="stToolbar"] > div {
            background: transparent !important;
        }

        [data-testid="stToolbarActions"] {
            display: none;
        }

        header [data-testid="stBaseButton-headerNoPadding"] {
            position: fixed;
            top: 0.75rem;
            left: -0.95rem;
            z-index: 1000;
            transition: transform 0.18s ease, opacity 0.18s ease, left 0.18s ease;
            border-radius: 14px;
            background: rgba(255, 255, 255, 0.94);
            border: 1px solid rgba(15, 98, 254, 0.14);
            color: var(--accent);
            box-shadow: 0 10px 24px rgba(16, 35, 63, 0.08);
            opacity: 0.2;
        }

        header [data-testid="stBaseButton-headerNoPadding"]:hover {
            border-color: rgba(15, 98, 254, 0.26);
            background: rgba(255, 255, 255, 0.98);
            transform: translateX(0.7rem);
            opacity: 1;
        }

        .stAppDeployButton,
        #MainMenu,
        [data-testid="stDecoration"] {
            display: none;
        }

        .block-container {
            padding-top: 1.1rem;
            padding-bottom: 3rem;
        }

        h1, h2, h3 {
            font-family: "Segoe UI Semibold", "Aptos Display", "Segoe UI", sans-serif;
            color: var(--ink);
            letter-spacing: 0.01em;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #f8fbff 0%, #eef4fc 100%);
            border-right: 1px solid rgba(15, 98, 254, 0.08);
        }

        .hero {
            padding: 1.5rem 1.5rem 1.25rem 1.5rem;
            border-radius: 28px;
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.98), rgba(244, 248, 253, 0.98)),
                linear-gradient(120deg, rgba(15, 98, 254, 0.07), rgba(15, 118, 110, 0.06));
            border: 1px solid rgba(15, 98, 254, 0.09);
            box-shadow: var(--shadow);
            margin-bottom: 1.25rem;
            overflow: hidden;
        }

        .hero__brand {
            display: flex;
            align-items: center;
            gap: 0.8rem;
            margin-bottom: 1rem;
        }

        .hero__mark {
            width: 2.5rem;
            height: 2.5rem;
            border-radius: 16px;
            background: linear-gradient(135deg, #0f62fe 0%, #1d4ed8 100%);
            color: #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.15rem;
            font-weight: 800;
            box-shadow: 0 14px 32px rgba(15, 98, 254, 0.22);
        }

        .hero__brand-copy {
            display: flex;
            flex-direction: column;
            gap: 0.12rem;
        }

        .hero__brand-title {
            font-size: 0.95rem;
            font-weight: 700;
            color: var(--ink);
        }

        .hero__brand-subtitle {
            font-size: 0.82rem;
            color: var(--muted);
            letter-spacing: 0.02em;
        }

        .hero__eyebrow {
            display: inline-block;
            padding: 0.35rem 0.7rem;
            border-radius: 999px;
            background: rgba(15, 98, 254, 0.1);
            color: var(--accent);
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 0.9rem;
        }

        .hero__title {
            font-size: 2.3rem;
            line-height: 1.02;
            margin: 0 0 0.45rem 0;
        }

        .hero__lead {
            font-size: 1.02rem;
            line-height: 1.55;
            color: var(--muted);
            max-width: 56rem;
            margin-bottom: 1rem;
        }

        .hero__grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.9rem;
            margin-top: 1rem;
        }

        .hero__card {
            padding: 1rem;
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid rgba(16, 35, 63, 0.08);
        }

        .hero__card strong {
            display: block;
            margin-bottom: 0.3rem;
            color: var(--ink);
        }

        .hero__card span {
            color: var(--muted);
            font-size: 0.92rem;
            line-height: 1.45;
        }

        .summary-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.85rem;
            margin: 0.5rem 0 1.15rem 0;
        }

        .summary-card {
            padding: 1rem 1.05rem;
            border-radius: 20px;
            background: rgba(255, 255, 255, 0.92);
            border: 1px solid var(--line);
            box-shadow: 0 10px 24px rgba(16, 35, 63, 0.06);
        }

        .summary-card__label {
            color: var(--muted);
            font-size: 0.82rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 0.4rem;
        }

        .summary-card__value {
            color: var(--ink);
            font-size: 1.6rem;
            font-weight: 800;
            line-height: 1;
        }

        .section-title {
            margin: 1.2rem 0 0.35rem 0;
            font-size: 1.2rem;
            font-weight: 800;
            color: var(--ink);
        }

        .section-copy {
            color: var(--muted);
            margin-bottom: 0.8rem;
        }

        .preview-surface,
        .preview-page {
            padding: 1rem 1.05rem;
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.95);
            border: 1px solid var(--line);
            line-height: 1.72;
            font-size: 0.98rem;
            color: #1e293b;
            box-shadow: 0 12px 28px rgba(16, 35, 63, 0.05);
        }

        .preview-page {
            margin-bottom: 0.9rem;
        }

        .preview-scroll {
            max-height: 70vh;
            overflow-y: auto;
            padding-right: 0.35rem;
        }

        .preview-page__title {
            font-size: 0.84rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--accent-3);
            margin-bottom: 0.7rem;
        }

        .preview-hit {
            display: inline;
            border: 1px solid transparent;
            border-radius: 10px;
            padding: 0.04rem 0.22rem 0.08rem 0.22rem;
            margin: 0 0.08rem;
            box-decoration-break: clone;
            -webkit-box-decoration-break: clone;
        }

        .preview-hit__tag {
            display: inline-block;
            margin-right: 0.34rem;
            padding: 0.05rem 0.32rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.7);
            font-size: 0.68rem;
            font-weight: 800;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            vertical-align: middle;
        }

        .preview-empty {
            color: var(--muted);
            padding: 0.4rem 0;
        }

        .metric-pills {
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
            margin: 0.4rem 0 0.9rem 0;
        }

        .metric-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.45rem 0.78rem;
            border-radius: 999px;
            background: rgba(15, 98, 254, 0.06);
            border: 1px solid rgba(15, 98, 254, 0.1);
            color: var(--ink);
            font-size: 0.9rem;
        }

        .metric-pill strong {
            color: var(--accent);
        }

        .footer-note {
            margin-top: 2rem;
            padding: 1rem 1.2rem;
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.84);
            border: 1px solid rgba(16, 35, 63, 0.07);
            color: var(--muted);
            font-size: 0.92rem;
        }

        [data-testid="stFileUploaderDropzone"] {
            background: rgba(255, 255, 255, 0.72);
            border: 1px dashed rgba(15, 98, 254, 0.28);
            border-radius: 20px;
        }

        .stButton > button {
            border-radius: 14px;
            transition: all 0.18s ease;
        }

        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #0f62fe 0%, #1d4ed8 100%);
            border: 1px solid #0f62fe;
            color: #ffffff;
            box-shadow: 0 10px 24px rgba(15, 98, 254, 0.2);
        }

        .stButton > button[kind="primary"]:hover {
            background: linear-gradient(135deg, #0b57ea 0%, #1b48c9 100%);
            border-color: #0b57ea;
        }

        .stButton > button[kind="secondary"] {
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid rgba(15, 98, 254, 0.16);
            color: var(--ink);
        }

        .stButton > button[kind="secondary"]:hover {
            border-color: rgba(15, 98, 254, 0.3);
            color: var(--accent);
        }

        .stDownloadButton > button {
            border-radius: 14px;
            background: linear-gradient(135deg, #0f62fe 0%, #1d4ed8 100%);
            border: 1px solid #0f62fe;
            color: #ffffff;
            box-shadow: 0 10px 24px rgba(15, 98, 254, 0.2);
        }

        [data-testid="stDataEditor"] {
            border-radius: 18px;
            overflow: hidden;
            border: 1px solid rgba(16, 35, 63, 0.08);
        }

        @media (max-width: 960px) {
            .hero__grid,
            .summary-grid {
                grid-template-columns: 1fr;
            }

            .hero__title {
                font-size: 1.7rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _request_health(backend_url: str) -> Dict[str, object]:
    try:
        response = requests.get(f"{backend_url}/health", timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as error:
        return {"status": "error", "detail": str(error)}


def _normalize_table_columns(table: pd.DataFrame | None) -> pd.DataFrame | None:
    if table is None:
        return None
    normalized = table.rename(columns=LEGACY_TABLE_COLUMNS).copy()
    for column in [TABLE_COL_DELETE, TABLE_COL_TYPE, TABLE_COL_SNIPPET, TABLE_COL_PAGE]:
        if column not in normalized.columns:
            normalized[column] = True if column == TABLE_COL_DELETE else ""
    return normalized[[TABLE_COL_DELETE, TABLE_COL_TYPE, TABLE_COL_SNIPPET, TABLE_COL_PAGE]]


def _translate_verdict(verdict: str) -> str:
    clean = str(verdict or "").strip()
    if not clean:
        return clean
    return VERDICT_TRANSLATIONS.get(clean, clean)


def _verdict_is_blocked(verdict: str) -> bool:
    clean = str(verdict or "").strip()
    return clean in {
        "Нельзя передавать без обезличивания",
        "Cannot transfer without anonymization",
        "Cannot be transferred without anonymization",
        "Cannot be transferred without redaction",
    }


def _translate_backend_preview_html(value: str) -> str:
    if not value:
        return value

    translated = str(value)

    translated = re.sub(
        r'(<span class="preview-hit__tag">)([^<]+)(</span>)',
        lambda match: (
            f"{match.group(1)}"
            f"{PREVIEW_TAG_TRANSLATIONS.get(match.group(2).strip(), match.group(2).strip())}"
            f"{match.group(3)}"
        ),
        translated,
    )
    translated = re.sub(
        r'(<div class="preview-page__title">)\s*Страница\s+(\d+)(</div>)',
        r"\1Page \2\3",
        translated,
    )
    translated = translated.replace("Пустой фрагмент", "Empty snippet")
    translated = translated.replace("Предпросмотр недоступен", "Preview not available")
    return translated


def _collapse_sidebar_on_load() -> None:
    components.html(
        """
        <script>
        (function () {
            const root = window.parent;
            if (!root || !root.document || !root.sessionStorage) {
                return;
            }

            const storageKey = "navicon_sidebar_autocollapsed_v1";
            if (root.sessionStorage.getItem(storageKey)) {
                return;
            }

            function collapseSidebar() {
                const doc = root.document;
                const sidebar = doc.querySelector('section[data-testid="stSidebar"]');
                const toggle = doc.querySelector('header [data-testid="stBaseButton-headerNoPadding"]');
                if (!sidebar || !toggle) {
                    return false;
                }

                const ariaExpanded = sidebar.getAttribute("aria-expanded");
                const isExpanded = ariaExpanded === "true" || (ariaExpanded === null && sidebar.offsetWidth > 80);
                if (isExpanded) {
                    toggle.click();
                }

                root.sessionStorage.setItem(storageKey, "1");
                return true;
            }

            if (collapseSidebar()) {
                return;
            }

            let attempts = 0;
            const timer = root.setInterval(function () {
                attempts += 1;
                if (collapseSidebar() || attempts > 40) {
                    root.clearInterval(timer);
                }
            }, 150);
        })();
        </script>
        """,
        height=0,
    )


def _build_analysis_payload(files, categories: List[str], custom_words: str, use_ocr: bool, engine: str):
    upload_payload = []
    for file in files:
        upload_payload.append(("files", (file.name, file.getvalue(), "application/octet-stream")))

    form_data = {
        "categories_json": json.dumps(categories, ensure_ascii=False),
        "custom_words": custom_words,
        "use_ocr": str(bool(use_ocr)).lower(),
        "engine": engine,
    }
    return upload_payload, form_data


def _init_tables(analysis_response: Dict[str, object]) -> None:
    analysis_id = analysis_response["analysis_id"]
    for file_item in analysis_response["files"]:
        table_key = f"table_{analysis_id}_{file_item['file_id']}"
        ids_key = f"ids_{analysis_id}_{file_item['file_id']}"
        manual_key = f"manual_terms_{analysis_id}_{file_item['file_id']}"
        rows = []
        hit_ids = []
        for hit in file_item["hits"]:
            rows.append(
                {
                    TABLE_COL_DELETE: True,
                    TABLE_COL_TYPE: LABEL_TITLES.get(hit["label"], hit["label"]),
                    TABLE_COL_SNIPPET: hit["text"],
                    TABLE_COL_PAGE: hit.get("page") if hit.get("page") is not None else "-",
                }
            )
            hit_ids.append(hit["id"])

        st.session_state[table_key] = _normalize_table_columns(pd.DataFrame(rows))
        st.session_state[ids_key] = hit_ids
        st.session_state.setdefault(manual_key, "")


def _collect_selected_hits(analysis_response: Dict[str, object]) -> Dict[str, List[str]]:
    selected: Dict[str, List[str]] = {}
    analysis_id = analysis_response["analysis_id"]

    for file_item in analysis_response["files"]:
        table_key = f"table_{analysis_id}_{file_item['file_id']}"
        ids_key = f"ids_{analysis_id}_{file_item['file_id']}"
        table = _normalize_table_columns(st.session_state.get(table_key))
        hit_ids = st.session_state.get(ids_key, [])

        if table is None or table.empty:
            selected[file_item["file_id"]] = []
            continue

        chosen = [hit_id for hit_id, checked in zip(hit_ids, table[TABLE_COL_DELETE].tolist()) if bool(checked)]
        selected[file_item["file_id"]] = chosen

    return selected


def _collect_manual_terms(analysis_response: Dict[str, object]) -> Dict[str, List[str]]:
    manual_terms: Dict[str, List[str]] = {}
    analysis_id = analysis_response["analysis_id"]

    for file_item in analysis_response["files"]:
        manual_key = f"manual_terms_{analysis_id}_{file_item['file_id']}"
        raw = str(st.session_state.get(manual_key, ""))
        manual_terms[file_item["file_id"]] = [line.strip() for line in raw.splitlines() if line.strip()]

    return manual_terms


def _render_pdf_preview(analysis_id: str, file_item: Dict[str, object]) -> None:
    preview_pages = list(file_item.get("preview_pages") or [])
    page_count = int(file_item.get("page_count") or len(preview_pages) or 1)

    if not preview_pages:
        if file_item.get("preview_html"):
            st.markdown(_translate_backend_preview_html(file_item["preview_html"]), unsafe_allow_html=True)
        else:
            st.info("Preview not available")
        return

    option_map = {"First page": 1}
    if page_count >= 3:
        option_map["First 3 pages"] = 3
    if page_count >= 5:
        option_map["First 5 pages"] = 5
    if page_count > 1:
        option_map["Whole document"] = None

    options = list(option_map.keys())
    preview_choice = st.radio(
        "Document preview",
        options=options,
        index=0,
        horizontal=True,
        key=f"preview_pages_{analysis_id}_{file_item['file_id']}",
    )

    selected_limit = option_map[preview_choice]
    visible_pages = preview_pages if selected_limit is None else preview_pages[:selected_limit]

    if selected_limit is None:
        st.caption(f"Showing the full available preview: {len(visible_pages)} pages.")
    else:
        st.caption(f"Showing {min(selected_limit, len(visible_pages))} of {page_count} pages.")

    st.markdown(
        f"<div class='preview-scroll'>{''.join(_translate_backend_preview_html(str(item.get('html', ''))) for item in visible_pages)}</div>",
        unsafe_allow_html=True,
    )


def _render_hero() -> None:
    st.markdown(
        """
        <section class="hero">
            <div class="hero__brand">
                <div class="hero__mark">N</div>
                <div class="hero__brand-copy">
                    <div class="hero__brand-title">Navicon Sanitizer 3.0</div>
                    <div class="hero__brand-subtitle">Local document preparation for safe data sharing</div>
                </div>
            </div>
            <div class="hero__eyebrow">Navicon AI Sprint 2026</div>
            <h1 class="hero__title">Analyze, confirm, and redact in one workspace</h1>
            <div class="hero__lead">
                Local service for document sanitization before external sharing.<br>
                First we identify sensitive content, then a user confirms the result, and only after that
                we build a safe version of the file.
            </div>
            <div class="hero__grid">
                <div class="hero__card">
                    <strong>Human in the loop</strong>
                    <span>No blind deletion. Every redaction candidate is reviewed by a user before export.</span>
                </div>
                <div class="hero__card">
                    <strong>Local processing</strong>
                    <span>Documents stay inside the local environment and do not need to be sent to public cloud services.</span>
                </div>
                <div class="hero__card">
                    <strong>Multiple file formats</strong>
                    <span>PDF, Word, PNG, JPG, ZIP, plus Markdown export and a final report of all applied changes.</span>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_summary_cards(analysis: Dict[str, object]) -> None:
    files_count = analysis.get("total_files", 0)
    hits_count = analysis.get("total_hits", 0)
    blocked = sum(
        1
        for file_item in analysis["files"]
        if _verdict_is_blocked(str(file_item.get("verdict", "")))
    )
    approved = max(files_count - blocked, 0)

    st.markdown(
        f"""
        <div class="summary-grid">
            <div class="summary-card">
                <div class="summary-card__label">Files</div>
                <div class="summary-card__value">{files_count}</div>
            </div>
            <div class="summary-card">
                <div class="summary-card__label">Matches found</div>
                <div class="summary-card__value">{hits_count}</div>
            </div>
            <div class="summary-card">
                <div class="summary-card__label">Redaction required</div>
                <div class="summary-card__value">{blocked}</div>
            </div>
            <div class="summary-card">
                <div class="summary-card__label">Ready to share</div>
                <div class="summary-card__value">{approved}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_metric_pills(summary: Dict[str, int]) -> None:
    if not summary:
        st.markdown("<div class='metric-pills'><span class='metric-pill'>No matches found</span></div>", unsafe_allow_html=True)
        return

    pills = []
    for label, value in summary.items():
        pills.append(
            f"<span class='metric-pill'><strong>{value}</strong> {LABEL_TITLES.get(label, label)}</span>"
        )

    st.markdown(f"<div class='metric-pills'>{''.join(pills)}</div>", unsafe_allow_html=True)


def _set_all_rows(analysis_id: str, file_id: str, value: bool) -> None:
    table_key = f"table_{analysis_id}_{file_id}"
    table = _normalize_table_columns(st.session_state.get(table_key))
    if table is None or table.empty:
        return
    table[TABLE_COL_DELETE] = value
    st.session_state[table_key] = table


def _render_file_block(analysis_id: str, file_item: Dict[str, object]) -> None:
    verdict = _translate_verdict(str(file_item.get("verdict", "")))

    st.markdown(f"<div class='section-title'>{file_item['filename']}</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-copy'>Preview highlights show redaction candidates before the final confirmation step.</div>",
        unsafe_allow_html=True,
    )
    _render_metric_pills(file_item.get("summary", {}))

    if verdict:
        if _verdict_is_blocked(verdict):
            st.warning(f"Security verdict: {verdict}")
        else:
            st.success(f"Security verdict: {verdict}")

    preview_tab, table_tab = st.tabs(["Text preview", "Matches list"])
    with preview_tab:
        if str(file_item.get("extension", "")) == "pdf":
            _render_pdf_preview(analysis_id, file_item)
        elif file_item.get("preview_html"):
            st.markdown(_translate_backend_preview_html(file_item["preview_html"]), unsafe_allow_html=True)
        elif file_item.get("preview"):
            st.text(file_item["preview"])
        else:
            st.info("Preview not available")

        manual_key = f"manual_terms_{analysis_id}_{file_item['file_id']}"
        with st.expander("Manual redaction", expanded=False):
            st.caption(
                "If the system missed something, add phrases below one per line. "
                "They will be additionally redacted when the archive is generated."
            )
            st.text_area(
                "Manual redaction phrases",
                key=manual_key,
                placeholder="For example:\nDE44500105175407324931\nContoso Ltd\njane.doe@contoso.com",
                label_visibility="collapsed",
                height=120,
            )
            manual_count = len([line for line in str(st.session_state.get(manual_key, "")).splitlines() if line.strip()])
            if manual_count:
                st.caption(f"Added manually: {manual_count}")

    with table_tab:
        table_key = f"table_{analysis_id}_{file_item['file_id']}"
        table = _normalize_table_columns(st.session_state.get(table_key, pd.DataFrame()))

        if table.empty:
            st.info("No redaction candidates in this file")
            return

        col_a, col_b, col_c = st.columns([1, 1, 3])
        with col_a:
            if st.button("Select all", key=f"select_all_{analysis_id}_{file_item['file_id']}", use_container_width=True):
                _set_all_rows(analysis_id, file_item["file_id"], True)
                st.rerun()
        with col_b:
            if st.button("Clear all", key=f"clear_all_{analysis_id}_{file_item['file_id']}", use_container_width=True):
                _set_all_rows(analysis_id, file_item["file_id"], False)
                st.rerun()
        with col_c:
            st.caption("The simpler the table, the faster a user can validate the result during a demo or daily work.")

        edited = st.data_editor(
            table,
            key=f"editor_{analysis_id}_{file_item['file_id']}",
            hide_index=True,
            use_container_width=True,
            column_config={
                TABLE_COL_DELETE: st.column_config.CheckboxColumn(
                    TABLE_COL_DELETE,
                    help="Clear the checkbox if this fragment may remain visible",
                    default=True,
                ),
                TABLE_COL_TYPE: st.column_config.TextColumn(TABLE_COL_TYPE, disabled=True),
                TABLE_COL_SNIPPET: st.column_config.TextColumn(TABLE_COL_SNIPPET, disabled=True, width="large"),
                TABLE_COL_PAGE: st.column_config.TextColumn(TABLE_COL_PAGE, disabled=True, width="small"),
            },
            disabled=[TABLE_COL_TYPE, TABLE_COL_SNIPPET, TABLE_COL_PAGE],
        )
        st.session_state[table_key] = _normalize_table_columns(edited)


def main() -> None:
    st.set_page_config(
        page_title="Navicon Sanitizer 3.0",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _inject_styles()
    _collapse_sidebar_on_load()

    if "backend_url" not in st.session_state:
        st.session_state["backend_url"] = DEFAULT_BACKEND_URL
    if "engine_override" not in st.session_state:
        st.session_state["engine_override"] = "auto"

    _render_hero()

    with st.sidebar:
        st.header("Processing options")

        selected_categories: List[str] = []
        for key, label, default in CATEGORY_OPTIONS:
            value = st.checkbox(label, value=default)
            if value:
                selected_categories.append(key)

        custom_words = st.text_area("Custom dictionary", placeholder="One phrase per line")
        if custom_words.strip() and "CUSTOM" not in selected_categories:
            selected_categories.append("CUSTOM")

        st.divider()
        st.subheader("Output")
        use_ocr = st.toggle("Search in scans and images", value=True)
        include_original = st.checkbox("Keep original file format", value=True)
        include_markdown = st.checkbox("Add Markdown", value=True)
        include_docx = st.checkbox("Add Word (.docx)", value=True)
        redaction_style = st.selectbox(
            "Text style in md/docx",
            options=["black", "tag"],
            format_func=lambda item: "Black boxes" if item == "black" else "Category tags",
            index=0,
        )

        st.divider()
        with st.expander("Expert mode", expanded=False):
            backend_url = st.text_input("Backend URL", value=st.session_state["backend_url"])
            st.session_state["backend_url"] = backend_url

            current_engine_label = next(
                (label for label, value in ENGINE_OPTIONS.items() if value == st.session_state["engine_override"]),
                "Automatic",
            )
            engine_label = st.selectbox(
                "Engine mode",
                options=list(ENGINE_OPTIONS.keys()),
                index=list(ENGINE_OPTIONS.keys()).index(current_engine_label),
            )
            st.session_state["engine_override"] = ENGINE_OPTIONS[engine_label]

            health = _request_health(backend_url)
            if health.get("status") == "ok":
                qwen_configured = bool(health.get("qwen_configured"))
                qwen_state = "configured" if qwen_configured else "disabled"
                st.caption(f"Local backend is reachable. Qwen: {qwen_state}.")
                if st.session_state["engine_override"] == "qwen" and not qwen_configured:
                    st.caption("Qwen is selected, but the backend is not configured. Fallback mode will be used instead of LLM processing.")
            else:
                st.caption("Backend is not reachable yet. Restart run.bat if required.")

    backend_url = st.session_state["backend_url"]
    engine = st.session_state.get("engine_override", "auto")

    st.markdown("<div class='section-title'>Document upload</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-copy'>Supported input: PDF, Word, text files, images, and ZIP archives.</div>",
        unsafe_allow_html=True,
    )
    uploaded_files = st.file_uploader(
        "Upload documents",
        type=["pdf", "docx", "txt", "md", "png", "jpg", "jpeg", "zip"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    col_analyze, col_reset = st.columns([2, 1])
    with col_analyze:
        analyze_clicked = st.button("1. Analyze documents", use_container_width=True, type="primary")
    with col_reset:
        reset_clicked = st.button("Reset session", use_container_width=True)

    if reset_clicked:
        for key in list(st.session_state.keys()):
            if key.startswith("table_") or key.startswith("ids_") or key.startswith("editor_") or key.startswith("manual_terms_") or key.startswith("preview_pages_"):
                st.session_state.pop(key, None)
        for key in ["analysis", "download_bytes", "download_name", "download_ready"]:
            st.session_state.pop(key, None)
        st.rerun()

    if analyze_clicked:
        if not uploaded_files:
            st.warning("Upload at least one file first.")
        elif not selected_categories:
            st.warning("Select at least one category.")
        else:
            files_payload, form_data = _build_analysis_payload(
                uploaded_files,
                selected_categories,
                custom_words,
                use_ocr,
                engine,
            )

            progress = st.progress(8, text="Validating files and starting analysis...")
            try:
                response = requests.post(
                    f"{backend_url}/analyze",
                    files=files_payload,
                    data=form_data,
                    timeout=1200,
                )
                progress.progress(72, text="Collecting redaction candidates...")
                response.raise_for_status()
                analysis = response.json()
                progress.progress(100, text="Analysis completed.")
            except Exception as error:
                progress.empty()
                st.error(f"Analysis error: {error}")
                return

            st.session_state["analysis"] = analysis
            st.session_state["download_ready"] = False
            _init_tables(analysis)
            progress.empty()

    analysis = st.session_state.get("analysis")
    if not analysis:
        return

    _render_summary_cards(analysis)

    for file_item in analysis["files"]:
        _render_file_block(analysis["analysis_id"], file_item)
        st.divider()

    st.markdown("<div class='section-title'>Final step</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-copy'>After confirmation, the app will build an archive with sanitized files and a report.</div>",
        unsafe_allow_html=True,
    )

    if st.button("2. Confirm and redact", use_container_width=True, type="primary"):
        selected_hits = _collect_selected_hits(analysis)
        manual_terms = _collect_manual_terms(analysis)
        payload = {
            "selected_hit_ids_by_file": selected_hits,
            "manual_terms_by_file": manual_terms,
            "redaction_style": redaction_style,
            "include_original": include_original,
            "include_markdown": include_markdown,
            "include_docx": include_docx,
        }

        progress = st.progress(12, text="Building the safe archive...")
        try:
            response = requests.post(
                f"{backend_url}/redact/{analysis['analysis_id']}",
                json=payload,
                timeout=1200,
            )
            progress.progress(86, text="Packing results and report...")
            response.raise_for_status()
        except Exception as error:
            progress.empty()
            st.error(f"Redaction error: {error}")
            return

        st.session_state["download_bytes"] = response.content
        st.session_state["download_name"] = "sanitized_results.zip"
        st.session_state["download_ready"] = True
        progress.progress(100, text="Archive is ready.")
        progress.empty()

    if st.session_state.get("download_ready"):
        st.download_button(
            "Download sanitized_results.zip",
            data=st.session_state["download_bytes"],
            file_name=st.session_state["download_name"],
            mime="application/zip",
            use_container_width=True,
        )

if __name__ == "__main__":
    main()

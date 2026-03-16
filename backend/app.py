from __future__ import annotations

import json
import time
import uuid
from typing import Dict, List

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

from backend.core import (
    SUPPORTED_EXTENSIONS,
    UnsupportedFileError,
    analyze_file,
    build_redacted_zip,
    expand_archives,
    parse_custom_words,
    qwen_is_configured,
)

if load_dotenv is not None:
    load_dotenv()

ANALYSIS_TTL_SECONDS = 60 * 60 * 6
ANALYSIS_STORE: Dict[str, Dict[str, object]] = {}


class RedactRequest(BaseModel):
    selected_hit_ids_by_file: Dict[str, List[str]] = Field(default_factory=dict)
    manual_terms_by_file: Dict[str, List[str]] = Field(default_factory=dict)
    redaction_style: str = Field(default="black")
    include_original: bool = True
    include_markdown: bool = True
    include_docx: bool = True


app = FastAPI(title="Navicon Sanitizer API", version="3.0.0")


def cleanup_store() -> None:
    now = time.time()
    stale_keys = [
        key
        for key, value in ANALYSIS_STORE.items()
        if now - float(value.get("created_at", now)) > ANALYSIS_TTL_SECONDS
    ]
    for key in stale_keys:
        ANALYSIS_STORE.pop(key, None)


def parse_categories(raw: str) -> List[str]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail=f"categories_json должен быть JSON-списком: {error}")

    if not isinstance(parsed, list):
        raise HTTPException(status_code=400, detail="categories_json должен быть JSON-списком")

    categories: List[str] = []
    for item in parsed:
        value = str(item).strip().upper()
        if value:
            categories.append(value)

    if not categories:
        raise HTTPException(status_code=400, detail="Нужно выбрать хотя бы одну категорию")

    return sorted(set(categories))


@app.get("/health")
def health() -> Dict[str, object]:
    return {
        "status": "ok",
        "qwen_configured": qwen_is_configured(),
        "supported_extensions": sorted(ext for ext in SUPPORTED_EXTENSIONS if ext != "zip"),
    }


@app.post("/analyze")
async def analyze(
    files: List[UploadFile] = File(...),
    categories_json: str = Form(...),
    custom_words: str = Form(default=""),
    use_ocr: bool = Form(default=True),
    engine: str = Form(default="auto"),
):
    cleanup_store()
    categories = parse_categories(categories_json)
    custom_terms = parse_custom_words(custom_words)

    uploaded: List[tuple[str, bytes]] = []
    for item in files:
        filename = item.filename or "file"
        payload = await item.read()
        uploaded.append((filename, payload))

    expanded = expand_archives(uploaded)
    if not expanded:
        raise HTTPException(status_code=400, detail="Нет файлов для обработки")

    analysis_id = uuid.uuid4().hex

    api_files: List[Dict[str, object]] = []
    state_files: List[Dict[str, object]] = []

    for index, (filename, payload) in enumerate(expanded, start=1):
        file_id = f"f{index}"
        try:
            analysis, state = analyze_file(
                file_id=file_id,
                filename=filename,
                data=payload,
                categories=set(categories),
                custom_words=custom_terms,
                use_ocr=use_ocr,
                engine_preference=engine,
            )
        except UnsupportedFileError as error:
            raise HTTPException(status_code=400, detail=str(error))
        except Exception as error:
            raise HTTPException(status_code=500, detail=f"Ошибка анализа файла {filename}: {error}")

        api_files.append(analysis)
        state_files.append(state)

    ANALYSIS_STORE[analysis_id] = {
        "created_at": time.time(),
        "categories": categories,
        "custom_words": custom_terms,
        "use_ocr": use_ocr,
        "engine": engine,
        "files": state_files,
    }

    response = {
        "analysis_id": analysis_id,
        "files": api_files,
        "total_files": len(api_files),
        "total_hits": sum(len(file["hits"]) for file in api_files),
    }
    return JSONResponse(response)


@app.post("/redact/{analysis_id}")
def redact(analysis_id: str, request: RedactRequest):
    cleanup_store()
    state = ANALYSIS_STORE.get(analysis_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Сессия анализа не найдена или устарела")

    if request.redaction_style not in {"black", "tag"}:
        raise HTTPException(status_code=400, detail="Допустимые стили: black, tag")

    try:
        archive_bytes, report = build_redacted_zip(
            analysis_state=state,
            selected_hit_ids_by_file=request.selected_hit_ids_by_file,
            manual_terms_by_file=request.manual_terms_by_file,
            redaction_style=request.redaction_style,
            include_original=request.include_original,
            include_markdown=request.include_markdown,
            include_docx=request.include_docx,
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Ошибка при вычеркивании: {error}")

    headers = {
        "Content-Disposition": 'attachment; filename="sanitized_results.zip"',
        "X-Redaction-Files": str(len(report.keys())),
    }
    return StreamingResponse(iter([archive_bytes]), media_type="application/zip", headers=headers)

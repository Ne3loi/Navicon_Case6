# Navicon Case 6 - Sanitizer 3.0

Прототип для кейса 6: локальное обезличивание документов перед отправкой за периметр.

## Что реализовано

- Двухшаговый UX: `Анализ -> Подтверждение -> Вычеркивание`.
- Разделенная архитектура:
  - `backend` (FastAPI) - анализ, OCR, вычеркивание, генерация архива.
  - `frontend` (Streamlit) - интерфейс загрузки, валидации и скачивания.
- Поддержка форматов: `PDF`, `DOCX`, `TXT`, `MD`, `PNG/JPG/JPEG`, `ZIP`.
- Отчет по найденным сущностям с указанием страницы и метода (`TextLayer`/`OCR`).
- Вердикт ИБ на шаге анализа: `Можно/Нельзя передавать`.
- Выгрузка результатов: исходный очищенный формат + `Markdown` + `Word` + `report.json` + `report.md`.
- Локальная работа (без облака по умолчанию).
- Автовыбор движка NER:
  - русский текст -> `Natasha`
  - англоязычный -> `Qwen` (если настроен) или `regex`

## Быстрый запуск (Windows)

```bat
run.bat
```

Скрипт запускает `run_local.py`, который:

- проверяет/поднимает backend и ждет `/health`,
- по умолчанию поднимает **свежий** backend (чтобы не цепляться к старому процессу с предыдущей версией кода),
- автоматически выбирает свободный порт для frontend (если `8501` занят),
- передает корректный `BACKEND_URL` во frontend,
- открывает браузер автоматически.

Если backend не поднялся, смотри лог: `backend.log`.

Опционально можно переиспользовать уже запущенный backend:

```bat
.\venv\Scripts\python.exe -u run_local.py --reuse-existing-backend
```

## Docker Compose

Сначала создай `.env` в корне проекта на основе `.env.example`.
Для Qwen backend-контейнер читает `QWEN_API_BASE`, `QWEN_MODEL`, `QWEN_API_KEY` именно из `.env`.

```bash
docker compose up --build
```

Сервисы:

- Frontend: `http://localhost:8501`
- Backend API: `http://localhost:8000`
- Nginx HTTPS: `https://localhost` (если сгенерированы сертификаты)

## Nginx + Self-Signed SSL (Ubuntu VM)

1. Сгенерировать сертификат:

```bash
chmod +x scripts/generate-self-signed.sh
./scripts/generate-self-signed.sh <DOMAIN_OR_IP> <IP_SAN>
```

Пример:

```bash
./scripts/generate-self-signed.sh 10.10.10.20 10.10.10.20
```

2. Запустить контейнеры:

```bash
docker compose up -d --build
```

3. Открыть:

```text
https://<DOMAIN_OR_IP>
```

### Быстрый деплой одной командой на Ubuntu

```bash
chmod +x scripts/deploy-ubuntu.sh
./scripts/deploy-ubuntu.sh
```

Скрипт сам:

- определит IP VM,
- выпустит self-signed сертификат в `nginx/certs/`,
- поднимет весь стек через `docker compose`.

## Переменные окружения

- `BACKEND_URL` - URL backend для frontend (по умолчанию `http://localhost:8000`)
- `OCR_GPU` - `1/true` для OCR на GPU, иначе CPU
- `QWEN_API_BASE` - base URL OpenAI-совместимого endpoint локальной LLM
- `QWEN_MODEL` - имя модели для Qwen
- `QWEN_API_KEY` - токен (если требуется)

Для Docker Compose backend получает эти переменные из `.env` через `env_file`.

## API

### `POST /analyze`

`multipart/form-data`:

- `files`: один или несколько файлов
- `categories_json`: JSON-массив категорий (`["PER","ORG", ...]`)
- `custom_words`: кастомный словарь (по строкам)
- `use_ocr`: `true/false`
- `engine`: `auto|natasha|qwen|regex`

### `POST /redact/{analysis_id}`

`application/json`:

```json
{
  "selected_hit_ids_by_file": {
    "f1": ["h1", "h2"]
  },
  "redaction_style": "black",
  "include_original": true,
  "include_markdown": true,
  "include_docx": true
}
```

Ответ: zip-архив с результатами.

## Материалы для защиты

- Пошаговый сценарий демо на 15 минут: [docs/DEMO_SCENARIO_15MIN.md](docs/DEMO_SCENARIO_15MIN.md)
- Короткий протокол тестирования и метрик: [docs/TEST_PROTOCOL.md](docs/TEST_PROTOCOL.md)

## Secrets And Local Config

- Шаблон переменных окружения: `.env.example`
- Локальные секреты и сертификаты исключены из репозитория через `.gitignore`

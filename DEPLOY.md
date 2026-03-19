# Деплой и запуск

## Локальный запуск на Windows

Базовый запуск:

```bat
run.bat
```

Что делает лаунчер:

- создает `venv`, если его еще нет
- ставит зависимости из `requirements.txt`
- поднимает backend и ждет `/health`
- выбирает свободный порт для frontend, если `8501` занят
- открывает браузер автоматически

Если нужно переиспользовать уже запущенный backend:

```bat
.\venv\Scripts\python.exe -u run_local.py --reuse-existing-backend
```

Если backend не поднялся, лог лежит в `backend.log`.

## Docker Compose

Перед запуском создай `.env` в корне проекта на основе `.env.example`.

Запуск:

```bash
docker compose up --build
```

Сервисы:

- frontend: `http://localhost:8501`
- backend API: `http://localhost:8000`
- nginx HTTPS: `https://localhost`

## Ubuntu VM + Nginx + self-signed SSL

Сгенерировать сертификат:

```bash
chmod +x scripts/generate-self-signed.sh
./scripts/generate-self-signed.sh <DOMAIN_OR_IP> <IP_SAN>
```

Пример:

```bash
./scripts/generate-self-signed.sh 10.10.10.20 10.10.10.20
```

Поднять стек:

```bash
docker compose up -d --build
```

Открыть:

```text
https://<DOMAIN_OR_IP>
```

Быстрый деплой одной командой:

```bash
chmod +x scripts/deploy-ubuntu.sh
./scripts/deploy-ubuntu.sh
```

## Переменные окружения

- `BACKEND_URL` — URL backend для frontend
- `OCR_GPU` — `1/true` для OCR на GPU, иначе CPU
- `QWEN_API_BASE` — base URL OpenAI-совместимого endpoint
- `QWEN_MODEL` — имя модели
- `QWEN_API_KEY` — токен доступа

Для Docker Compose backend получает эти переменные из `.env` через `env_file`.

Поля `QWEN_*` нужны только если используется внешний Qwen.

Пример `.env`:

```env
BACKEND_URL=http://127.0.0.1:8000
OCR_GPU=0
QWEN_API_BASE=http://llm.ncdev.ru/v1
QWEN_MODEL=Qwen3-VL-8B-Instruct-FP8
QWEN_API_KEY=replace-me
```

## API

### `GET /health`

Возвращает статус backend, признак настройки Qwen и список поддерживаемых расширений.

### `POST /analyze`

`multipart/form-data`:

- `files` — один или несколько файлов
- `categories_json` — JSON-массив категорий, например `["PER","ORG","EMAIL"]`
- `custom_words` — пользовательский словарь, по одной фразе на строку
- `use_ocr` — `true/false`
- `engine` — `auto|natasha|qwen|regex`

### `POST /redact/{analysis_id}`

`application/json`:

```json
{
  "selected_hit_ids_by_file": {
    "f1": ["h1", "h2"]
  },
  "manual_terms_by_file": {
    "f1": ["ООО Ромашка", "1234 567890"]
  },
  "redaction_style": "black",
  "include_original": true,
  "include_markdown": true,
  "include_docx": true
}
```

Ответ: ZIP-архив с результатами.

## Qwen

Если `QWEN_API_BASE`, `QWEN_MODEL` и `QWEN_API_KEY` не заданы, приложение продолжит работать без LLM и переключится на локальные fallback-движки.

Проверка backend:

```bash
curl -s http://127.0.0.1:8000/health
```

Ожидаемо для активного Qwen:

```json
{
  "status": "ok",
  "qwen_configured": true
}
```

## Полезные файлы

- [docker-compose.yml](docker-compose.yml)
- [Dockerfile.backend](Dockerfile.backend)
- [Dockerfile.frontend](Dockerfile.frontend)
- [scripts/deploy-ubuntu.sh](scripts/deploy-ubuntu.sh)
- [scripts/generate-self-signed.sh](scripts/generate-self-signed.sh)

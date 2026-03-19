# Сборка и запуск

## Назначение документа

Этот документ описывает, как собрать и запустить сервис `Navicon Sanitizer 3.0`.

Важно:

- в текущей версии решения не используется внешняя база данных
- миграции отсутствуют, так как все промежуточные данные хранятся во временном in-memory хранилище backend-сервиса

## Состав решения

- `frontend` — Streamlit-интерфейс для загрузки, анализа, подтверждения и скачивания результатов
- `backend` — FastAPI-сервис для анализа документов, OCR и формирования итогового архива
- `nginx` — reverse proxy для стенда и HTTPS-сценария

## Требования

### Локальный запуск

- Windows 10/11
- Python 3.11+

### Контейнерный запуск

- Docker
- Docker Compose

## Быстрый локальный запуск

```bat
run.bat
```

Скрипт:

- создает `venv`, если он отсутствует
- устанавливает зависимости
- поднимает backend
- запускает frontend
- открывает страницу в браузере

Если backend уже запущен и его нужно переиспользовать:

```bat
.\venv\Scripts\python.exe -u run_local.py --reuse-existing-backend
```

## Docker Compose

Перед запуском необходимо создать `.env` в корне проекта на основе `.env.example`.

Запуск:

```bash
docker compose up --build
```

Сервисы по умолчанию:

- frontend: `http://localhost:8501`
- backend: `http://localhost:8000`
- nginx: `https://localhost`

## Переменные окружения

Шаблон файла находится в [.env.example](.env.example).

### Обязательные поля

- `BACKEND_URL` — адрес backend для frontend
- `OCR_GPU` — использование GPU для OCR (`0` или `1`)

### Опциональные поля

- `QWEN_API_BASE`
- `QWEN_MODEL`
- `QWEN_API_KEY`

Поля `QWEN_*` нужны только в том случае, если используется внешний Qwen.
Если Qwen не используется, их можно не заполнять.

### Пример `.env`

```env
BACKEND_URL=http://127.0.0.1:8000
OCR_GPU=0
QWEN_API_BASE=http://llm.ncdev.ru/v1
QWEN_MODEL=Qwen3-VL-8B-Instruct-FP8
QWEN_API_KEY=replace-me
```

## Что хранится в репозитории

- в репозитории хранится только `.env.example`
- реальный `.env` в репозиторий не добавлен
- база данных в текущей версии не используется
- миграции отсутствуют

## Проверка после запуска

Проверка backend:

```bash
curl -s http://127.0.0.1:8000/health
```

Ожидаемый ответ:

```json
{
  "status": "ok",
  "qwen_configured": false
}
```

или

```json
{
  "status": "ok",
  "qwen_configured": true
}
```

## Дополнительные материалы

- [README.md](README.md) — обзор решения
- [ARCHITECTURE.md](ARCHITECTURE.md) — архитектура сервиса
- [USER_GUIDE.md](USER_GUIDE.md) — пользовательская инструкция
- [DEPLOY.md](DEPLOY.md) — расширенные варианты деплоя и технические детали

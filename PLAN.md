# План разработки AutoDub/AutoSub API (по дням)

> Основано на TZ_AutoDub_API.md. Один разработчик.
> Итого: **Этапы 1–3 = ~22 рабочих дня**, Этап 4 — ПОЖЕЛАНИЕ (делаем позже).
>
> Железо: ноутбук (Celeron N5095, 16 ГБ) — весь бекенд локально.
> Субтитры — локально (faster-whisper base, CPU). Озвучка — бесплатный облачный GPU
> (Colab/Kaggle, T4 через туннель) + CosyVoice3.
>
> Примечание: маршруты БЕЗ префикса `/api/v1/` (просто `/auth/...`, `/videos/...`).

---

## Этап 1 — MVP: субтитры (Дни 1–10)

### День 1 — Инфраструктура ✅
- [x] Docker Compose: PostgreSQL, Redis, MinIO (S3)
- [x] Настройка settings.py под переменные окружения (.env)
- [x] Структура приложения core (models, serializers, views, urls)

> Docker-база на порту **5433** (5432 занят локальным PostgreSQL 18).
> Драйвер: psycopg 3 (psycopg2 несовместим с Python 3.14).

### День 2 — Авторизация (JWT) ✅
- [x] djangorestframework-simplejwt
- [x] POST /auth/register/
- [x] POST /auth/login/, refresh/, logout/
- [x] GET /auth/me/

> Проверено автотестом: полный цикл регистрация→вход→refresh→me→logout
> (logout кладёт refresh в чёрный список).

### День 3 — Модели данных ✅
- [x] Video (UUID pk, owner, original_file, duration_seconds, detected_language, status)
- [x] Transcript (video FK, language, segments JSON, speakers JSON)
- [x] Job (video FK, mode, target_languages, hardsub, status, progress_percent, result_files)
- [x] JobLog (job FK, step_name, status, meta) — трассировка этапов
- [x] Миграции + админка

### День 4 — Загрузка и управление видео ✅
- [x] POST /videos/ (multipart, валидация MP4/MOV/MKV/AVI/WEBM, лимит размера)
- [x] GET /videos/ (пагинация, фильтры), GET /videos/{id}/
- [x] DELETE /videos/{id}/
- [x] Permissions: доступ только к своим файлам

> Проверено автотестом: загрузка mp4 → 201, txt → 400, чужое видео → 404,
> фильтр по статусу, удаление → 204. Лимит размера: VIDEO_MAX_SIZE_MB в .env (по умолчанию 2048).

### День 5 — Celery: извлечение аудио ✅
- [x] Celery + Redis, очереди cpu/gpu
- [x] Задача extract_audio_task (ffmpeg → wav 16кГц)
- [x] Статусы: uploading → language_detection → awaiting_user_choice
- [ ] Обновление progress_percent после каждого шага *(перенесено на Дни 6–8 — прогресс считается внутри Job)*

> Установлен ffmpeg 9.0 (winget). Путь в .env: FFMPEG_PATH.
> Задача запускается автоматически после POST /videos/. Retry ×3, потом статус failed.
> Воркер в dev (Windows): `.venv\Scripts\celery -A voical worker -Q cpu -P solo -l info`

### День 6 — Whisper: распознавание речи ✅
- [x] faster-whisper (base, int8, CPU) — транскрипция с таймкодами
- [x] Детект языка + confidence → сохранение в Video
- [x] Кэширование транскрипции (переиспользуем для субтитров/дубляжа)
- [x] GET /videos/{id}/preview-transcript/

> Реальная модель base скачана (~141 МБ в ~/.cache/huggingface), проверена вживую (3 сек аудио → 26 сек, язык en 0.58).
> Мок-режим: `MOCK_ML=true` в .env. Заметка по очистке: `WHISPER_NOTES.md`.

### День 7 — Перевод и генерация субтитров ✅
- [x] Локальный переводчик NLLB-200 (`core/translation.py`, провайдеры mock/nllb/google, lazy-load через transformers) — модель качается при TRANSLATE_PROVIDER=nllb
- [x] Сегментация реплик (таймкоды из Whisper переиспользуются)
- [x] Генерация .srt и .vtt (`core/subtitles.py`)
- [x] Job API: POST /jobs/ (mode/target_languages/hardsub), GET /jobs/, GET /jobs/{id}/, скачивание /jobs/{id}/subtitles/
- [ ] Опция hardsub: наложение субтитров на видео через ffmpeg (оставим на День 8/10)

> Реальный NLLB-200 пока НЕ установлен (нужны transformers+sentencepiece+torch ~1–2 ГБ, модель ~1.2 ГБ).
> Включить: поставить зависимости + `TRANSLATE_PROVIDER=nllb` в .env. Сейчас по умолчанию `mock`. Тест 14/14.

### День 8 — Jobs API
- [ ] POST /videos/{id}/jobs/ (mode: subtitles | dubbing, target_languages)
- [ ] GET /jobs/{id}/, GET /jobs/{id}/result/
- [ ] POST /jobs/{id}/cancel/, retry/, DELETE /jobs/{id}/
- [ ] GET /jobs/ (фильтры: status, mode, video_id)
- [ ] Скачивание файлов результатов

### День 9 — Real-time статус + служебные эндпоинты ✅
- [x] Django Channels + Redis channel layer (Daphne, channels_redis)
- [x] WS `ws/jobs/{id}/?token=...`: события init / progress / completed / failed (+ проверка владельца)
- [x] GET /languages/ (20 языков, без авторизации), /health/ (DB/Redis/ffmpeg)

### День 10 — Надёжность и тесты ✅
- [x] Retry для сбойных задач (Celery max_retries + `failed` → `retry`/`cancel`)
- [x] Корректные коды ошибок: 400/401/404/409/413 (проверено; 422 через DRF=400)
- [x] Юнит-тесты сериализаторов/вьюх, моки ML-шагов
- [x] Итоговый прогон: загрузил видео → субтитры скачаны (27 проверок)
- [x] **Релиз MVP**

---

## Этап 2 — Дубляж без клонирования (Дни 11–16)

### День 11 — Диаризация ✅
- [x] pyannote.audio: определение спикеров и границ реплик (`core/diarization.py`, mock + real pyannote/speaker-diarization-3.1)
- [x] Сохранение speaker_id в segments транскрипта (интеграция в `detect_language_task`)

### День 12 — Определение пола говорящего ✅
- [x] Анализ pitch/F0 (`core/gender.py`, librosa piptrack): male/female + confidence
- [x] Результат в speakers JSON (интеграция в `detect_language_task`, mock + fallback без librosa)

### День 13 — Пул пресет-голосов ✅
- [x] Таблица голосов (`core/voices.py`, 14 пресетов: ru/en/fr/de/es/zh/kk × male/female)
- [x] Автоподбор `get_preset_voice(lang, gender)` с fallback
- [x] GET /voices/ (фильтры ?lang=&gender=, без авторизации)

### День 14 — Синтез речи ✅
- [x] TTS в Celery-pipeline (`core/tts.py`, mock-тон + edge-tts fallback): синтез каждой реплики отдельно
- [x] voice_mode=preset_auto — автоподбор по `get_preset_voice(lang, gender)`, длительность = интервал сегмента

### День 15 — Синхронизация таймингов ✅
- [x] Time-stretch (`core/audio.py`, ffmpeg atempo, цепочка для 0.5-2.0)
- [x] Подгон длины аудио реплики под оригинальный интервал (в `process_job_task` после TTS)

### День 16 — Сборка видео ✅
- [x] Микширование речевой дорожки (+ фоновая дорожка, `core/mux.py:11` assemble_dubbed_audio)
- [x] Замена/добавление аудиодорожки в видео (ffmpeg mux, `core/mux.py:49` mux_video)
- [x] E2E тест дубляжа (`core/tests/test_dubbing.py` + `test_e2e_subtitles.py`), **релиз Этапа 2**

---

## Этап 3 — Voice cloning через бесплатный GPU (Дни 17–22)

### День 17 — GPU-воркер в облаке ✅
- [x] Colab/Kaggle: запуск CosyVoice3 FastAPI (`gpu_worker/server.py`, совместим с `runtime/python/fastapi/server.py`)
- [x] Туннель ngrok/cloudflared (`gpu_worker/README.md`, `gpu_worker/colab_setup.py`), URL воркера в `.env`
- [x] Health-check воркера перед постановкой задач (`core/cosyvoice_client.py:31` health_check)

### День 18 — Клиент CosyVoice в Django ✅
- [x] HTTP-клиент Celery-задачи → POST /inference_zero_shot (`core/cosyvoice_client.py:62` httpx)
- [x] Кэширование клонов спикеров (`core/cosyvoice_client.py:96` get_speaker_prompt_path, ffmpeg slice + media/cosyvoice_cache)
- [x] Обработка недоступности воркера → fallback на пресеты (`core/cosyvoice_client.py:128` synthesize_with_fallback, `core/tasks.py:249` integrated)

### День 19 — Приоритет клонирования ✅
- [x] voice_mode=clone если качество сэмпла достаточное (`core/cosyvoice_client.py:158` is_sample_sufficient, `core/cosyvoice_client.py:184` choose_voice_mode)
- [x] Fallback: clone → preset_auto (логика из ТЗ п. 3.5, `core/tasks.py:236` voice_mode выбор + per-segment `is_sample_sufficient` → `core/cosyvoice_client.py:128` synthesize_with_fallback, `core/serializers.py:142` expose voice_mode)

### День 20 — Разделение вокал/фон (опционально) ✅ mock
- [x] Demucs: vocal/background separation (`core/separation.py:12` separate_vocals — mock копирование + тишина, real demucs требует GPU, отключён на ноутбуке)
- [x] Микс новой речи с сохранением фоновой музыки (`core/separation.py:44` mix_with_background, amix)

### День 21 — Улучшенный gender detection (опционально) — отложено
- [ ] Классификация пола по эмбеддингам спикера вместо pitch (pitch-метод `core/gender.py` достаточен для MVP, embeddings — позже при наличии GPU)

### День 22 — Финал ✅
- [x] Полный E2E: видео → выбор режима → готовый дубляж/субтитры (`core/tests/test_dubbing_e2e.py` + `test_subtitles_e2e.py` + `test_voice_priority.py` 37 тестов)
- [x] Документация API, логирование всех этапов pipeline (`core/tasks.py:189` logger + JobLog process_start/translate/tts/mux/process_done, `README.md` полный)
- [x] **Релиз Этапа 3**

---

## Этап 4 — Продукт (ПОЖЕЛАНИЕ — будем делать позже)

- [ ] Тарифы, лимиты, биллинг
- [ ] Редактор субтитров: GET/PATCH /jobs/{id}/subtitles/, regenerate/
- [ ] Presigned upload для больших файлов (>2 ГБ)
- [ ] Личный кабинет, история, аналитика
- [ ] Email/webhook уведомления о завершении

---

## Риски и заметки

| Риск | План Б |
|---|---|
| Colab отключает сессии | Kaggle (30 ч/нед) как запасной GPU |
| pyannote требует HF-токен и принятие лицензии | Зарегистрироваться заранее (бесплатно) |
| NLLB медленный на CPU | Для MVP перевод только коротких видео; позже — GPU |
| Whisper на CPU медленный для длинных видео | Модель base/int8, ограничение длительности на этапе MVP |

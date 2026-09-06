# AutoDub / AutoSub API — сервис автодубляжа и субтитров

REST API (Django + DRF) + Celery + Whisper + NLLB + TTS/CosyVoice + ffmpeg.

**Пайплайн:** `загрузка видео → extract_audio (ffmpeg 16кГц) → detect_language + faster-whisper (транскрипт+таймкоды) → diarization (pyannote) + gender (librosa) → выбор режима → translate (NLLB) → TTS (preset auto / CosyVoice clone) → time-stretch (atempo) → assemble_dubbed_audio → mux_video → готово`

## Стек
- Django 6.1, DRF, SimpleJWT, django-filter, Channels (WS)
- Celery + Redis (очереди `cpu`), PostgreSQL 16 (порт **5433**), MinIO (S3)
- ML локально (CPU): `faster-whisper base/int8`, `pyannote/speaker-diarization-3.1`, `librosa`, `NLLB-200`
- TTS: mock тон + `edge-tts` → пресеты `core/voices.py` (14 голосов) → CosyVoice3 на Colab/Kaggle (GPU T4, туннель)
- ffmpeg 9.0 (`FFMPEG_PATH` в `.env`)

## Быстрый старт (локально, без GPU — всё на моках)
```powershell
# 1. Зависимости
.venv\Scripts\python.exe -m pip install -r requirements.txt
# 2. Переменные
copy .env.example .env   # заполни SECRET_KEY, POSTGRES_PASSWORD
# 3. Контейнеры (Docker Desktop должен быть запущен)
C:\Users\GG\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe compose up -d
# 4. Миграции
.venv\Scripts\python.exe manage.py migrate
# 5. Запуск
.venv\Scripts\python.exe manage.py runserver          # терминал 2
.venv\Scripts\celery -A voical worker -Q cpu -P solo -l info  # терминал 3 (Windows!)
```

По умолчанию `MOCK_ML=true` и `TRANSLATE_PROVIDER=mock` — без скачки моделей. Для реальных моделей:
```ini
MOCK_ML=false
TRANSLATE_PROVIDER=nllb
HF_TOKEN=hf_xxx   # для pyannote, прими лицензии на HF
NLLB_MODEL=facebook/nllb-200-distilled-600M
WHISPER_MODEL=base
```

## API (без префикса `/api/v1/`, см. `voical/urls.py`)
| Метод | Endpoint | Описание |
|---|---|---|
| POST | `/auth/register/` | регистрация |
| POST | `/auth/login/` | JWT access/refresh |
| POST | `/auth/token/refresh/` | обновить access |
| POST | `/auth/logout/` | blacklist refresh |
| GET | `/auth/me/` | текущий пользователь |
| POST | `/videos/` | загрузка `multipart file` (mp4/mov/mkv/avi/webm, лимит `VIDEO_MAX_SIZE_MB`) → 201 + запуск `extract_audio_task` |
| GET | `/videos/` | список своих (фильтр `?status=`) |
| GET | `/videos/{id}/` | детали + `detected_language` |
| DELETE | `/videos/{id}/` | удаление |
| GET | `/videos/{id}/preview-transcript/` | черновой транскрипт |
| POST | `/jobs/` | создание задачи `{video, mode: subtitles|dubbing, target_languages: ["ru"], hardsub: false}` → `process_job_task` |
| POST | `/videos/{id}/jobs/` | алиас для `/jobs/` |
| GET | `/jobs/` | список (фильтры `status, mode, video_id`) |
| GET | `/jobs/{id}/` | статус `progress_percent, current_step, result_files, voice_mode` |
| GET | `/jobs/{id}/result/` | файлы результата |
| POST | `/jobs/{id}/cancel/` | отмена (409 если уже done/failed) |
| POST | `/jobs/{id}/retry/` | перезапуск failed |
| DELETE | `/jobs/{id}/` | удаление + чистка `media/jobs/{id}` |
| GET | `/jobs/{id}/subtitles/?lang=ru&fmt=srt` | скачать srt/vtt |
| GET | `/languages/` | 20 языков (без auth) |
| GET | `/voices/?lang=ru&gender=male` | пресеты 14 голосов |
| GET | `/health/` | DB/Redis/ffmpeg |

**WebSocket:** `ws://host/ws/jobs/{id}/?token=<access>` — события `job_progress` (45%), `job_completed`, `job_failed`.

**Коды:** 400 (valid), 401, 403/404 (чужое →404), 409 (конфликт статуса), 413 (превышен размер), 429, 500, 503 (ML перегружен).

## Дубляж — детали (Этап 2-3)
- **Diarization** `core/diarization.py` — mock или `pyannote/speaker-diarization-3.1` (`HF_TOKEN`)
- **Gender** `core/gender.py` — `librosa.piptrack` (fallback если нет librosa)
- **Пресеты** `core/voices.py` — `get_preset_voice(lang, gender)` с fallback
- **TTS** `core/tts.py` — `synthesize()` mock тон `sine 440Hz` или `edge-tts`; длительность = интервал сегмента
- **Time-stretch** `core/audio.py:36` `time_stretch()` — `ffmpeg atempo` (цепочка для 0.5-2.0), дельта <50мс — копия
- **Сборка** `core/mux.py:11` `assemble_dubbed_audio()` — раскладка `tts/0000.wav` по `start`, нормализация пика 0.99; `core/mux.py:49` `mux_video()` — `ffmpeg -c:v copy -map 0:v:0 -map 1:a:0 -shortest`
- **Clone** `core/cosyvoice_client.py:158` — `is_sample_sufficient()` (>=1.5с), `choose_voice_mode()` (clone vs preset_auto), `synthesize_with_fallback()` (health_check → zero_shot → fallback), кэш `media/cosyvoice_cache/{video}_{spk}.wav`

## GPU-воркер CosyVoice3 (Этап 3, Дни 17-19)
Локально ноутбук (Celeron) не тянет CosyVoice → GPU на Colab/Kaggle (T4) + туннель.

- Сервер: `gpu_worker/server.py` — совместим с `runtime/python/fastapi/server.py`, endpoints `/health`, `/inference_zero_shot`, `/inference_cross_lingual`, mock если модели нет.
- Запуск локально (mock): `.venv\Scripts\python.exe -m uvicorn gpu_worker.server:app --port 50000`
- Colab/Kaggle: см. `gpu_worker/README.md` + `gpu_worker/colab_setup.py` (git clone CosyVoice, pip install, запуск сервера, `cloudflared` туннель → URL).
- Django: `.env` → `COSYVOICE_URL=https://xxx.trycloudflare.com`, `COSYVOICE_ENABLED=true`; health-check перед каждой задачей, fallback на пресеты если недоступен.

## Тесты (37 тестов, `SimpleTestCase`, без БД)
```powershell
.venv\Scripts\python.exe manage.py test core.tests --verbosity=2
# или по модулям
.venv\Scripts\python.exe manage.py test core.tests.test_audio core.tests.test_mux core.tests.test_dubbing_e2e core.tests.test_cosyvoice core.tests.test_voice_priority
```
Покрыто: atempo цепочка, time-stretch реальный ffmpeg, сборка дубляжа, mux, subtitles, full dubbing pipeline (mock), cosyvoice health/clone/caching, sample sufficient, voice_mode clone/preset.

## Логи и трассировка
`core/tasks.py` пишет `logger.info` на каждом этапе + `JobLog` (`step_name`, `status`, `meta`, `started_at/finished_at`): `process_start`, `translate_to_{lang}`, `tts_{lang}`, `mux_{lang}`, `process_done`. Смотри `admin` → JobLog или `docker logs`.

## Переменные `.env`
```
SECRET_KEY, POSTGRES_DB/USER/PASSWORD, DB_HOST/PORT (5433), REDIS_URL, MINIO_*, FFMPEG_PATH,
WHISPER_MODEL, MOCK_ML, TRANSLATE_PROVIDER, NLLB_MODEL, GOOGLE_API_KEY,
HF_TOKEN, DIARIZATION_MODEL,
COSYVOICE_URL, COSYVOICE_ENABLED, COSYVOICE_TIMEOUT, COSYVOICE_HEALTH_TIMEOUT, COSYVOICE_SAMPLE_MIN_DURATION,
VIDEO_MAX_SIZE_MB, ALLOWED_VIDEO_FORMATS
```

## Roadmap
- Этап 1 (Дни 1-10) ✅ MVP субтитры
- Этап 2 (11-16) ✅ дубляж без клонирования (preset)
- Этап 3 (17-19) ✅ клон через GPU (mock+real), приоритет и fallback
- День 20 (Demucs) — mock `core/separation.py` (реальный требует GPU, отключён на ноутбуке)
- День 21 (gender embeddings) — pitch пока достаточно, embeddings — позже
- День 22 (финал) ✅ логи, доки, 37 тестов, релиз Этапа 3
- Этап 4 (пожелание) — тарифы, редактор субтитров, presigned upload, кабинеты — позже

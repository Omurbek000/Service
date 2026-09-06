# Дневник/диареза — что скачалось и как удалить (локально, не коммитить)

> Расширенная версия `WHISPER_NOTES.md` — теперь покрывает все ML-модели (Whisper, NLLB, pyannote).

## Что занимает место (факт на сейчас)

| Что | Путь | Размер | Когда ставится |
|---|---|---|---|
| Whisper `base` | `C:\Users\GG\.cache\huggingface\hub\models--Systran--faster-whisper-base` | ~141 МБ | День 6 (скачано) |
| Весь кеш HF | `C:\Users\GG\.cache\huggingface` | ~141 МБ сейчас | растёт с каждой моделью |
| pip Whisper | `faster-whisper`, `ctranslate2`, `huggingface_hub`, `tokenizers` | ~400–500 МБ в `.venv` | День 6 |
| pip Channels | `channels`, `channels_redis`, `daphne` | ~20 МБ | День 9 |
| NLLB-200 (опц.) | `~\.cache\huggingface\hub\models--facebook--nllb-200-distilled-600M` | ~1.2 ГБ модель + `torch` ~800 МБ | День 7 (не ставился, mock) |
| pyannote (опц.) | `~\.cache\huggingface\hub\models--pyannote--speaker-diarization-3.1` + `torch`/`torchaudio` | ~500 МБ модель + `torch` | День 11 (не ставился, mock) |
| librosa (опц.) | `librosa`, `soundfile`, `numpy` | ~150 МБ в `.venv` | День 12 (не ставился, mock) |
| Временные медиа | `media/audio/*.wav`, `media/videos/*`, `media/jobs/*` | копейки | чистятся |

## Как удалить и освободить диск/память

### 1. Удалить модели из кеша HF (выборочно)
```powershell
# Whisper
Remove-Item -Recurse -Force "C:\Users\GG\.cache\huggingface\hub\models--Systran--faster-whisper-base"

# NLLB (если ставил)
Remove-Item -Recurse -Force "C:\Users\GG\.cache\huggingface\hub\models--facebook--nllb-200-distilled-600M"

# pyannote (если ставил)
Remove-Item -Recurse -Force "C:\Users\GG\.cache\huggingface\hub\models--pyannote--speaker-diarization-3.1"
Remove-Item -Recurse -Force "C:\Users\GG\.cache\huggingface\hub\models--pyannote--segmentation-3.0"

# или ВЕСЬ кеш целиком (если ничего не нужно):
Remove-Item -Recurse -Force "C:\Users\GG\.cache\huggingface"
```

### 2. Удалить pip-пакеты из .venv
```powershell
# Whisper
.venv\Scripts\python.exe -m pip uninstall -y faster-whisper ctranslate2

# NLLB (если ставил)
.venv\Scripts\python.exe -m pip uninstall -y transformers sentencepiece torch torchaudio

# pyannote (если ставил)
.venv\Scripts\python.exe -m pip uninstall -y pyannote.audio speechbrain

# librosa (если ставил)
.venv\Scripts\python.exe -m pip uninstall -y librosa soundfile

# Channels (если нужно откатить WS)
.venv\Scripts\python.exe -m pip uninstall -y channels channels-redis daphne
```

### 3. Очистить pip-кеш
```powershell
.venv\Scripts\python.exe -m pip cache purge
```

### 4. Удалить временные медиа
```powershell
Remove-Item -Recurse -Force media\audio, media\videos, media\jobs -ErrorAction SilentlyContinue
```

### 5. Вернуться на моки (без моделей, 0 нагрузки)
В `.env`:
```ini
MOCK_ML=true              # Whisper + pyannote → заглушки
TRANSLATE_PROVIDER=mock   # NLLB → заглушка
# HF_TOKEN=               # можно очистить, если не нужен
```
После этого приложение не грузит ни одной ML-модели.

## Где что лежит в .venv?
```powershell
.venv\Scripts\python.exe -m pip list
.venv\Scripts\python.exe -m pip show faster-whisper  # Location
dir .venv\Lib\site-packages\ctranslate2  # проверить
```

## Примечание про symlink warning (HF Hub)
При скачке было предупреждение про symlink. Включи **Developer Mode** (Параметры → Для разработчиков → Режим разработчика), тогда кеш займёт меньше. Не критично.

## Как вернуть обратно

### Whisper
```powershell
.venv\Scripts\python.exe -m pip install faster-whisper
# Модель base скачается сама при первом вызове detect_language_task (MOCK_ML=false)
```

### NLLB (перевод)
```powershell
.venv\Scripts\python.exe -m pip install transformers sentencepiece torch --index-url https://download.pytorch.org/whl/cpu
# В .env: TRANSLATE_PROVIDER=nllb
```

### pyannote (диаризация) — нужен токен
1. Зарегистрируйся на https://huggingface.co/join (если нет аккаунта)
2. Прими условия моделей (кнопка Agree):
   - https://huggingface.co/pyannote/speaker-diarization-3.1
   - https://huggingface.co/pyannote/segmentation-3.0
3. Создай токен: https://huggingface.co/settings/tokens → Create new token → тип Read → скопируй `hf_...`
4. Вставь в `Service/.env`:
   ```ini
   HF_TOKEN=hf_твой_токен_сюда
   MOCK_ML=false
   ```
5. Поставь пакет:
   ```powershell
   .venv\Scripts\python.exe -m pip install pyannote.audio
   # Модель скачается сама при первом вызове diarization (MOCK_ML=false)
   ```

### librosa (пол говорящего)
```powershell
.venv\Scripts\python.exe -m pip install librosa soundfile
# Работает сразу после установки (MOCK_ML=false)
```

Модели HF скачаются сами при первом вызове (если `MOCK_ML=false` / `TRANSLATE_PROVIDER=nllb`).

---
*Этот файл заменяет `WHISPER_NOTES.md` (тот можно удалить).*

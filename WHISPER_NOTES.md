# Whisper — что скачалось и как удалить

> Файл для локального использования, не коммитить.

## Что занимает место

| Что | Путь | Размер |
|---|---|---|
| Модель `base` | `C:\Users\GG\.cache\huggingface\hub\models--Systran--faster-whisper-base` | ~141 МБ |
| Весь кеш HF | `C:\Users\GG\.cache\huggingface` | ~141 МБ (пока только base) |
| pip-пакеты | `faster-whisper`, `ctranslate2`, `huggingface_hub`, `tokenizers` | ~400–500 МБ в `.venv` |
| Временные аудио | `media/audio/*.wav`, `media/videos/*` | копейки, чистятся после задач |

## Как удалить и освободить память/диск

### 1. Удалить модель Whisper (освободит ~140 МБ)
```powershell
Remove-Item -Recurse -Force "C:\Users\GG\.cache\huggingface\hub\models--Systran--faster-whisper-base"
# или весь кеш HF целиком (если больше nothing не нужен):
Remove-Item -Recurse -Force "C:\Users\GG\.cache\huggingface"
```

### 2. Удалить pip-пакеты (из .venv)
```powershell
.venv\Scripts\python.exe -m pip uninstall -y faster-whisper ctranslate2 huggingface-hub
```

### 3. Очистить pip-кеш
```powershell
.venv\Scripts\python.exe -m pip cache purge
```

### 4. Удалить временные медиа
```powershell
Remove-Item -Recurse -Force media\audio, media\videos -ErrorAction SilentlyContinue
```

### 5. Вернуться на моки (без модели)
В файле `.env`:
```ini
MOCK_ML=true
```
После этого приложение будет использовать заглушки и не грузит модель вообще.

## Примечание про symlink warning
При скачке было предупреждение про symlink. Можно включить **Developer Mode** в Windows (Параметры → Для разработчиков → Режим разработчика), тогда кеш будет занимать чуть меньше. Не критично.

## Как вернуть обратно
```powershell
.venv\Scripts\python.exe -m pip install faster-whisper
# Модель скачается сама при первом вызове detect_language_task (MOCK_ML=false)
```

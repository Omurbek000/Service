# GPU-воркер CosyVoice3 — запуск на Colab / Kaggle (ТЗ День 17)

Этот воркер реализует тот же интерфейс, что и `runtime/python/fastapi/server.py` из оригинального CosyVoice,
но добавляет `/health` и mock-режим для локальной разработки.

## Интерфейс
- `GET /health` → `{"status":"ok","mock":true/false}`
- `POST /inference_zero_shot` (tts_text, prompt_text, prompt_wav) → wav bytes (streaming)
- `POST /inference_cross_lingual` (tts_text, prompt_wav) → wav
- `POST /inference_sft` (tts_text, spk_id) → wav
- и т.д. (см. `server.py`)

Mock: если модель не загружена — возвращает тон 440Гц нужной длительности (эквивалент `core/tts.py`).

---

## Вариант A: Colab (T4 бесплатно)

1. Создай ноутбук на https://colab.research.google.com (GPU → T4).
2. Выполни ячейки:

```python
# 1. Клонируем CosyVoice3 и зависимости (один раз)
!git clone https://github.com/FunAudioLLM/CosyVoice.git
%cd CosyVoice
!pip install -r requirements.txt
# ttsfrd (опционально)
!pip install funasr modelscope

# 2. Копируем наш воркер (или клонируй весь Service)
!git clone https://github.com/<твой>/Service.git
!cp Service/gpu_worker/server.py ./runtime/python/fastapi/server.py

# 3. Запускаем сервер (фон)
!nohup python runtime/python/fastapi/server.py --port 50000 --model_dir iic/CosyVoice2-0.5B > /tmp/cosy.log 2>&1 &
!sleep 10 && curl -s http://localhost:50000/health && echo " — ok"
```

3. Подними туннель (выбери один):

**cloudflared (рекомендуется, без регистрации):**
```python
!wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /tmp/cloudflared
!chmod +x /tmp/cloudflared
!nohup /tmp/cloudflared tunnel --url http://localhost:50000 > /tmp/tunnel.log 2>&1 &
!sleep 5 && cat /tmp/tunnel.log | grep -o 'https://.*trycloudflare.com'
# скопируй https://xxx.trycloudflare.com
```

**ngrok (нужен токен):**
```python
!pip install pyngrok -q
from pyngrok import ngrok
ngrok.set_auth_token("ТВОЙ_NGROK_TOKEN")
url = ngrok.connect(50000)
print(url)  # https://xxx.ngrok-free.app
```

4. Скопируй URL в `.env` ноутбука:
```ini
COSYVOICE_URL=https://xxx.trycloudflare.com
COSYVOICE_ENABLED=true
```

---

## Вариант B: Kaggle (30 ч/нед, T4 x2)

Аналогично Colab, но в Kaggle Notebook:
- Settings → Accelerator → GPU T4 x2
- Internet → On
- Выполни те же ячейки, туннель — `cloudflared` (ngrok тоже работает).

---

## Локальная проверка (без GPU, mock)

```powershell
# из корня Service
.venv\Scripts\python.exe -m uvicorn gpu_worker.server:app --host 0.0.0.0 --port 50000
# в другом терминале
curl http://localhost:50000/health
curl -X POST http://localhost:50000/inference_zero_shot -F tts_text="Привет мир" -F prompt_text="hello" -F prompt_wav=@media/audio/test.wav --output out.wav
```

---

## Переменные окружения воркера
- `COSYVOICE_MODEL_DIR` — путь к модели (по умолчанию `iic/CosyVoice2-0.5B`, для CosyVoice3: `FunAudioLLM/Fun-CosyVoice3-0.5B`)
- `COSYVOICE_MOCK` — `auto` (пытается грузить модель, иначе mock) | `true` (принудительный mock) | `false`
- `FFMPEG_PATH` — путь к ffmpeg (для mock)

## Переменные Django (.env ноутбука)
```ini
COSYVOICE_URL=https://xxx.trycloudflare.com
COSYVOICE_ENABLED=true
COSYVOICE_TIMEOUT=30
COSYVOICE_HEALTH_TIMEOUT=5
```

Health-check перед постановкой задач делается в `core/cosyvoice_client.py:health_check()`.
Если воркер недоступен — `process_job_task` падает в fallback на пресеты (`core/tts.py`).

# GPU-воркер CosyVoice3 (ТЗ День 17) — FastAPI сервер для запуска на Colab/Kaggle
# Совместим с оригиналом runtime/python/fastapi/server.py (интерфейс inference_zero_shot и т.д.)
# При отсутствии GPU/модели работает в mock-режиме (генерит тон через ffmpeg, как core/tts.py)
import os
import io
import sys
import argparse
import logging
import tempfile
import subprocess
from pathlib import Path

import numpy as np

logging.getLogger('matplotlib').setLevel(logging.WARNING)

from fastapi import FastAPI, UploadFile, Form, File
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title='CosyVoice GPU Worker', version='1.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Глобальная модель (None = mock)
cosyvoice = None
MODEL_DIR = os.getenv('COSYVOICE_MODEL_DIR', 'iic/CosyVoice2-0.5B')
MOCK_MODE = os.getenv('COSYVOICE_MOCK', 'auto')  # auto | true | false


def _try_load_model(model_dir):
    """Пытается загрузить CosyVoice, иначе остаётся в mock."""
    global cosyvoice
    try:
        sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
        # пробуем импортировать как в оригинале
        from cosyvoice.cli.cosyvoice import AutoModel
        from cosyvoice.utils.file_utils import load_wav
        print(f'[gpu_worker] загружаем модель {model_dir} ...')
        cosyvoice = AutoModel(model_dir=model_dir)
        print('[gpu_worker] модель загружена, mock отключён')
        return False
    except Exception as e:
        print(f'[gpu_worker] mock режим (причина: {e})')
        cosyvoice = None
        return True


def _mock_sine(duration=1.0, sr=24000):
    """Генерит тон 440 Гц длительностью duration, возвращает bytes wav."""
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        ffmpeg = os.getenv('FFMPEG_PATH', 'ffmpeg')
        subprocess.run([
            ffmpeg, '-y', '-f', 'lavfi', '-i', f'sine=frequency=440:duration={duration}',
            '-c:a', 'pcm_s16le', '-ar', str(sr), '-ac', '1', str(tmp_path)
        ], check=True, capture_output=True)
        # отдаём как pcm16 wav bytes (читаем файл)
        return tmp_path.read_bytes()
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass


def generate_data(model_output):
    """Генератор для StreamingResponse из CosyVoice (как в оригинале)."""
    for chunk in model_output:
        tts_audio = (chunk['tts_speech'].numpy() * (2 ** 15)).astype(np.int16).tobytes()
        yield tts_audio


@app.get('/')
async def root():
    return {
        'service': 'cosyvoice-gpu-worker',
        'mock': cosyvoice is None,
        'model_dir': MODEL_DIR,
        'endpoints': ['/health', '/inference_zero_shot', '/inference_cross_lingual', '/inference_sft']
    }


@app.get('/health')
async def health():
    """Health-check для Django (ТЗ День 17)."""
    return {
        'status': 'ok',
        'mock': cosyvoice is None,
        'model_dir': MODEL_DIR,
    }


@app.get('/inference_sft')
@app.post('/inference_sft')
async def inference_sft(tts_text: str = Form(), spk_id: str = Form()):
    if cosyvoice is None:
        # mock: генерим тон по длительности текста (0.35 сек на слово)
        dur = max(0.5, len(tts_text.split()) * 0.35)
        wav_bytes = _mock_sine(duration=dur)
        return StreamingResponse(io.BytesIO(wav_bytes), media_type='audio/wav')
    model_output = cosyvoice.inference_sft(tts_text, spk_id)
    return StreamingResponse(generate_data(model_output), media_type='audio/wav')


@app.get('/inference_zero_shot')
@app.post('/inference_zero_shot')
async def inference_zero_shot(
    tts_text: str = Form(),
    prompt_text: str = Form(''),
    prompt_wav: UploadFile = File(...),
):
    if cosyvoice is None:
        dur = max(0.5, len(tts_text.split()) * 0.35)
        wav_bytes = _mock_sine(duration=dur)
        return StreamingResponse(io.BytesIO(wav_bytes), media_type='audio/wav')
    # real
    try:
        from cosyvoice.utils.file_utils import load_wav
        prompt_speech_16k = load_wav(prompt_wav.file, 16000)
        model_output = cosyvoice.inference_zero_shot(tts_text, prompt_text, prompt_speech_16k)
        return StreamingResponse(generate_data(model_output), media_type='audio/wav')
    except Exception as e:
        return JSONResponse({'detail': str(e)}, status_code=500)


@app.get('/inference_cross_lingual')
@app.post('/inference_cross_lingual')
async def inference_cross_lingual(
    tts_text: str = Form(),
    prompt_wav: UploadFile = File(...),
):
    if cosyvoice is None:
        dur = max(0.5, len(tts_text.split()) * 0.35)
        wav_bytes = _mock_sine(duration=dur)
        return StreamingResponse(io.BytesIO(wav_bytes), media_type='audio/wav')
    try:
        from cosyvoice.utils.file_utils import load_wav
        prompt_speech_16k = load_wav(prompt_wav.file, 16000)
        model_output = cosyvoice.inference_cross_lingual(tts_text, prompt_speech_16k)
        return StreamingResponse(generate_data(model_output), media_type='audio/wav')
    except Exception as e:
        return JSONResponse({'detail': str(e)}, status_code=500)


@app.get('/inference_instruct')
@app.post('/inference_instruct')
async def inference_instruct(tts_text: str = Form(), spk_id: str = Form(), instruct_text: str = Form()):
    if cosyvoice is None:
        dur = max(0.5, len(tts_text.split()) * 0.35)
        wav_bytes = _mock_sine(duration=dur)
        return StreamingResponse(io.BytesIO(wav_bytes), media_type='audio/wav')
    model_output = cosyvoice.inference_instruct(tts_text, spk_id, instruct_text)
    return StreamingResponse(generate_data(model_output), media_type='audio/wav')


@app.get('/inference_instruct2')
@app.post('/inference_instruct2')
async def inference_instruct2(tts_text: str = Form(), instruct_text: str = Form(), prompt_wav: UploadFile = File(...)):
    if cosyvoice is None:
        dur = max(0.5, len(tts_text.split()) * 0.35)
        wav_bytes = _mock_sine(duration=dur)
        return StreamingResponse(io.BytesIO(wav_bytes), media_type='audio/wav')
    try:
        from cosyvoice.utils.file_utils import load_wav
        prompt_speech_16k = load_wav(prompt_wav.file, 16000)
        model_output = cosyvoice.inference_instruct2(tts_text, instruct_text, prompt_speech_16k)
        return StreamingResponse(generate_data(model_output), media_type='audio/wav')
    except Exception as e:
        return JSONResponse({'detail': str(e)}, status_code=500)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CosyVoice GPU worker')
    parser.add_argument('--port', type=int, default=50000, help='порт')
    parser.add_argument('--host', type=str, default='0.0.0.0')
    parser.add_argument('--model_dir', type=str, default=MODEL_DIR, help='путь к модели или modelscope id')
    parser.add_argument('--mock', action='store_true', help='принудительно mock')
    args = parser.parse_args()

    MODEL_DIR = args.model_dir
    if args.mock or MOCK_MODE == 'true':
        cosyvoice = None
        print('[gpu_worker] принудительный mock')
    elif MOCK_MODE == 'false':
        _try_load_model(MODEL_DIR)
    else:
        _try_load_model(MODEL_DIR)

    uvicorn.run(app, host=args.host, port=args.port)

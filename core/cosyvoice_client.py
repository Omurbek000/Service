# Клиент CosyVoice GPU-воркера (ТЗ Дни 17-18)
# Отвечает за health-check, zero-shot синтез и fallback на пресеты
import logging
import subprocess
import tempfile
from pathlib import Path

import httpx
from django.conf import settings

from .voices import get_preset_voice

logger = logging.getLogger(__name__)


def _base_url():
    url = getattr(settings, 'COSYVOICE_URL', '') or ''
    return url.rstrip('/')


def is_enabled():
    """Включён ли клонирование (есть URL и флаг)."""
    url = _base_url()
    enabled = getattr(settings, 'COSYVOICE_ENABLED', bool(url))
    return bool(enabled and url)


def health_check(timeout=None):
    """
    Проверяет доступность воркера (GET /health).
    Возвращает True если ok, иначе False (не бросает исключение).
    ТЗ День 17 — health-check перед постановкой задач.
    """
    url = _base_url()
    if not url:
        return False
    if timeout is None:
        timeout = getattr(settings, 'COSYVOICE_HEALTH_TIMEOUT', 5)
    try:
        resp = httpx.get(f'{url}/health', timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('status') == 'ok'
        return False
    except Exception as e:
        logger.warning(f'[cosyvoice] health_check failed: {e}')
        return False


def _post_inference(endpoint, data, files, out_path, timeout=None):
    """Общая логика POST на воркер, сохраняет ответ в out_path (wav bytes)."""
    url = _base_url()
    if timeout is None:
        timeout = getattr(settings, 'COSYVOICE_TIMEOUT', 30)
    full_url = f'{url}{endpoint}'
    # httpx ожидает files как dict {name: (filename, fileobj, content_type)}
    # открываем файлы
    opened = {}
    try:
        httpx_files = {}
        for k, p in files.items():
            f = open(p, 'rb')
            opened[k] = f
            httpx_files[k] = (Path(p).name, f, 'audio/wav')
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(full_url, data=data, files=httpx_files)
        if resp.status_code != 200:
            raise RuntimeError(f'CosyVoice {endpoint} вернул {resp.status_code}: {resp.text[:200]}')
        # ответ — wav bytes (streaming)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(resp.content)
        return out_path
    finally:
        for f in opened.values():
            try:
                f.close()
            except Exception:
                pass


def synthesize_zero_shot(text, prompt_wav_path, prompt_text, out_path, timeout=None):
    """
    Zero-shot клонирование: POST /inference_zero_shot
    text — что синтезировать, prompt_wav_path — образец голоса, prompt_text — его транскрипт.
    Возвращает out_path или бросает исключение.
    """
    return _post_inference(
        '/inference_zero_shot',
        data={'tts_text': text, 'prompt_text': prompt_text or text},
        files={'prompt_wav': str(prompt_wav_path)},
        out_path=Path(out_path),
        timeout=timeout,
    )


def synthesize_cross_lingual(text, prompt_wav_path, out_path, timeout=None):
    """Кросс-язычное клонирование: POST /inference_cross_lingual."""
    return _post_inference(
        '/inference_cross_lingual',
        data={'tts_text': text},
        files={'prompt_wav': str(prompt_wav_path)},
        out_path=Path(out_path),
        timeout=timeout,
    )


# --- Кэширование промптов (ТЗ День 18) ---

def _extract_speaker_sample(audio_path, segments, speaker_id, cache_path):
    """
    Вырезает самый длинный сегмент спикера из исходного аудио как промпт.
    Кэширует в cache_path (media/cosyvoice_cache/{video_id}_{speaker_id}.wav).
    Возвращает путь к wav.
    """
    if cache_path.exists():
        return cache_path
    # находим самый длинный сегмент этого спикера
    spk_segs = [s for s in segments if s.get('speaker_id') == speaker_id]
    if not spk_segs:
        spk_segs = segments
    if not spk_segs:
        return None
    best = max(spk_segs, key=lambda s: float(s.get('end', 0)) - float(s.get('start', 0)))
    start = float(best.get('start', 0))
    dur = float(best.get('end', 0)) - start
    dur = max(0.5, min(dur, 10.0))  # ограничиваем 0.5-10 сек
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([
            settings.FFMPEG_PATH, '-y',
            '-i', str(audio_path),
            '-ss', str(start), '-t', str(dur),
            '-ac', '1', '-ar', '16000',
            str(cache_path)
        ], check=True, capture_output=True)
        return cache_path
    except Exception as e:
        logger.warning(f'[cosyvoice] extract sample failed: {e}')
        return None


def get_speaker_prompt_path(video_id, speaker_id, audio_path, segments):
    """Возвращает путь к кэшированному промпту спикера или None."""
    cache_dir = Path(settings.MEDIA_ROOT) / 'cosyvoice_cache'
    cache_path = cache_dir / f'{video_id}_{speaker_id}.wav'
    if cache_path.exists():
        return cache_path
    if not Path(audio_path).exists():
        return None
    return _extract_speaker_sample(Path(audio_path), segments, speaker_id, cache_path)


# --- Приоритет клонирования (ТЗ День 19, п. 3.5) ---

def is_sample_sufficient(speaker_id, audio_path, segments, speakers=None):
    """
    Проверяет, достаточно ли качества образца для клонирования.
    Критерии (простые, без ML):
    - самый длинный сегмент спикера >= COSYVOICE_SAMPLE_MIN_DURATION (по умолчанию 1.5 сек)
    - файл аудио существует
    - при наличии speakers — confidence не слишком низкий (>0.3)
    Возвращает True если можно клонировать, иначе False → fallback на preset.
    """
    min_dur = float(getattr(settings, 'COSYVOICE_SAMPLE_MIN_DURATION', 1.5))
    if not Path(audio_path).exists():
        return False
    spk_segs = [s for s in segments if s.get('speaker_id') == speaker_id]
    if not spk_segs:
        spk_segs = segments
    if not spk_segs:
        return False
    longest = max(float(s.get('end', 0)) - float(s.get('start', 0)) for s in spk_segs)
    if longest < min_dur:
        logger.info(f'[cosyvoice] sample too short for {speaker_id}: {longest:.2f}s < {min_dur}s')
        return False
    if speakers and speaker_id in speakers:
        conf = speakers[speaker_id].get('confidence', 1.0)
        if conf is not None and float(conf) < 0.3:
            logger.info(f'[cosyvoice] low confidence for {speaker_id}: {conf}')
            return False
    # доп. проверка: вырезанный семпл должен быть не пустым (пробуем получить длительность)
    # но не режем заново, просто считаем что longest уже достаточно
    return True


def choose_voice_mode(transcript, audio_path):
    """
    Выбирает voice_mode для задачи (clone или preset_auto) по ТЗ п. 3.5.
    Логика:
    - если клонирование выключено или воркер недоступен → preset_auto
    - если хотя бы у одного спикера образец недостаточного качества → preset_auto (или per-segment fallback)
    - иначе clone
    Для упрощения: если все спикеры sufficient → clone, иначе preset_auto.
    Возвращает строку 'clone' | 'preset_auto'.
    """
    if not is_enabled():
        return 'preset_auto'
    if not health_check():
        return 'preset_auto'
    segments = transcript.segments or []
    speakers = transcript.speakers or {}
    # если нет diarization — считаем одного spk_0
    speaker_ids = list(speakers.keys()) or list({s.get('speaker_id', 'spk_0') for s in segments}) or ['spk_0']
    for spk in speaker_ids:
        if not is_sample_sufficient(spk, audio_path, segments, speakers):
            return 'preset_auto'
    return 'clone'


def synthesize_with_fallback(text, language, gender, out_path, prompt_wav=None, prompt_text=None, duration=None):
    """
    Пытается синтез через CosyVoice (если доступен), иначе fallback на пресет (core/tts.py).
    ТЗ День 18: обработка недоступности воркера → fallback на пресеты.
    Возвращает out_path и флаг used_clone (bool).
    """
    out_path = Path(out_path)
    # пробуем клон
    if is_enabled() and prompt_wav and Path(prompt_wav).exists():
        if health_check():
            try:
                synthesize_zero_shot(text, prompt_wav, prompt_text or text, out_path)
                return out_path, True
            except Exception as e:
                logger.warning(f'[cosyvoice] clone failed, fallback to preset: {e}')
        else:
            logger.info('[cosyvoice] health_check false, fallback to preset')
    # fallback — пресет
    from .tts import synthesize as preset_synthesize
    preset_synthesize(text, language, gender, out_path, duration=duration)
    return out_path, False

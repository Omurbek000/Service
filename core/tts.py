# Синтез речи (ТЗ День 14) — mock + edge-tts/пипер как опция
import subprocess
from pathlib import Path

from django.conf import settings

from .voices import get_preset_voice


def _synthesize_mock(text, out_path, duration=1.0):
    """Генерирует тон 440 Гц нужной длительности (заглушка)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [settings.FFMPEG_PATH, '-y',
         '-f', 'lavfi', '-i', f'sine=frequency=440:duration={duration}',
         '-c:a', 'pcm_s16le', '-ar', '24000', '-ac', '1', str(out_path)],
        check=True, capture_output=True,
    )
    return out_path


def synthesize(text, language, gender, out_path, duration=None):
    """
    Синтезирует речь в out_path (wav 24кГц моно).
    При MOCK_ML=true или без edge-tts — тон-заглушка длительностью duration.
    Возвращает путь.
    """
    if not text or not text.strip():
        text = '...'
    # Длительность — из duration или эвристика 0.3 сек на слово
    if duration is None:
        duration = max(0.5, len(text.split()) * 0.35)

    if settings.MOCK_ML:
        return _synthesize_mock(text, out_path, duration=duration)

    # Попытка real: edge-tts
    try:
        import edge_tts
        import asyncio

        # Маппинг наших голосов → edge-tts voice
        edge_map = {
            ('ru','male'): 'ru-RU-DmitryNeural', ('ru','female'): 'ru-RU-SvetlanaNeural',
            ('en','male'): 'en-US-GuyNeural', ('en','female'): 'en-US-JennyNeural',
            ('fr','male'): 'fr-FR-HenriNeural', ('fr','female'): 'fr-FR-DeniseNeural',
            ('de','male'): 'de-DE-ConradNeural', ('de','female'): 'de-DE-KatjaNeural',
            ('es','male'): 'es-ES-AlvaroNeural', ('es','female'): 'es-ES-ElviraNeural',
        }
        voice = edge_map.get((language, gender), 'en-US-GuyNeural')

        async def _run():
            comm = edge_tts.Communicate(text, voice)
            await comm.save(str(out_path))

        asyncio.run(_run())
        # edge-tts выдаёт mp3, конвертируем в wav 24кГц
        tmp = out_path.with_suffix('.mp3')
        # на деле edge_tts сохраняет сразу в out_path, но если mp3 — конвертим
        if out_path.suffix == '.wav':
            subprocess.run([settings.FFMPEG_PATH, '-y', '-i', str(out_path), '-ar', '24000', str(out_path)], check=True, capture_output=True)
        return out_path
    except Exception as e:
        print(f'[tts] fallback to mock: {e}')
        return _synthesize_mock(text, out_path, duration=duration)

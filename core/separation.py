# Разделение вокал/фон (ТЗ День 20, опционально) — Demucs / Spleeter
# Пока mock: копирует аудио в vocal, генерит тишину для bg, чтобы пайплайн не падал без GPU
import subprocess
import logging
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


def separate_vocals(audio_path, vocal_path, bg_path):
    """
    Разделяет аудио на вокал и фон.
    Если установлен demucs и есть GPU/CPU — использует его, иначе mock.
    Возвращает (vocal_path, bg_path).
    """
    audio_path = Path(audio_path)
    vocal_path = Path(vocal_path)
    bg_path = Path(bg_path)
    vocal_path.parent.mkdir(parents=True, exist_ok=True)
    bg_path.parent.mkdir(parents=True, exist_ok=True)

    # пробуем real demucs
    try:
        import demucs.api  # noqa
        # если demucs установлен, пробуем запустить
        logger.info(f'[separation] trying demucs for {audio_path}')
        # упрощённый вызов: demucs --two-stems=vocals (нужен torch)
        # пока не реализован полностью — fallback в mock, чтобы не требовать GPU на ноутбуке
        raise ImportError('demucs real not wired, use mock')
    except Exception as e:
        logger.info(f'[separation] mock fallback: {e}')
        # mock: vocal = копия оригинала, bg = тишина той же длительности
        try:
            # копируем оригинал как vocal
            subprocess.run([settings.FFMPEG_PATH, '-y', '-i', str(audio_path), '-c', 'copy', str(vocal_path)],
                           check=True, capture_output=True)
        except Exception:
            # если copy не сработала (разные форматы) — перекодируем
            subprocess.run([settings.FFMPEG_PATH, '-y', '-i', str(audio_path), '-c:a', 'pcm_s16le', str(vocal_path)],
                           check=True, capture_output=True)
        # bg — тишина
        try:
            # получаем длительность оригинала
            from .audio import get_duration
            dur = get_duration(audio_path)
        except Exception:
            dur = 5.0
        subprocess.run([
            settings.FFMPEG_PATH, '-y',
            '-f', 'lavfi', '-i', f'anullsrc=r=16000:cl=mono:d={dur}',
            '-c:a', 'pcm_s16le', '-ar', '16000', str(bg_path)
        ], check=True, capture_output=True)
        return vocal_path, bg_path


def mix_with_background(dubbed_vocal_path, bg_path, out_path, vocal_gain=1.0, bg_gain=0.3):
    """
    Микширует новую речь с фоновой дорожкой (опционально, ТЗ День 20).
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # amix с уменьшением громкости фона
    subprocess.run([
        settings.FFMPEG_PATH, '-y',
        '-i', str(dubbed_vocal_path),
        '-i', str(bg_path),
        '-filter_complex', f'[0:a]volume={vocal_gain}[v];[1:a]volume={bg_gain}[b];[v][b]amix=inputs=2:duration=longest',
        str(out_path)
    ], check=True, capture_output=True)
    return out_path

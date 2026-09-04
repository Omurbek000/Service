# Обработка аудио: time-stretch без искажения тона (ТЗ День 15)
import subprocess
import json
from pathlib import Path

from django.conf import settings


def get_duration(path):
    """Возвращает длительность аудио в секундах через ffprobe."""
    ffprobe = str(Path(settings.FFMPEG_PATH).with_name('ffprobe.exe'))
    out = subprocess.run(
        [ffprobe, '-v','quiet','-print_format','json','-show_format', str(path)],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(out.stdout)
    return float(info['format']['duration'])


def _atempo_filter(factor):
    """Строит цепочку atempo для factor вне 0.5-2.0."""
    if 0.5 <= factor <= 2.0:
        return f'atempo={factor:.4f}'
    # разбиваем на несколько atempo по 2.0
    filters = []
    while factor < 0.5:
        filters.append('atempo=0.5')
        factor /= 0.5
    while factor > 2.0:
        filters.append('atempo=2.0')
        factor /= 2.0
    filters.append(f'atempo={factor:.4f}')
    return ','.join(filters)


def time_stretch(in_path, out_path, target_duration):
    """
    Подгоняет длительность in_path под target_duration без изменения тона.
    Возвращает out_path.
    """
    try:
        cur = get_duration(in_path)
    except Exception:
        # fallback: просто копируем
        subprocess.run([settings.FFMPEG_PATH,'-y','-i',str(in_path), str(out_path)], check=True, capture_output=True)
        return out_path

    if abs(cur - target_duration) < 0.05:
        # разница <50мс — не трогаем
        if str(in_path) != str(out_path):
            subprocess.run([settings.FFMPEG_PATH,'-y','-i',str(in_path), str(out_path)], check=True, capture_output=True)
        return out_path

    factor = cur / target_duration  # >1 ускоряем, <1 замедляем
    filt = _atempo_filter(factor)
    subprocess.run(
        [settings.FFMPEG_PATH,'-y','-i',str(in_path), '-filter:a', filt, str(out_path)],
        check=True, capture_output=True,
    )
    return out_path

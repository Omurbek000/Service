# Генерация субтитров (.srt / .vtt) из сегментов транскрипта (ТЗ п. 2.1)


def _ts_srt(seconds):
    seconds = float(seconds)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms == 1000:
        ms = 999
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


def _ts_vtt(seconds):
    seconds = float(seconds)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms == 1000:
        ms = 999
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f'{h:02d}:{m:02d}:{s:02d}.{ms:03d}'


def build_srt(segments):
    """Собирает .srt из списка сегментов {start, end, text, ...}."""
    out = []
    for i, seg in enumerate(segments, 1):
        out.append(str(i))
        out.append(f'{_ts_srt(seg["start"])} --> {_ts_srt(seg["end"])}')
        out.append((seg.get('text') or '').strip())
        out.append('')
    return '\n'.join(out).strip() + '\n'


def build_vtt(segments):
    """Собирает .vtt из списка сегментов {start, end, text, ...}."""
    out = ['WEBVTT', '']
    for seg in segments:
        out.append(f'{_ts_vtt(seg["start"])} --> {_ts_vtt(seg["end"])}')
        out.append((seg.get('text') or '').strip())
        out.append('')
    return '\n'.join(out).strip() + '\n'

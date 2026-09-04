# Сборка итогового видео с дубляжом (ТЗ День 16)
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from django.conf import settings


def assemble_dubbed_audio(segments, tts_dir, out_path, total_duration, sr=24000):
    """
    Собирает одну дорожку дубляжа, расставляя tts-кусочки по таймингам.
    segments — уже переведённые {start,end,...}, tts_dir — папка 0000.wav...
    """
    total_samples = int(total_duration * sr)
    mix = np.zeros(total_samples, dtype=np.float32)

    for i, seg in enumerate(segments):
        wav_path = tts_dir / f'{i:04d}.wav'
        if not wav_path.exists():
            continue
        data, file_sr = sf.read(str(wav_path))
        if file_sr != sr:
            # ресемплим через ffmpeg если нужно
            tmp = wav_path.with_suffix('.tmp.wav')
            subprocess.run([settings.FFMPEG_PATH,'-y','-i',str(wav_path),'-ar',str(sr), str(tmp)], check=True, capture_output=True)
            data, _ = sf.read(str(tmp))
            tmp.unlink(missing_ok=True)
        if data.ndim > 1:
            data = data.mean(axis=1)
        start_idx = int(float(seg['start']) * sr)
        end_idx = start_idx + len(data)
        if end_idx > len(mix):
            # расширяем если нужно
            mix = np.pad(mix, (0, end_idx - len(mix)))
        mix[start_idx:end_idx] += data

    # нормализуем чтобы не клиповало
    peak = np.abs(mix).max()
    if peak > 0.99:
        mix = mix * 0.99 / peak

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), mix, sr)
    return out_path


def mux_video(original_video_path, dubbed_audio_path, out_path):
    """Заменяет аудиодорожку видео на dubbed (копия видео, новая аудио)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [settings.FFMPEG_PATH, '-y',
         '-i', str(original_video_path),
         '-i', str(dubbed_audio_path),
         '-c:v', 'copy',
         '-map', '0:v:0',
         '-map', '1:a:0',
         '-shortest',
         str(out_path)],
        check=True, capture_output=True,
    )
    return out_path

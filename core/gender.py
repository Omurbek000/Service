# Определение пола говорящего по pitch/F0 (ТЗ День 12)
import numpy as np
from pathlib import Path

from django.conf import settings


def detect_gender(audio_path, segments, speakers):
    """
    Для каждого speaker считает средний F0 и проставляет gender/confidence.

    Если MOCK_ML=true или librosa не установлен — возвращает speakers без изменения
    (gender остаётся как было из диаризации).
    """
    if settings.MOCK_ML:
        return speakers

    try:
        import librosa
        import soundfile as sf
    except ImportError as e:
        print(f'[detect_gender] fallback (нет librosa): {e}')
        return speakers

    try:
        y, sr = librosa.load(str(audio_path), sr=16000, mono=True)
    except Exception as e:
        print(f'[detect_gender] load error: {e}')
        return speakers

    # Для каждого спикера собираем pitch по его сегментам
    from collections import defaultdict
    speaker_pitches = defaultdict(list)

    for seg in segments:
        spk = seg.get('speaker_id', 'spk_0')
        s = int(float(seg['start']) * sr)
        e = int(float(seg['end']) * sr)
        chunk = y[s:e]
        if len(chunk) < sr * 0.2:  # короче 0.2 сек — пропускаем
            continue
        # Оценка F0 через piptrack
        try:
            pitches, mags = librosa.piptrack(y=chunk, sr=sr, fmin=50, fmax=400)
            # берём pitch с макс. магнитудой в каждом фрейме
            idx = mags.argmax(axis=0)
            f0 = pitches[idx, range(pitches.shape[1])]
            # фильтруем ненулевые и в диапазоне 50-400
            f0 = f0[(f0 > 50) & (f0 < 400)]
            if len(f0) > 0:
                speaker_pitches[spk].extend(f0.tolist())
        except Exception:
            continue

    for spk, pitches in speaker_pitches.items():
        if not pitches:
            continue
        median = float(np.median(pitches))
        # Порог: <160 Гц — male, >165 Гц — female, между — неуверенно
        if median < 155:
            gender, conf = 'male', 0.85
        elif median > 170:
            gender, conf = 'female', 0.85
        else:
            # около границы — слабая уверенность
            gender = 'male' if median < 162 else 'female'
            conf = 0.55
        speakers[spk] = {'gender': gender, 'confidence': conf, 'median_f0': round(median, 1)}

    return speakers

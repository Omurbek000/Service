# Диаризация говорящих (pyannote.audio, ТЗ День 11)
from django.conf import settings

# Ленивый кеш pipeline
_pyannote = {'pipeline': None}


def _load_pipeline():
    if _pyannote['pipeline'] is None:
        from pyannote.audio import Pipeline
        model = getattr(settings, 'DIARIZATION_MODEL', 'pyannote/speaker-diarization-3.1')
        token = getattr(settings, 'HF_TOKEN', None) or None
        _pyannote['pipeline'] = Pipeline.from_pretrained(model, use_auth_token=token)
    return _pyannote['pipeline']


def diarize(audio_path, segments):
    """
    Проставляет speaker_id для каждого сегмента транскрипта.

    Если MOCK_ML=true или pyannote не установлен — возвращает исходные сегменты
    с speaker_id='spk_0' (заглушка).
    Возвращает (segments, speakers).
    """
    if settings.MOCK_ML:
        # Заглушка как в detect_language_task
        speakers = {'spk_0': {'gender': 'unknown', 'confidence': 0.0}}
        for seg in segments:
            seg['speaker_id'] = 'spk_0'
        return segments, speakers

    try:
        pipeline = _load_pipeline()
    except Exception as e:
        # Fallback на mock если нет токена/модели
        print(f'[diarize] fallback to mock: {e}')
        speakers = {'spk_0': {'gender': 'unknown', 'confidence': 0.0}}
        for seg in segments:
            seg['speaker_id'] = 'spk_0'
        return segments, speakers

    # Запускаем диаризацию
    diarization = pipeline(str(audio_path))

    # Собираем список (start, end, speaker)
    turns = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        turns.append((turn.start, turn.end, speaker))

    speakers = {}
    for _, _, spk in turns:
        if spk not in speakers:
            speakers[spk] = {'gender': 'unknown', 'confidence': 0.0}

    # Назначаем каждому транскрипт-сегменту ближайшего говорящего по перекрытию
    for seg in segments:
        s, e = float(seg['start']), float(seg['end'])
        best_spk = 'spk_0'
        best_overlap = 0.0
        for ts, te, spk in turns:
            overlap = max(0.0, min(e, te) - max(s, ts))
            if overlap > best_overlap:
                best_overlap = overlap
                best_spk = spk
        seg['speaker_id'] = best_spk
        # если совпадений нет — оставляем spk_0
        if best_spk not in speakers and best_spk != 'spk_0':
            speakers[best_spk] = {'gender': 'unknown', 'confidence': 0.0}
    if not speakers:
        speakers = {'spk_0': {'gender': 'unknown', 'confidence': 0.0}}
    return segments, speakers

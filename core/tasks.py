# Фоновые задачи обработки видео
import subprocess
from pathlib import Path

from celery import shared_task
from django.conf import settings

from .models import Video

# Кеш модели Whisper, чтобы не грузить её на каждой задаче
_whisper_model = None


def get_audio_path(video_id):
    """Путь к извлечённой аудиодорожке (wav 16 кГц моно)."""
    return Path(settings.MEDIA_ROOT) / 'audio' / f'{video_id}.wav'


def get_whisper_model():
    """Ленивая загрузка модели Whisper (один раз на процесс воркера)."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel(
            settings.WHISPER_MODEL, device='cpu', compute_type='int8',
        )
    return _whisper_model


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def extract_audio_task(self, video_id):
    """Извлекает аудиодорожку из видео (ffmpeg -> wav 16 кГц моно).

    Нужна для дальнейшей работы Whisper (ТЗ п. 3.2).
    Статус видео: uploading -> language_detection.
    """
    try:
        video = Video.objects.get(id=video_id)
    except Video.DoesNotExist:
        return

    audio_path = get_audio_path(video.id)
    audio_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            [
                settings.FFMPEG_PATH,
                '-y',                # перезаписать файл, если уже есть
                '-i', str(video.original_file.path),
                '-vn',               # без видеодорожки
                '-ac', '1',          # моно
                '-ar', '16000',      # 16 кГц — формат для Whisper
                str(audio_path),
            ],
            check=True,
            capture_output=True,
        )
    except Exception as exc:
        # После трёх неудачных попыток помечаем видео как ошибочное
        if self.request.retries >= self.max_retries:
            video.status = 'failed'
            video.save(update_fields=['status'])
            return
        raise self.retry(exc=exc)

    video.status = 'language_detection'
    video.save(update_fields=['status'])

    # Сразу запускаем следующий шаг — определение языка и транскрипцию
    detect_language_task.delay(str(video.id))


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def detect_language_task(self, video_id):
    """Определяет язык аудио, делает транскрипцию и сохраняет результат.

    Если MOCK_ML=true — возвращает заглушки (без загрузки модели).
    Статус видео: language_detection -> awaiting_user_choice.
    """
    from .models import Transcript

    try:
        video = Video.objects.get(id=video_id)
    except Video.DoesNotExist:
        return

    audio_path = get_audio_path(video.id)
    if not audio_path.exists():
        if self.request.retries >= self.max_retries:
            video.status = 'failed'
            video.save(update_fields=['status'])
            return
        raise self.retry(exc=FileNotFoundError(f'Аудио не найдено: {audio_path}'))

    try:
        if settings.MOCK_ML:
            # Заглушки для тестов и быстрых прогонов pipeline
            language = 'en'
            confidence = 0.97
            segments = [
                {'start': 0.0, 'end': 2.3, 'text': 'Hello, this is a test transcription.',
                 'speaker_id': 'spk_0'},
            ]
            speakers = {'spk_0': {'gender': 'male', 'confidence': 0.95}}
        else:
            model = get_whisper_model()
            segments_raw, info = model.transcribe(
                str(audio_path), beam_size=5, vad_filter=True,
            )
            language = info.language
            confidence = float(info.language_probability)
            segments = []
            for seg in segments_raw:
                segments.append({
                    'start': float(seg.start),
                    'end': float(seg.end),
                    'text': seg.text.strip(),
                    'speaker_id': 'spk_0',
                })
            speakers = {'spk_0': {'gender': 'unknown', 'confidence': 0.0}}

        # Сохраняем транскрипт (перезаписываем, если уже был)
        Transcript.objects.update_or_create(
            video=video, language=language,
            defaults={'segments': segments, 'speakers': speakers},
        )

        video.detected_language = language
        video.detected_language_confidence = confidence
        video.status = 'awaiting_user_choice'
        video.save(update_fields=['detected_language', 'detected_language_confidence', 'status'])

    except Exception as exc:
        if self.request.retries >= self.max_retries:
            video.status = 'failed'
            video.save(update_fields=['status'])
            return
        raise self.retry(exc=exc)

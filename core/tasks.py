# Фоновые задачи обработки видео
import subprocess
from pathlib import Path

from celery import shared_task
from django.conf import settings

from .models import Video


def get_audio_path(video_id):
    """Путь к извлечённой аудиодорожке (wav 16 кГц моно)."""
    return Path(settings.MEDIA_ROOT) / 'audio' / f'{video_id}.wav'


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

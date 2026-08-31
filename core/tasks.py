# Фоновые задачи обработки видео
import subprocess
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import Job, JobLog, Video

# Кеш модели Whisper, чтобы не грузить её на каждой задаче
_whisper_model = None


def _ws_notify(job_id, event_type, **payload):
    """Отправляет событие в WebSocket-группу job_{id} (ТЗ День 9, игнор ошибок)."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(f'job_{job_id}', {
            'type': event_type, 'job_id': str(job_id), **payload,
        })
    except Exception:
        pass


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

        # Диаризация говорящих (ТЗ День 11) + пол (ТЗ День 12)
        try:
            from .diarization import diarize
            segments, speakers = diarize(audio_path, segments)
            from .gender import detect_gender
            speakers = detect_gender(audio_path, segments, speakers)
        except Exception as e:
            print(f'[detect_language_task] diarization/gender skipped: {e}')

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


@shared_task(bind=True, max_retries=2, default_retry_delay=15)
def process_job_task(self, job_id):
    """Обрабатывает задачу: перевод транскрипта + генерация субтитров (.srt/.vtt).

    Для режима 'dubbing' субтитры тоже создаются (ТЗ п. 2.1/2.2), TTS — в следующих днях.
    Статус задачи: created -> processing -> completed / failed.
    """
    from .subtitles import build_srt, build_vtt
    from .translation import translate_text

    try:
        job = Job.objects.get(id=job_id)
    except Job.DoesNotExist:
        return

    job.status = 'processing'
    job.current_step = 'translating'
    job.started_at = timezone.now()
    job.save(update_fields=['status', 'current_step', 'started_at'])

    video = job.video
    transcript = video.transcripts.order_by('-created_at').first()
    if not transcript:
        job.status = 'failed'
        job.error_message = 'Нет транскрипции для перевода'
        job.save(update_fields=['status', 'error_message'])
        return

    src_lang = transcript.language
    job_dir = Path(settings.MEDIA_ROOT) / 'jobs' / str(job.id)
    job_dir.mkdir(parents=True, exist_ok=True)

    targets = job.target_languages or [src_lang]
    result_files = []

    try:
        for idx, tgt in enumerate(targets, 1):
            log = JobLog.objects.create(job=job, step_name=f'translate_to_{tgt}', status='running',
                                        meta={'source': src_lang})
            if tgt == src_lang:
                # Субтитры на исходном языке без перевода
                translated = list(transcript.segments)
            else:
                translated = []
                total = len(transcript.segments) or 1
                for i, seg in enumerate(transcript.segments):
                    new_text = translate_text(seg.get('text', ''), src_lang, tgt)
                    seg_copy = dict(seg)
                    seg_copy['text'] = new_text
                    translated.append(seg_copy)
                    job.progress_percent = int((idx - 1 + (i + 1) / total) / len(targets) * 90)
                    job.save(update_fields=['progress_percent'])
                    _ws_notify(job.id, 'job_progress', progress_percent=job.progress_percent,
                               current_step=f'translate_to_{tgt}', status='processing')
            log.status = 'success'
            log.save(update_fields=['status'])

            # Субтитры генерируем для обоих режимов
            srt_path = job_dir / f'{tgt}.srt'
            vtt_path = job_dir / f'{tgt}.vtt'
            srt_path.write_text(build_srt(translated), encoding='utf-8')
            vtt_path.write_text(build_vtt(translated), encoding='utf-8')
            result_files.append({'lang': tgt, 'type': 'srt',
                                 'path': srt_path.relative_to(settings.MEDIA_ROOT).as_posix()})
            result_files.append({'lang': tgt, 'type': 'vtt',
                                 'path': vtt_path.relative_to(settings.MEDIA_ROOT).as_posix()})

        job.result_files = result_files
        job.current_step = 'done'
        job.progress_percent = 100
        job.status = 'completed'
        job.finished_at = timezone.now()
        job.save(update_fields=['result_files', 'current_step', 'progress_percent', 'status', 'finished_at'])
        _ws_notify(job.id, 'job_completed', result_files=result_files)
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            job.status = 'failed'
            job.error_message = str(exc)
            job.finished_at = timezone.now()
            job.save(update_fields=['status', 'error_message', 'finished_at'])
            _ws_notify(job.id, 'job_failed', error_message=str(exc))
            return
        raise self.retry(exc=exc)

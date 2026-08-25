# Модели приложения core
import uuid

from django.contrib.auth.models import User
from django.db import models


# Choices

VIDEO_STATUS_CHOICES = (
    ('uploading', 'Загрузка'),
    ('language_detection', 'Определение языка'),
    ('awaiting_user_choice', 'Ожидание выбора режима'),
    ('processing', 'Обработка'),
    ('completed', 'Завершено'),
    ('failed', 'Ошибка'),
)

JOB_STATUS_CHOICES = (
    ('created', 'Создана'),
    ('queued', 'В очереди'),
    ('processing', 'Обрабатывается'),
    ('completed', 'Завершена'),
    ('failed', 'Ошибка'),
    ('cancelled', 'Отменена'),
)

JOB_MODE_CHOICES = (
    ('subtitles', 'Субтитры'),
    ('dubbing', 'Дубляж'),
)

VOICE_MODE_CHOICES = (
    ('clone', 'Клонирование голоса'),
    ('preset_auto', 'Автоподбор пресет-голоса'),
)

STEP_STATUS_CHOICES = (
    ('pending', 'Ожидает'),
    ('running', 'Выполняется'),
    ('success', 'Успешно'),
    ('failed', 'Ошибка'),
)

GENDER_CHOICES = (
    ('male', 'Мужской'),
    ('female', 'Женский'),
)


class Video(models.Model):
    """Видеофайл, загруженный пользователем."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='videos',
                              verbose_name='Владелец')
    original_file = models.FileField(upload_to='videos/%Y/%m/%d/',
                                     verbose_name='Исходный файл')
    duration_seconds = models.PositiveIntegerField(null=True, blank=True,
                                                   verbose_name='Длительность (сек)')
    detected_language = models.CharField(max_length=10, null=True, blank=True,
                                         verbose_name='Определённый язык')
    detected_language_confidence = models.FloatField(null=True, blank=True,
                                                     verbose_name='Уверенность определения языка')
    status = models.CharField(max_length=30, choices=VIDEO_STATUS_CHOICES,
                              default='uploading', verbose_name='Статус')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        verbose_name = 'Видео'
        verbose_name_plural = 'Видео'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.original_file.name} ({self.owner.username})'


class Transcript(models.Model):
    """Транскрипция видео: текст с таймкодами и данными по спикерам."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='transcripts',
                              verbose_name='Видео')
    language = models.CharField(max_length=10, verbose_name='Язык транскрипции')
    # Список сегментов: {start, end, text, speaker_id}
    segments = models.JSONField(default=list, verbose_name='Сегменты')
    # Сводка по спикерам: {speaker_id: {gender, confidence}}
    speakers = models.JSONField(default=dict, verbose_name='Спикеры')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        verbose_name = 'Транскрипция'
        verbose_name_plural = 'Транскрипции'
        ordering = ['-created_at']

    def __str__(self):
        return f'Транскрипция {self.video_id} ({self.language})'


class Job(models.Model):
    """Задача обработки видео: субтитры или дубляж."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='jobs',
                              verbose_name='Видео')
    mode = models.CharField(max_length=20, choices=JOB_MODE_CHOICES, verbose_name='Режим обработки')
    target_languages = models.JSONField(default=list, verbose_name='Целевые языки')
    # Внутренний параметр, пользователем не выбирается — определяется системой автоматически
    voice_mode = models.CharField(max_length=20, choices=VOICE_MODE_CHOICES,
                                  null=True, blank=True, verbose_name='Режим голоса')
    hardsub = models.BooleanField(default=False, verbose_name='Вшить субтитры в видео')
    status = models.CharField(max_length=20, choices=JOB_STATUS_CHOICES,
                              default='created', verbose_name='Статус')
    # Текущий этап внутри processing: transcribing / translating / tts / muxing и т.д.
    current_step = models.CharField(max_length=50, null=True, blank=True,
                                    verbose_name='Текущий этап')
    progress_percent = models.PositiveSmallIntegerField(default=0, verbose_name='Прогресс (%)')
    error_message = models.TextField(null=True, blank=True, verbose_name='Сообщение об ошибке')
    # Ссылки на итоговые файлы: {video_url, srt_url, vtt_url, ...}
    result_files = models.JSONField(null=True, blank=True, verbose_name='Файлы результата')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата запуска')
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата завершения')

    class Meta:
        verbose_name = 'Задача'
        verbose_name_plural = 'Задачи'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.mode} — {self.video_id} ({self.get_status_display()})'


class JobLog(models.Model):
    """Лог этапов обработки задачи (для трассировки pipeline)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='logs',
                            verbose_name='Задача')
    # Название этапа: extract_audio / transcribe / translate / tts / mux и т.д.
    step_name = models.CharField(max_length=50, verbose_name='Этап')
    status = models.CharField(max_length=20, choices=STEP_STATUS_CHOICES,
                              default='pending', verbose_name='Статус этапа')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='Начало этапа')
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name='Конец этапа')
    # Доп. данные: {model, execution_time, ...}
    meta = models.JSONField(default=dict, blank=True, verbose_name='Дополнительно')

    class Meta:
        verbose_name = 'Лог задачи'
        verbose_name_plural = 'Логи задач'
        ordering = ['started_at']

    def __str__(self):
        return f'{self.step_name} ({self.get_status_display()})'

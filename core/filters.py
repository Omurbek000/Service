# Фильтры приложения core
import django_filters

from .models import Job, Video


class VideoFilter(django_filters.FilterSet):
    """Фильтры для списка видео: по статусу обработки."""

    class Meta:
        model = Video
        fields = ('status',)


class JobFilter(django_filters.FilterSet):
    """Фильтры для списка задач: статус, режим, видео."""

    class Meta:
        model = Job
        fields = ('status', 'mode', 'video')

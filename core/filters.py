# Фильтры приложения core
import django_filters

from .models import Video


class VideoFilter(django_filters.FilterSet):
    """Фильтры для списка видео: по статусу обработки."""

    class Meta:
        model = Video
        fields = ('status',)

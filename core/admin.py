# Админ-панель приложения core
from django.contrib import admin
from .models import Job, JobLog, Transcript, Video


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ('id', 'owner', 'original_file', 'status', 'detected_language',
                    'duration_seconds', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('owner__username',)
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(Transcript)
class TranscriptAdmin(admin.ModelAdmin):
    list_display = ('id', 'video', 'language', 'created_at')
    list_filter = ('language',)
    readonly_fields = ('id', 'created_at')


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('id', 'video', 'mode', 'status', 'progress_percent',
                    'voice_mode', 'created_at')
    list_filter = ('mode', 'status', 'hardsub')
    readonly_fields = ('id', 'created_at', 'started_at', 'finished_at')


@admin.register(JobLog)
class JobLogAdmin(admin.ModelAdmin):
    list_display = ('job', 'step_name', 'status', 'started_at', 'finished_at')
    list_filter = ('status', 'step_name')

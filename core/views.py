# Представления приложения core
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView as BaseTokenRefreshView
from rest_framework.views import APIView
from django.http import FileResponse
from .filters import JobFilter, VideoFilter
from .models import Job, Transcript, Video
from .pagination import StandardPagination
from .permissions import IsJobOwner, IsOwner
from .tasks import extract_audio_task, process_job_task
from .serializers import (CustomLoginSerializer, JobCreateSerializer, JobSerializer,
                          RegisterSerializer, UserSerializer, TranscriptSerializer,
                          VideoSerializer, VideoUploadSerializer)


# Авторизация

class RegisterView(generics.CreateAPIView):
    """POST /auth/register/ — регистрация нового пользователя."""

    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = (AllowAny,)


class CustomLoginView(generics.GenericAPIView):
    """POST /auth/login/ — вход, возвращает user + access/refresh токены."""

    serializer_class = CustomLoginSerializer
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TokenRefreshView(BaseTokenRefreshView):
    """POST /auth/token/refresh/ — обновление access-токена (без авторизации)."""

    permission_classes = (AllowAny,)


class LogoutView(generics.GenericAPIView):
    """POST /auth/logout/ — выход: refresh-токен уходит в чёрный список."""

    permission_classes = (AllowAny,)

    def post(self, request):
        try:
            token = RefreshToken(request.data['refresh'])
            token.blacklist()
        except Exception:
            return Response({'detail': 'Невалидный токен'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(generics.RetrieveAPIView):
    """GET /auth/me/ — данные текущего пользователя."""

    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


# Видео

class VideoListCreateView(generics.ListCreateAPIView):
    """GET /videos/ — список видео текущего пользователя (пагинация, фильтр по статусу).
    POST /videos/ — загрузка нового видео (multipart/form-data, поле file)."""

    queryset = Video.objects.all()
    permission_classes = (IsAuthenticated,)
    filterset_class = VideoFilter
    ordering_fields = ('created_at',)

    def get_serializer_class(self):
        # Для загрузки и для списка — разные сериализаторы
        if self.request.method == 'POST':
            return VideoUploadSerializer
        return VideoSerializer

    def get_queryset(self):
        # Видим только свои видео
        return Video.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        video = serializer.save(owner=self.request.user)
        # После загрузки сразу запускаем извлечение аудио (ТЗ п. 3.1)
        extract_audio_task.delay(str(video.id))


class VideoDetailView(generics.RetrieveDestroyAPIView):
    """GET /videos/{id}/ — детали видео.
    DELETE /videos/{id}/ — удаление видео и связанных данных."""

    queryset = Video.objects.all()
    serializer_class = VideoSerializer
    permission_classes = (IsAuthenticated, IsOwner)

    def get_queryset(self):
        # Видим только свои видео (чужие → 404)
        return Video.objects.filter(owner=self.request.user)


class TranscriptPreviewView(generics.RetrieveAPIView):
    """GET /videos/{id}/preview-transcript/ — черновая транскрипция для предпросмотра."""

    serializer_class = TranscriptSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        # Только своё видео, иначе 404
        video = generics.get_object_or_404(Video, pk=self.kwargs['pk'], owner=self.request.user)
        transcript = video.transcripts.order_by('-created_at').first()
        if not transcript:
            from rest_framework.exceptions import NotFound
            raise NotFound('Транскрипция ещё не готова')
        return transcript


class JobListCreateView(generics.ListCreateAPIView):
    """POST /jobs/ — создать задачу (выбор режима пользователем).
    GET /jobs/ — список своих задач (пагинация + фильтры status/mode/video)."""

    permission_classes = (IsAuthenticated,)
    pagination_class = StandardPagination
    filterset_class = JobFilter

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return JobCreateSerializer
        return JobSerializer

    def get_queryset(self):
        return Job.objects.filter(video__owner=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        job = serializer.save()
        # Запускаем обработку в фоне
        process_job_task.delay(str(job.id))


class JobVideoCreateView(generics.CreateAPIView):
    """POST /videos/{id}/jobs/ — алиас для создания задачи по конкретному видео (ТЗ День 8)."""

    serializer_class = JobCreateSerializer
    permission_classes = (IsAuthenticated,)

    def create(self, request, *args, **kwargs):
        video = generics.get_object_or_404(Video, pk=self.kwargs['pk'], owner=request.user)
        data = dict(request.data) if isinstance(request.data, dict) else {}
        data['video'] = str(video.id)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        job = serializer.save()
        process_job_task.delay(str(job.id))
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class JobDetailView(generics.RetrieveDestroyAPIView):
    """GET /jobs/{id}/ — статус и прогресс задачи.
    DELETE /jobs/{id}/ — удаление задачи и её файлов."""

    queryset = Job.objects.all()
    serializer_class = JobSerializer
    permission_classes = (IsAuthenticated, IsJobOwner)

    def get_queryset(self):
        return Job.objects.filter(video__owner=self.request.user)

    def perform_destroy(self, instance):
        # Чистим файлы на диске
        if instance.result_files:
            for f in instance.result_files:
                try:
                    (Path(settings.MEDIA_ROOT) / f['path']).unlink(missing_ok=True)
                except Exception:
                    pass
            # Папка задачи
            try:
                (Path(settings.MEDIA_ROOT) / 'jobs' / str(instance.id)).rmdir()
            except Exception:
                pass
        instance.delete()


class JobResultView(generics.RetrieveAPIView):
    """GET /jobs/{id}/result/ — файлы результата задачи."""

    serializer_class = JobSerializer
    permission_classes = (IsAuthenticated, IsJobOwner)

    def get_queryset(self):
        return Job.objects.filter(video__owner=self.request.user)


class JobCancelView(APIView):
    """POST /jobs/{id}/cancel/ — отменить задачу (created/queued/processing -> cancelled)."""

    permission_classes = (IsAuthenticated,)

    def post(self, request, pk):
        job = generics.get_object_or_404(Job, pk=pk, video__owner=request.user)
        if job.status in ('completed', 'failed', 'cancelled'):
            return Response({'detail': f'Нельзя отменить задачу в статусе {job.status}'},
                            status=status.HTTP_409_CONFLICT)
        job.status = 'cancelled'
        job.current_step = 'cancelled'
        job.save(update_fields=['status', 'current_step'])
        return Response(JobSerializer(job).data, status=status.HTTP_200_OK)


class JobRetryView(APIView):
    """POST /jobs/{id}/retry/ — перезапустить задачу в статусе failed."""

    permission_classes = (IsAuthenticated,)

    def post(self, request, pk):
        job = generics.get_object_or_404(Job, pk=pk, video__owner=request.user)
        if job.status != 'failed':
            return Response({'detail': f'Перезапуск возможен только для статуса failed (сейчас {job.status})'},
                            status=status.HTTP_409_CONFLICT)
        job.status = 'created'
        job.current_step = None
        job.progress_percent = 0
        job.error_message = None
        job.result_files = None
        job.save(update_fields=['status', 'current_step', 'progress_percent',
                                'error_message', 'result_files'])
        process_job_task.delay(str(job.id))
        return Response(JobSerializer(job).data, status=status.HTTP_200_OK)


class SubtitleDownloadView(APIView):
    """GET /jobs/{id}/subtitles/?lang=ru&fmt=srt — скачать субтитры."""

    permission_classes = (IsAuthenticated, IsJobOwner)

    def get(self, request, pk):
        job = generics.get_object_or_404(Job, pk=pk, video__owner=request.user)
        lang = request.query_params.get('lang')
        fmt = (request.query_params.get('fmt') or 'srt').lower()
        if fmt not in ('srt', 'vtt'):
            fmt = 'srt'
        if not job.result_files:
            return Response({'detail': 'Файлы результата ещё не готовы'},
                            status=status.HTTP_404_NOT_FOUND)
        # Ищем нужный файл по языку и формату
        selected = None
        for f in job.result_files:
            if f.get('type') == fmt and (lang is None or f.get('lang') == lang):
                selected = f
                break
        if not selected:
            return Response({'detail': f'Субтитры ({fmt}) для языка {lang} не найдены'},
                            status=status.HTTP_404_NOT_FOUND)
        file_path = Path(settings.MEDIA_ROOT) / selected['path']
        if not file_path.exists():
            return Response({'detail': 'Файл не найден на диске'}, status=status.HTTP_404_NOT_FOUND)
        content_type = 'text/vtt' if fmt == 'vtt' else 'application/x-subrip'
        return FileResponse(open(file_path, 'rb'), content_type=content_type,
                            as_attachment=True, filename=file_path.name)

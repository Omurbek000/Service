# Представления приложения core
from django.contrib.auth.models import User
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView as BaseTokenRefreshView
from .filters import VideoFilter
from .models import Transcript, Video
from .permissions import IsOwner
from .tasks import extract_audio_task
from .serializers import (CustomLoginSerializer, RegisterSerializer, UserSerializer,
                          TranscriptSerializer, VideoSerializer, VideoUploadSerializer)


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

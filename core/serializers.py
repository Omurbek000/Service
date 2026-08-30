# Сериализаторы приложения core
import os

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Job, Transcript, Video


class PayloadTooLarge(APIException):
    """413 — файл превышает лимит (ТЗ День 10)."""

    status_code = 413
    default_detail = 'Файл слишком большой'
    default_code = 'payload_too_large'


# Пользователи

class UserSerializer(serializers.ModelSerializer):
    """Сериализатор данных пользователя (без пароля)."""

    class Meta:
        model = User
        fields = ('id', 'username', 'email')


# Авторизация

class RegisterSerializer(serializers.ModelSerializer):
    """Сериализатор регистрации нового пользователя."""

    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password')

    def validate_username(self, value):
        """Проверяем, что имя пользователя ещё не занято."""
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('Пользователь с таким именем уже существует')
        return value

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


class CustomLoginSerializer(serializers.Serializer):
    """Сериализатор входа: проверяет логин/пароль и выдаёт JWT-токены."""

    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(username=attrs['username'], password=attrs['password'])
        if not user:
            raise serializers.ValidationError('Неверное имя пользователя или пароль')
        # Сохраняем пользователя для to_representation
        self.user = user
        return attrs

    def to_representation(self, instance):
        """Возвращаем данные пользователя и пару токенов access/refresh."""
        refresh = RefreshToken.for_user(self.user)
        return {
            'user': UserSerializer(self.user).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }


# Видео

class VideoSerializer(serializers.ModelSerializer):
    """Сериализатор видео для списка и деталей."""

    class Meta:
        model = Video
        fields = ('id', 'original_file', 'duration_seconds', 'detected_language',
                  'detected_language_confidence', 'status', 'created_at')


class VideoUploadSerializer(serializers.ModelSerializer):
    """Сериализатор загрузки нового видео (multipart, поле file)."""

    file = serializers.FileField(write_only=True)

    class Meta:
        model = Video
        fields = ('id', 'status', 'created_at', 'file')
        read_only_fields = ('id', 'status', 'created_at')

    def validate_file(self, value):
        """Проверяем формат и размер загружаемого файла."""
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in settings.ALLOWED_VIDEO_FORMATS:
            raise serializers.ValidationError(
                f'Формат файла не поддерживается. Разрешены: {", ".join(settings.ALLOWED_VIDEO_FORMATS)}'
            )
        max_mb = settings.VIDEO_MAX_SIZE_MB
        if value.size > max_mb * 1024 * 1024:
            raise PayloadTooLarge(f'Файл слишком большой. Максимум: {max_mb} МБ')
        return value

    def create(self, validated_data):
        file = validated_data.pop('file')
        return Video.objects.create(original_file=file, **validated_data)


class TranscriptSerializer(serializers.ModelSerializer):
    """Сериализатор транскрипции (черновая и итоговая)."""

    class Meta:
        model = Transcript
        fields = ('id', 'video', 'language', 'segments', 'speakers', 'created_at')
        read_only_fields = ('id', 'video', 'created_at')


class JobCreateSerializer(serializers.ModelSerializer):
    """Создание задачи обработки (выбор режима пользователем — ТЗ п. 3.3)."""

    class Meta:
        model = Job
        fields = ('id', 'video', 'mode', 'target_languages', 'hardsub')

    def validate_video(self, value):
        request = self.context['request']
        if value.owner != request.user:
            raise serializers.ValidationError('Видео вам не принадлежит')
        return value


class JobSerializer(serializers.ModelSerializer):
    """Просмотр задачи и её прогресса."""

    class Meta:
        model = Job
        fields = ('id', 'video', 'mode', 'target_languages', 'hardsub', 'status',
                  'current_step', 'progress_percent', 'result_files', 'created_at', 'finished_at')
        read_only_fields = ('id', 'status', 'current_step', 'progress_percent',
                            'result_files', 'created_at', 'finished_at')

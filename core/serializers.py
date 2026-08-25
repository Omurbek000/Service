# Сериализаторы приложения core
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken


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

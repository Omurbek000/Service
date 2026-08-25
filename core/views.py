# Представления приложения core
from django.contrib.auth.models import User
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView as BaseTokenRefreshView
from .serializers import CustomLoginSerializer, RegisterSerializer, UserSerializer


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

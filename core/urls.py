# Маршруты приложения core
from django.urls import path
from .views import CustomLoginView, LogoutView, MeView, RegisterView, TokenRefreshView

urlpatterns = [
    # Авторизация
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', CustomLoginView.as_view(), name='login'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/me/', MeView.as_view(), name='me'),
]

# Маршруты приложения core
from django.urls import path

from .views import (CustomLoginView, LogoutView, MeView, RegisterView,
                    TokenRefreshView, TranscriptPreviewView, VideoDetailView, VideoListCreateView)

urlpatterns = [
    # Авторизация
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', CustomLoginView.as_view(), name='login'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/me/', MeView.as_view(), name='me'),

    # Видео
    path('videos/', VideoListCreateView.as_view(), name='video-list'),
    path('videos/<uuid:pk>/', VideoDetailView.as_view(), name='video-detail'),
    path('videos/<uuid:pk>/preview-transcript/', TranscriptPreviewView.as_view(),
         name='video-preview-transcript'),
]

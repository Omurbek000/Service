# Маршруты приложения core
from django.urls import path

from .views import (CustomLoginView, HealthView, JobCancelView, JobDetailView, JobListCreateView,
                    JobResultView, JobRetryView, JobVideoCreateView, LanguagesView, LogoutView, MeView,
                    RegisterView, SubtitleDownloadView, TokenRefreshView, TranscriptPreviewView,
                    VideoDetailView, VideoListCreateView)

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

    # Служебные
    path('health/', HealthView.as_view(), name='health'),
    path('languages/', LanguagesView.as_view(), name='languages'),

    # Задачи обработки
    path('jobs/', JobListCreateView.as_view(), name='job-list'),
    path('videos/<uuid:pk>/jobs/', JobVideoCreateView.as_view(), name='video-job-create'),
    path('jobs/<uuid:pk>/', JobDetailView.as_view(), name='job-detail'),
    path('jobs/<uuid:pk>/result/', JobResultView.as_view(), name='job-result'),
    path('jobs/<uuid:pk>/cancel/', JobCancelView.as_view(), name='job-cancel'),
    path('jobs/<uuid:pk>/retry/', JobRetryView.as_view(), name='job-retry'),
    path('jobs/<uuid:pk>/subtitles/', SubtitleDownloadView.as_view(), name='job-subtitles'),
]

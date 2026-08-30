"""
ASGI config for voical project — HTTP + WebSocket (ТЗ День 9).
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'voical.settings')

django_asgi_app = get_asgi_application()

# WebSocket маршруты подключаются здесь, чтобы избежать циклических импортов
from core.consumers import JobProgressConsumer  # noqa: E402

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AuthMiddlewareStack(
        URLRouter([
            path('ws/jobs/<uuid:job_id>/', JobProgressConsumer.as_asgi()),
        ])
    ),
})

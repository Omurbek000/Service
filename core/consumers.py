# WebSocket-консьюмер для отслеживания прогресса задачи (ТЗ День 9)
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async

from .models import Job


class JobProgressConsumer(AsyncJsonWebsocketConsumer):
    """
    WS: ws/jobs/{job_id}/  (требует авторизации через query ?token=...)

    Токен передаётся как `?token=<access_token>` (JWT).
    События от Celery: job_progress / job_completed / job_failed.
    """

    async def connect(self):
        # Проверка токена из query string
        query = self.scope.get('query_string', b'').decode()
        token = None
        for part in query.split('&'):
            if part.startswith('token='):
                token = part.split('=',1)[1]
                break
        if not token:
            await self.close(code=4401)
            return

        # Валидация JWT и получение пользователя
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            from django.contrib.auth.models import User
            at = AccessToken(token)
            user_id = at['user_id']
            self.scope['user'] = await database_sync_to_async(
                lambda: User.objects.get(id=user_id)
            )()
        except Exception:
            await self.close(code=4401)
            return

        self.job_id = str(self.scope['url_route']['kwargs']['job_id'])
        self.group_name = f'job_{self.job_id}'

        # Проверка владения задачей
        try:
            job = await database_sync_to_async(
                lambda: Job.objects.select_related('video').get(id=self.job_id, video__owner=self.scope['user'])
            )()
        except Job.DoesNotExist:
            await self.close(code=4404)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Отправляем текущий снимок задачи сразу после подключения
        await self.send_json({
            'type': 'init',
            'job_id': str(job.id),
            'status': job.status,
            'progress_percent': job.progress_percent,
            'current_step': job.current_step,
        })

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # Обработчики событий от channel_layer.group_send
    async def job_progress(self, event):
        await self.send_json({
            'type': 'progress',
            'job_id': event['job_id'],
            'status': event.get('status', 'processing'),
            'progress_percent': event['progress_percent'],
            'current_step': event.get('current_step'),
        })

    async def job_completed(self, event):
        await self.send_json({
            'type': 'completed',
            'job_id': event['job_id'],
            'status': 'completed',
            'progress_percent': 100,
            'result_files': event.get('result_files'),
        })

    async def job_failed(self, event):
        await self.send_json({
            'type': 'failed',
            'job_id': event['job_id'],
            'status': 'failed',
            'error_message': event.get('error_message'),
        })

# Тесты клиента CosyVoice (ТЗ Дни 17-18) — core/cosyvoice_client.py + gpu_worker/server.py
import tempfile
import subprocess
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from core.cosyvoice_client import health_check, is_enabled, synthesize_with_fallback, get_speaker_prompt_path


class HealthCheckTests(SimpleTestCase):
    @override_settings(COSYVOICE_URL='http://fake:50000', COSYVOICE_ENABLED=True)
    @mock.patch('core.cosyvoice_client.httpx.get')
    def test_health_ok(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {'status': 'ok'}
        self.assertTrue(health_check())
        mock_get.assert_called_once()

    @override_settings(COSYVOICE_URL='http://fake:50000', COSYVOICE_ENABLED=True)
    @mock.patch('core.cosyvoice_client.httpx.get')
    def test_health_fail_status(self, mock_get):
        mock_get.return_value.status_code = 500
        mock_get.return_value.text = 'error'
        self.assertFalse(health_check())

    @override_settings(COSYVOICE_URL='http://fake:50000', COSYVOICE_ENABLED=True)
    @mock.patch('core.cosyvoice_client.httpx.get')
    def test_health_exception(self, mock_get):
        mock_get.side_effect = Exception('timeout')
        self.assertFalse(health_check())

    @override_settings(COSYVOICE_URL='', COSYVOICE_ENABLED=False)
    def test_is_enabled_false_when_no_url(self):
        self.assertFalse(is_enabled())

    @override_settings(COSYVOICE_URL='http://fake:50000', COSYVOICE_ENABLED=True)
    def test_is_enabled_true(self):
        self.assertTrue(is_enabled())

    @override_settings(COSYVOICE_URL='http://fake:50000', COSYVOICE_ENABLED=False)
    def test_is_enabled_false_when_disabled(self):
        self.assertFalse(is_enabled())


class SynthesizeWithFallbackTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    @override_settings(COSYVOICE_URL='', COSYVOICE_ENABLED=False, MOCK_ML=True)
    def test_fallback_to_preset_when_disabled(self):
        out = self.tmp / 'out.wav'
        # без воркера должен уйти в пресет (mock тон)
        res, used_clone = synthesize_with_fallback('Привет', 'ru', 'male', out, duration=1.0)
        self.assertTrue(out.exists())
        self.assertFalse(used_clone)

    @override_settings(COSYVOICE_URL='http://fake:50000', COSYVOICE_ENABLED=True, MOCK_ML=True)
    @mock.patch('core.cosyvoice_client.health_check', return_value=False)
    def test_fallback_when_health_false(self, mock_health):
        out = self.tmp / 'out.wav'
        prompt = self.tmp / 'prompt.wav'
        # создаём dummy prompt
        subprocess.run([settings.FFMPEG_PATH, '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.5',
                        '-c:a', 'pcm_s16le', '-ar', '16000', '-ac', '1', str(prompt)], check=True, capture_output=True)
        res, used_clone = synthesize_with_fallback('Hello', 'en', 'male', out, prompt_wav=prompt, prompt_text='hello', duration=1.0)
        self.assertTrue(out.exists())
        self.assertFalse(used_clone)
        mock_health.assert_called_once()

    @override_settings(COSYVOICE_URL='http://fake:50000', COSYVOICE_ENABLED=True, MOCK_ML=True)
    @mock.patch('core.cosyvoice_client.health_check', return_value=True)
    @mock.patch('core.cosyvoice_client.synthesize_zero_shot')
    def test_clone_success(self, mock_synth, mock_health):
        # эмулируем успешный клон — создаём wav
        def fake_synth(text, prompt_wav, prompt_text, out_path, timeout=None):
            subprocess.run([settings.FFMPEG_PATH, '-y', '-f', 'lavfi', '-i', 'sine=frequency=880:duration=1.0',
                            '-c:a', 'pcm_s16le', '-ar', '24000', '-ac', '1', str(out_path)], check=True, capture_output=True)
            return Path(out_path)
        mock_synth.side_effect = fake_synth
        out = self.tmp / 'out.wav'
        prompt = self.tmp / 'prompt.wav'
        subprocess.run([settings.FFMPEG_PATH, '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.5',
                        '-c:a', 'pcm_s16le', '-ar', '16000', '-ac', '1', str(prompt)], check=True, capture_output=True)
        res, used_clone = synthesize_with_fallback('Hello', 'en', 'male', out, prompt_wav=prompt, prompt_text='hello', duration=1.0)
        self.assertTrue(out.exists())
        self.assertTrue(used_clone)
        mock_synth.assert_called_once()

    @override_settings(COSYVOICE_URL='http://fake:50000', COSYVOICE_ENABLED=True, MOCK_ML=True)
    @mock.patch('core.cosyvoice_client.health_check', return_value=True)
    @mock.patch('core.cosyvoice_client.synthesize_zero_shot', side_effect=Exception('gpu error'))
    def test_clone_fail_fallback(self, mock_synth, mock_health):
        out = self.tmp / 'out.wav'
        prompt = self.tmp / 'prompt.wav'
        subprocess.run([settings.FFMPEG_PATH, '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.5',
                        '-c:a', 'pcm_s16le', '-ar', '16000', '-ac', '1', str(prompt)], check=True, capture_output=True)
        res, used_clone = synthesize_with_fallback('Hello', 'en', 'male', out, prompt_wav=prompt, prompt_text='hello', duration=1.0)
        self.assertTrue(out.exists())
        self.assertFalse(used_clone)


class SpeakerPromptCacheTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_extract_and_cache(self):
        # создаём dummy аудио 5 сек
        audio = self.tmp / 'audio.wav'
        subprocess.run([settings.FFMPEG_PATH, '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=5',
                        '-c:a', 'pcm_s16le', '-ar', '16000', '-ac', '1', str(audio)], check=True, capture_output=True)
        segments = [
            {'start': 0.0, 'end': 1.0, 'text': 'a', 'speaker_id': 'spk_0'},
            {'start': 1.0, 'end': 4.0, 'text': 'long segment here', 'speaker_id': 'spk_0'},
            {'start': 4.0, 'end': 5.0, 'text': 'b', 'speaker_id': 'spk_1'},
        ]
        with override_settings(MEDIA_ROOT=self.tmp):
            p1 = get_speaker_prompt_path('vid1', 'spk_0', audio, segments)
            self.assertTrue(p1.exists())
            # второй вызов — из кэша
            p2 = get_speaker_prompt_path('vid1', 'spk_0', audio, segments)
            self.assertEqual(p1, p2)
            # другой спикер — другой файл
            p3 = get_speaker_prompt_path('vid1', 'spk_1', audio, segments)
            self.assertNotEqual(p1, p3)
            self.assertTrue(p3.exists())


class GpuWorkerServerTests(SimpleTestCase):
    """Локальный тест gpu_worker/server.py в mock-режиме (без GPU)."""

    def test_health_endpoint(self):
        from fastapi.testclient import TestClient
        from gpu_worker.server import app
        client = TestClient(app)
        resp = client.get('/health')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'ok')

    def test_zero_shot_mock(self):
        from fastapi.testclient import TestClient
        from gpu_worker.server import app
        client = TestClient(app)
        # создаём dummy prompt wav
        tmp = Path(tempfile.mkdtemp())
        try:
            prompt = tmp / 'prompt.wav'
            subprocess.run([settings.FFMPEG_PATH, '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
                            '-c:a', 'pcm_s16le', '-ar', '16000', '-ac', '1', str(prompt)], check=True, capture_output=True)
            with open(prompt, 'rb') as f:
                resp = client.post('/inference_zero_shot',
                                   data={'tts_text': 'Привет мир', 'prompt_text': 'hello'},
                                   files={'prompt_wav': ('prompt.wav', f, 'audio/wav')})
            self.assertEqual(resp.status_code, 200)
            self.assertGreater(len(resp.content), 1000)
            # контент — wav bytes, должен начинаться с RIFF
            self.assertTrue(resp.content.startswith(b'RIFF'))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

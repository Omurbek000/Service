# Тесты приоритета клонирования (ТЗ День 19) — voice_mode clone vs preset_auto
import tempfile
import subprocess
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from core.cosyvoice_client import is_sample_sufficient, choose_voice_mode


class SampleSufficientTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.audio = self.tmp / 'audio.wav'
        subprocess.run([settings.FFMPEG_PATH, '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=5',
                        '-c:a', 'pcm_s16le', '-ar', '16000', '-ac', '1', str(self.audio)], check=True, capture_output=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    @override_settings(COSYVOICE_SAMPLE_MIN_DURATION=1.5)
    def test_sufficient_long_segment(self):
        segments = [
            {'start': 0.0, 'end': 2.0, 'text': 'long', 'speaker_id': 'spk_0'},
            {'start': 2.0, 'end': 3.0, 'text': 'short', 'speaker_id': 'spk_1'},
        ]
        speakers = {'spk_0': {'gender': 'male', 'confidence': 0.9}, 'spk_1': {'gender': 'female', 'confidence': 0.9}}
        self.assertTrue(is_sample_sufficient('spk_0', self.audio, segments, speakers))
        self.assertFalse(is_sample_sufficient('spk_1', self.audio, segments, speakers))

    @override_settings(COSYVOICE_SAMPLE_MIN_DURATION=1.5)
    def test_insufficient_short(self):
        segments = [{'start': 0.0, 'end': 0.8, 'text': 'hi', 'speaker_id': 'spk_0'}]
        self.assertFalse(is_sample_sufficient('spk_0', self.audio, segments))

    @override_settings(COSYVOICE_SAMPLE_MIN_DURATION=1.5)
    def test_insufficient_no_audio(self):
        segments = [{'start': 0.0, 'end': 2.0, 'text': 'hi', 'speaker_id': 'spk_0'}]
        self.assertFalse(is_sample_sufficient('spk_0', Path('/nonexistent.wav'), segments))

    @override_settings(COSYVOICE_SAMPLE_MIN_DURATION=1.0)
    def test_low_confidence(self):
        segments = [{'start': 0.0, 'end': 2.0, 'text': 'hi', 'speaker_id': 'spk_0'}]
        speakers = {'spk_0': {'gender': 'male', 'confidence': 0.2}}
        self.assertFalse(is_sample_sufficient('spk_0', self.audio, segments, speakers))


class ChooseVoiceModeTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.audio = self.tmp / 'audio.wav'
        subprocess.run([settings.FFMPEG_PATH, '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=5',
                        '-c:a', 'pcm_s16le', '-ar', '16000', '-ac', '1', str(self.audio)], check=True, capture_output=True)
        self.transcript = mock.Mock()
        self.transcript.segments = [{'start': 0.0, 'end': 2.0, 'text': 'hello', 'speaker_id': 'spk_0'}]
        self.transcript.speakers = {'spk_0': {'gender': 'male', 'confidence': 0.9}}

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    @override_settings(COSYVOICE_URL='', COSYVOICE_ENABLED=False)
    def test_disabled_returns_preset(self):
        self.assertEqual(choose_voice_mode(self.transcript, self.audio), 'preset_auto')

    @override_settings(COSYVOICE_URL='http://fake:50000', COSYVOICE_ENABLED=True)
    @mock.patch('core.cosyvoice_client.health_check', return_value=False)
    def test_health_false_returns_preset(self, mock_health):
        self.assertEqual(choose_voice_mode(self.transcript, self.audio), 'preset_auto')

    @override_settings(COSYVOICE_URL='http://fake:50000', COSYVOICE_ENABLED=True, COSYVOICE_SAMPLE_MIN_DURATION=1.5)
    @mock.patch('core.cosyvoice_client.health_check', return_value=True)
    def test_sufficient_returns_clone(self, mock_health):
        self.assertEqual(choose_voice_mode(self.transcript, self.audio), 'clone')

    @override_settings(COSYVOICE_URL='http://fake:50000', COSYVOICE_ENABLED=True, COSYVOICE_SAMPLE_MIN_DURATION=1.5)
    @mock.patch('core.cosyvoice_client.health_check', return_value=True)
    def test_insufficient_returns_preset(self, mock_health):
        self.transcript.segments = [{'start': 0.0, 'end': 0.5, 'text': 'hi', 'speaker_id': 'spk_0'}]
        self.assertEqual(choose_voice_mode(self.transcript, self.audio), 'preset_auto')


class ProcessJobVoiceModeIntegrationTests(SimpleTestCase):
    """Интеграция voice_mode в process_job_task (мок БД)."""

    @override_settings(MOCK_ML=True, MEDIA_ROOT=Path(tempfile.gettempdir()) / 'test_media19',
                       COSYVOICE_URL='http://fake:50000', COSYVOICE_ENABLED=True, COSYVOICE_SAMPLE_MIN_DURATION=1.5)
    @mock.patch('core.tasks.JobLog')
    @mock.patch('core.tasks.Job')
    def test_clone_mode_chosen_when_sufficient(self, mock_job_cls, mock_log_cls):
        tmp = Path(tempfile.mkdtemp())
        try:
            dummy_video = tmp / 'orig.mp4'
            subprocess.run([settings.FFMPEG_PATH, '-y', '-f', 'lavfi', '-i', 'color=c=black:s=320x240:d=4',
                            '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo',
                            '-shortest', '-c:v', 'libx264', '-c:a', 'aac', str(dummy_video)], check=True, capture_output=True)
            # Мок transcript
            mock_transcript = mock.Mock()
            mock_transcript.language = 'en'
            mock_transcript.segments = [
                {'start': 0.0, 'end': 2.0, 'text': 'Hello world long', 'speaker_id': 'spk_0'},
            ]
            mock_transcript.speakers = {'spk_0': {'gender': 'male', 'confidence': 0.9}}
            mock_video = mock.Mock()
            mock_video.id = 'vid-clone-test'
            mock_video.original_file.path = str(dummy_video)
            mock_video.duration_seconds = 4
            mock_video.transcripts.order_by.return_value.first.return_value = mock_transcript
            # аудио для промпта — по пути get_audio_path(video.id)
            audio_path = tmp / 'audio' / f'{mock_video.id}.wav'
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([settings.FFMPEG_PATH, '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=4',
                            '-c:a', 'pcm_s16le', '-ar', '16000', '-ac', '1', str(audio_path)], check=True, capture_output=True)

            mock_job = mock.Mock()
            mock_job.id = 'test-job-id'
            mock_job.video = mock_video
            mock_job.mode = 'dubbing'
            mock_job.target_languages = ['ru']
            mock_job.voice_mode = None
            mock_job.status = 'created'
            mock_job.result_files = None
            mock_job.save = mock.Mock()

            mock_job_cls.objects.get.return_value = mock_job
            mock_log_cls.objects.create.return_value = mock.Mock(status='running', save=lambda **kw: None)

            with override_settings(MEDIA_ROOT=tmp):
                with mock.patch('core.cosyvoice_client.health_check', return_value=True):
                    with mock.patch('core.cosyvoice_client.synthesize_zero_shot') as mock_clone:
                        def fake_clone(text, prompt_wav, prompt_text, out_path, timeout=None):
                            subprocess.run([settings.FFMPEG_PATH, '-y', '-f', 'lavfi', '-i', 'sine=frequency=880:duration=1.0',
                                            '-c:a', 'pcm_s16le', '-ar', '24000', '-ac', '1', str(out_path)], check=True, capture_output=True)
                            return Path(out_path)
                        mock_clone.side_effect = fake_clone
                        from core.tasks import process_job_task
                        process_job_task.run('test-job-id') if hasattr(process_job_task, 'run') else process_job_task('test-job-id')
            # voice_mode должен стать clone
            self.assertEqual(mock_job.voice_mode, 'clone')
            # result_files должен содержать видео
            self.assertIsNotNone(mock_job.result_files)
            types = [f['type'] for f in mock_job.result_files]
            self.assertIn('video', types)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    @override_settings(MOCK_ML=True, MEDIA_ROOT=Path(tempfile.gettempdir()) / 'test_media19',
                       COSYVOICE_URL='', COSYVOICE_ENABLED=False)
    @mock.patch('core.tasks.JobLog')
    @mock.patch('core.tasks.Job')
    def test_preset_mode_when_disabled(self, mock_job_cls, mock_log_cls):
        tmp = Path(tempfile.mkdtemp())
        try:
            dummy_video = tmp / 'orig.mp4'
            subprocess.run([settings.FFMPEG_PATH, '-y', '-f', 'lavfi', '-i', 'color=c=black:s=320x240:d=3',
                            '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo',
                            '-shortest', '-c:v', 'libx264', '-c:a', 'aac', str(dummy_video)], check=True, capture_output=True)
            mock_transcript = mock.Mock()
            mock_transcript.language = 'en'
            mock_transcript.segments = [{'start': 0.0, 'end': 1.0, 'text': 'Hi', 'speaker_id': 'spk_0'}]
            mock_transcript.speakers = {'spk_0': {'gender': 'male', 'confidence': 0.9}}
            mock_video = mock.Mock()
            mock_video.original_file.path = str(dummy_video)
            mock_video.duration_seconds = 3
            mock_video.transcripts.order_by.return_value.first.return_value = mock_transcript
            mock_job = mock.Mock()
            mock_job.id = 'test-job-2'
            mock_job.video = mock_video
            mock_job.mode = 'dubbing'
            mock_job.target_languages = ['ru']
            mock_job.voice_mode = None
            mock_job.status = 'created'
            mock_job.result_files = None
            mock_job.save = mock.Mock()
            mock_job_cls.objects.get.return_value = mock_job
            mock_log_cls.objects.create.return_value = mock.Mock(status='running', save=lambda **kw: None)
            with override_settings(MEDIA_ROOT=tmp):
                from core.tasks import process_job_task
                process_job_task.run('test-job-2') if hasattr(process_job_task, 'run') else process_job_task('test-job-2')
            self.assertEqual(mock_job.voice_mode, 'preset_auto')
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

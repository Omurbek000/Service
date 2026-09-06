# E2E дубляжа без БД (ТЗ День 16) — имитирует ветку dubbing из process_job_task
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from core.audio import get_duration
from core.mux import assemble_dubbed_audio, mux_video
from core.tts import synthesize


class DubbingE2ETest(SimpleTestCase):
    """Полный пайплайн дубляжа: TTS -> time_stretch -> assemble -> mux."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        # подменяем MEDIA_ROOT на временный каталог
        self.media_tmp = self.tmp / 'media'
        self.media_tmp.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_dummy_video(self, path, duration=5.0):
        subprocess.run([
            settings.FFMPEG_PATH, '-y',
            '-f', 'lavfi', '-i', f'color=c=blue:s=320x240:d={duration}',
            '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo',
            '-shortest', '-c:v', 'libx264', '-c:a', 'aac', str(path)
        ], check=True, capture_output=True)

    @override_settings(MOCK_ML=True)
    def test_full_dubbing_pipeline_mock(self):
        # 1. готовим dummy видео
        dummy_video = self.tmp / 'original.mp4'
        self._make_dummy_video(dummy_video, duration=5.0)

        # 2. сегменты как из Transcript
        translated = [
            {'start': 0.0, 'end': 1.5, 'text': 'Привет мир', 'speaker_id': 'spk_0'},
            {'start': 2.0, 'end': 4.0, 'text': 'Как дела', 'speaker_id': 'spk_0'},
        ]
        speakers = {'spk_0': {'gender': 'male', 'confidence': 0.95}}

        job_dir = self.media_tmp / 'jobs' / 'test-job'
        job_dir.mkdir(parents=True)
        tts_dir = job_dir / 'tts' / 'ru'
        tts_dir.mkdir(parents=True)

        # 3. TTS + time_stretch (как в tasks.py:235-260)
        from core.audio import time_stretch
        for i, seg in enumerate(translated):
            spk = seg.get('speaker_id', 'spk_0')
            gender = speakers.get(spk, {}).get('gender', 'male')
            dur = float(seg.get('end', 0)) - float(seg.get('start', 0))
            dur = max(0.5, dur)
            tmp_wav = tts_dir / f'{i:04d}_raw.wav'
            out_wav = tts_dir / f'{i:04d}.wav'
            synthesize(seg.get('text', ''), 'ru', gender, tmp_wav, duration=dur)
            try:
                time_stretch(tmp_wav, out_wav, dur)
                tmp_wav.unlink(missing_ok=True)
            except Exception as e:
                print(f'[time_stretch] {e}')
                tmp_wav.rename(out_wav)
            self.assertTrue(out_wav.exists())
            # длительность после stretch должна совпасть с dur +-0.15
            self.assertAlmostEqual(get_duration(out_wav), dur, delta=0.15)

        # 4. сборка + mux (как в tasks.py:261-277)
        total_dur = 5.0
        dubbed_audio = job_dir / 'ru_dubbed.wav'
        assemble_dubbed_audio(translated, tts_dir, dubbed_audio, total_dur)
        self.assertTrue(dubbed_audio.exists())
        self.assertAlmostEqual(get_duration(dubbed_audio), total_dur, delta=0.1)

        out_video = job_dir / 'ru_dubbed.mp4'
        mux_video(dummy_video, dubbed_audio, out_video)
        self.assertTrue(out_video.exists())
        self.assertGreater(out_video.stat().st_size, 1000)

        # 5. проверяем что result_files логика как в tasks.py
        result_files = []
        result_files.append({'lang': 'ru', 'type': 'video', 'path': out_video.relative_to(self.media_tmp).as_posix()})
        result_files.append({'lang': 'ru', 'type': 'audio', 'path': dubbed_audio.relative_to(self.media_tmp).as_posix()})
        self.assertEqual(len(result_files), 2)
        self.assertEqual(result_files[0]['type'], 'video')
        self.assertTrue(result_files[0]['path'].endswith('_dubbed.mp4'))


class ProcessJobTaskMockTest(SimpleTestCase):
    """Мок-тест process_job_task без реальной БД — проверяет ветку dubbing через patch."""

    @override_settings(MOCK_ML=True, MEDIA_ROOT=Path(tempfile.gettempdir()) / 'test_media')
    @mock.patch('core.tasks.JobLog')
    @mock.patch('core.tasks.Job')
    @mock.patch('core.tasks.Video')
    def test_dubbing_branch_creates_result_files(self, mock_video_cls, mock_job_cls, mock_log_cls):
        # подготавливаем временные файлы
        tmp = Path(tempfile.mkdtemp())
        try:
            # dummy видео
            dummy_video = tmp / 'orig.mp4'
            subprocess.run([
                settings.FFMPEG_PATH, '-y',
                '-f', 'lavfi', '-i', 'color=c=black:s=320x240:d=4',
                '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo',
                '-shortest', '-c:v', 'libx264', '-c:a', 'aac', str(dummy_video)
            ], check=True, capture_output=True)

            # мок transcript
            mock_transcript = mock.Mock()
            mock_transcript.language = 'en'
            mock_transcript.segments = [
                {'start': 0.0, 'end': 1.0, 'text': 'Hello', 'speaker_id': 'spk_0'},
                {'start': 1.5, 'end': 2.5, 'text': 'World', 'speaker_id': 'spk_0'},
            ]
            mock_transcript.speakers = {'spk_0': {'gender': 'male', 'confidence': 0.9}}

            mock_video = mock.Mock()
            mock_video.original_file.path = str(dummy_video)
            mock_video.duration_seconds = 4
            mock_video.transcripts.order_by.return_value.first.return_value = mock_transcript

            mock_job = mock.Mock()
            mock_job.id = 'test-job-id'
            mock_job.video = mock_video
            mock_job.mode = 'dubbing'
            mock_job.target_languages = ['ru']
            mock_job.status = 'created'
            mock_job.result_files = None

            mock_job_cls.objects.get.return_value = mock_job
            mock_log_cls.objects.create.return_value = mock.Mock(status='running', save=lambda **kw: None)

            # Запускаем задачу синхронно (без Celery)
            from core.tasks import process_job_task
            # чтобы MEDIA_ROOT указывал на tmp, патчим settings
            with override_settings(MEDIA_ROOT=tmp):
                # вызываем как обычную функцию, обходя retry
                process_job_task.run('test-job-id') if hasattr(process_job_task, 'run') else process_job_task('test-job-id')

            # проверяем что result_files заполнился видео+аудио + субтитры
            self.assertIsNotNone(mock_job.result_files)
            types = [f['type'] for f in mock_job.result_files]
            self.assertIn('srt', types)
            self.assertIn('vtt', types)
            self.assertIn('video', types)
            self.assertIn('audio', types)
            # проверяем что файлы реально создались
            for f in mock_job.result_files:
                p = tmp / f['path']
                self.assertTrue(p.exists(), f"missing {p}")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

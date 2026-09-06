# Тесты сборки дубляжа (ТЗ День 16) — core/mux.py
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from core.audio import get_duration
from core.mux import assemble_dubbed_audio, mux_video
from core.tts import _synthesize_mock


class AssembleDubbedAudioTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_assemble_places_segments(self):
        tts_dir = self.tmp / 'tts'
        tts_dir.mkdir()
        # два кусочка по 1 сек
        _synthesize_mock('a', tts_dir / '0000.wav', duration=1.0)
        _synthesize_mock('b', tts_dir / '0001.wav', duration=1.0)
        segments = [
            {'start': 0.0, 'end': 1.0, 'text': 'a'},
            {'start': 2.0, 'end': 3.0, 'text': 'b'},
        ]
        out = self.tmp / 'dubbed.wav'
        assemble_dubbed_audio(segments, tts_dir, out, total_duration=5.0, sr=24000)
        self.assertTrue(out.exists())
        dur = get_duration(out)
        self.assertAlmostEqual(dur, 5.0, delta=0.1)

    def test_assemble_normalizes_peak(self):
        # громкий микс не должен клиповать >0.99
        import numpy as np, soundfile as sf
        tts_dir = self.tmp / 'tts'
        tts_dir.mkdir()
        # создаём громкий сигнал
        sr = 24000
        data = np.ones(sr, dtype=np.float32) * 0.9  # 1 сек
        sf.write(str(tts_dir / '0000.wav'), data, sr)
        sf.write(str(tts_dir / '0001.wav'), data, sr)
        segments = [
            {'start': 0.0, 'end': 1.0, 'text': 'a'},
            {'start': 0.0, 'end': 1.0, 'text': 'b'},  # наложатся -> пик 1.8
        ]
        out = self.tmp / 'dubbed.wav'
        assemble_dubbed_audio(segments, tts_dir, out, total_duration=2.0, sr=sr)
        import soundfile as sf2
        mix, _ = sf2.read(str(out))
        self.assertLessEqual(abs(mix).max(), 0.995)


class MuxVideoTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_dummy_video(self, path, duration=3.0):
        subprocess.run([
            settings.FFMPEG_PATH, '-y',
            '-f', 'lavfi', '-i', f'color=c=black:s=320x240:d={duration}',
            '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo',
            '-shortest', '-c:v', 'libx264', '-c:a', 'aac', str(path)
        ], check=True, capture_output=True)

    def test_mux_replaces_audio(self):
        dummy = self.tmp / 'dummy.mp4'
        self._make_dummy_video(dummy, duration=3.0)
        # dubbed audio 3 сек
        dubbed = self.tmp / 'dubbed.wav'
        _synthesize_mock('hello', dubbed, duration=3.0)
        # но assemble даёт 24кГц, а dummy 48кГц — mux должен всё равно сработать
        out = self.tmp / 'out.mp4'
        mux_video(dummy, dubbed, out)
        self.assertTrue(out.exists())
        self.assertGreater(out.stat().st_size, 1000)
        # проверяем длительность видео ~3 сек
        probe = subprocess.run(
            [str(Path(settings.FFMPEG_PATH).with_name('ffprobe.exe')),
             '-v', 'quiet', '-print_format', 'json', '-show_format', str(out)],
            capture_output=True, text=True, check=True
        )
        import json
        info = json.loads(probe.stdout)
        dur = float(info['format']['duration'])
        self.assertAlmostEqual(dur, 3.0, delta=0.3)

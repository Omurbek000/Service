# Тесты time-stretch (ТЗ День 15) — core/audio.py
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from core.audio import _atempo_filter, get_duration, time_stretch
from core.tts import _synthesize_mock


class AtempoFilterTests(SimpleTestCase):
    """Проверка построения цепочки atempo."""

    def test_simple_range(self):
        self.assertEqual(_atempo_filter(1.0), 'atempo=1.0000')
        self.assertEqual(_atempo_filter(0.5), 'atempo=0.5000')
        self.assertEqual(_atempo_filter(2.0), 'atempo=2.0000')
        self.assertEqual(_atempo_filter(1.5), 'atempo=1.5000')

    def test_small_factor_splits(self):
        # 0.25 = 0.5 * 0.5
        filt = _atempo_filter(0.25)
        self.assertEqual(filt, 'atempo=0.5,atempo=0.5000')

    def test_large_factor_splits(self):
        # 4.0 = 2.0 * 2.0
        filt = _atempo_filter(4.0)
        self.assertEqual(filt, 'atempo=2.0,atempo=2.0000')
        # 3.0 = 2.0 * 1.5
        filt = _atempo_filter(3.0)
        self.assertEqual(filt, 'atempo=2.0,atempo=1.5000')

    def test_very_large_factor(self):
        filt = _atempo_filter(8.0)
        # 8 = 2*2*2
        self.assertEqual(filt, 'atempo=2.0,atempo=2.0,atempo=2.0000')


class TimeStretchTests(SimpleTestCase):
    """Реальный ffmpeg-тест подгона длительности."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stretch_no_change_if_close(self):
        # разница <0.05 сек — просто копируем
        raw = self.tmp / 'raw.wav'
        _synthesize_mock('hello', raw, duration=1.0)
        out = self.tmp / 'out.wav'
        time_stretch(raw, out, 1.02)  # diff 0.02
        self.assertTrue(out.exists())
        # длительность должна остаться ~1.0, а не 1.02 (копия)
        dur = get_duration(out)
        self.assertAlmostEqual(dur, 1.0, delta=0.05)

    def test_stretch_speed_up(self):
        raw = self.tmp / 'raw.wav'
        _synthesize_mock('hello', raw, duration=2.0)
        out = self.tmp / 'out.wav'
        time_stretch(raw, out, 1.0)  # ускорить в 2 раза
        self.assertTrue(out.exists())
        dur = get_duration(out)
        self.assertAlmostEqual(dur, 1.0, delta=0.15)

    def test_stretch_slow_down(self):
        raw = self.tmp / 'raw.wav'
        _synthesize_mock('hello', raw, duration=1.0)
        out = self.tmp / 'out.wav'
        time_stretch(raw, out, 2.0)  # замедлить в 2 раза
        self.assertTrue(out.exists())
        dur = get_duration(out)
        self.assertAlmostEqual(dur, 2.0, delta=0.15)

    def test_get_duration(self):
        raw = self.tmp / 'raw.wav'
        _synthesize_mock('test', raw, duration=1.5)
        dur = get_duration(raw)
        self.assertAlmostEqual(dur, 1.5, delta=0.05)

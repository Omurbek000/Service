# E2E субтитров (ТЗ День 7-10) — без БД, через прямые функции
from pathlib import Path
import tempfile

from django.test import SimpleTestCase

from core.subtitles import build_srt, build_vtt
from core.translation import translate_text


class SubtitlesE2ETest(SimpleTestCase):
    def test_build_srt_vtt_and_translate_mock(self):
        segments = [
            {'start': 0.0, 'end': 2.3, 'text': 'Hello world', 'speaker_id': 'spk_0'},
            {'start': 2.5, 'end': 5.0, 'text': 'How are you?', 'speaker_id': 'spk_0'},
        ]
        # перевод mock должен вернуть что-то (не падать)
        translated = []
        for seg in segments:
            new = translate_text(seg['text'], 'en', 'ru')
            c = dict(seg)
            c['text'] = new
            translated.append(c)
        srt = build_srt(translated)
        vtt = build_vtt(translated)
        self.assertIn('00:00:00', srt)
        self.assertIn('WEBVTT', vtt)
        # запись во временные файлы как в tasks.py
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / 'ru.srt').write_text(srt, encoding='utf-8')
            (tmp / 'ru.vtt').write_text(vtt, encoding='utf-8')
            self.assertTrue((tmp / 'ru.srt').exists())
            self.assertTrue((tmp / 'ru.vtt').exists())
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

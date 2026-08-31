# Пул пресет-голосов (ТЗ День 13) — язык × пол, автоподбор
from django.conf import settings

# Базовый пул (mock-данные для MVP, в реале — пути к XTTS/EdgeTTS голосам)
PRESET_VOICES = [
    {'id': 'ru_male_1', 'language': 'ru', 'gender': 'male', 'name': 'Русский Мужской', 'sample': None},
    {'id': 'ru_female_1', 'language': 'ru', 'gender': 'female', 'name': 'Русский Женский', 'sample': None},
    {'id': 'en_male_1', 'language': 'en', 'gender': 'male', 'name': 'English Male', 'sample': None},
    {'id': 'en_female_1', 'language': 'en', 'gender': 'female', 'name': 'English Female', 'sample': None},
    {'id': 'fr_male_1', 'language': 'fr', 'gender': 'male', 'name': 'Français Homme', 'sample': None},
    {'id': 'fr_female_1', 'language': 'fr', 'gender': 'female', 'name': 'Français Femme', 'sample': None},
    {'id': 'de_male_1', 'language': 'de', 'gender': 'male', 'name': 'Deutsch Männlich', 'sample': None},
    {'id': 'de_female_1', 'language': 'de', 'gender': 'female', 'name': 'Deutsch Weiblich', 'sample': None},
    {'id': 'es_male_1', 'language': 'es', 'gender': 'male', 'name': 'Español Hombre', 'sample': None},
    {'id': 'es_female_1', 'language': 'es', 'gender': 'female', 'name': 'Español Mujer', 'sample': None},
    {'id': 'zh_male_1', 'language': 'zh', 'gender': 'male', 'name': '中文 男声', 'sample': None},
    {'id': 'zh_female_1', 'language': 'zh', 'gender': 'female', 'name': '中文 女声', 'sample': None},
    {'id': 'kk_male_1', 'language': 'kk', 'gender': 'male', 'name': 'Қазақ Ер', 'sample': None},
    {'id': 'kk_female_1', 'language': 'kk', 'gender': 'female', 'name': 'Қазақ Әйел', 'sample': None},
]

# Быстрый индекс по (lang, gender)
_VOICE_MAP = {(v['language'], v['gender']): v for v in PRESET_VOICES}


def get_preset_voice(language, gender):
    """Возвращает пресет-голос для языка и пола, с fallback."""
    # точное совпадение
    if (language, gender) in _VOICE_MAP:
        return _VOICE_MAP[(language, gender)]
    # тот же язык, другой пол
    for g in ('male', 'female'):
        if (language, g) in _VOICE_MAP:
            return _VOICE_MAP[(language, g)]
    # тот же пол, любой язык (en как дефолт)
    if ('en', gender) in _VOICE_MAP:
        return _VOICE_MAP[('en', gender)]
    # последний fallback
    return PRESET_VOICES[0]


def list_voices(language=None, gender=None):
    """Фильтрует пул по языку/полу."""
    out = PRESET_VOICES
    if language:
        out = [v for v in out if v['language'] == language]
    if gender:
        out = [v for v in out if v['gender'] == gender]
    return out

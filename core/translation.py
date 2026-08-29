# Перевод текста: провайдеры mock / nllb / google (ТЗ п. 3.4)
from django.conf import settings

# Маппинг ISO 639-1 (выдаёт Whisper) -> FLORES-200 (ожидает NLLB)
LANG_TO_FLORES = {
    'en': 'eng_Latn', 'ru': 'rus_Cyrl', 'fr': 'fra_Latn', 'de': 'deu_Latn',
    'es': 'spa_Latn', 'it': 'ita_Latn', 'pt': 'por_Latn', 'zh': 'zho_Hans',
    'ja': 'jpn_Jpan', 'ko': 'kor_Hang', 'tr': 'tur_Latn', 'ar': 'arb_Arab',
    'kk': 'kaz_Cyrl', 'uz': 'uzn_Latn', 'ky': 'kir_Cyrl', 'be': 'bel_Cyrl',
    'uk': 'ukr_Cyrl', 'pl': 'pol_Latn', 'nl': 'nld_Latn', 'cs': 'ces_Latn',
}

# Ленивый кеш модели NLLB (один раз на процесс воркера)
_nllb = {'tokenizer': None, 'model': None}


def _load_nllb():
    if _nllb['model'] is None:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        name = getattr(settings, 'NLLB_MODEL', 'facebook/nllb-200-distilled-600M')
        _nllb['tokenizer'] = AutoTokenizer.from_pretrained(name)
        _nllb['model'] = AutoModelForSeq2SeqLM.from_pretrained(name)
    return _nllb['tokenizer'], _nllb['model']


def translate_text(text, source, target):
    """Переводит текст с source на target (ISO 639-1)."""
    if not text or not text.strip():
        return text
    provider = settings.TRANSLATE_PROVIDER
    if provider == 'nllb':
        return _translate_nllb(text, source, target)
    if provider == 'google':
        return _translate_google(text, source, target)
    # mock — заглушка по умолчанию
    return _translate_mock(text, source, target)


def _translate_mock(text, source, target):
    return f'[ПЕРЕВОД: {source}->{target}] {text}'


def _translate_nllb(text, source, target):
    tokenizer, model = _load_nllb()
    src = LANG_TO_FLORES.get(source, 'eng_Latn')
    tgt = LANG_TO_FLORES.get(target, 'rus_Cyrl')
    tokenizer.src_lang = src
    inputs = tokenizer(text, return_tensors='pt', truncation=True, max_length=1024)
    out = model.generate(
        **inputs,
        forced_bos_token_id=tokenizer.convert_tokens_to_ids(tgt),
        max_new_tokens=1024,
    )
    return tokenizer.decode(out[0], skip_special_tokens=True)


def _translate_google(text, source, target):
    # Заглушка под будущую реализацию через GOOGLE_API_KEY
    raise NotImplementedError('Google Translate пока не подключён')

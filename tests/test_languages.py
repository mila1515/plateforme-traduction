from pathlib import Path
from types import SimpleNamespace
import json
from io import BytesIO

import pytest
from pypdf import PdfReader
from services.translation import SOURCE_LANGUAGES, LANGUAGES, translate_document
from services.openai_translation import translate_openai_document

PAIRS = [(source, target) for source in SOURCE_LANGUAGES.values() for target in LANGUAGES.values()
         if source != target.split('-')[0]]


@pytest.mark.parametrize('source,target', PAIRS)
def test_deepl_language_pairs(source, target):
    class Client:
        def translate_document_from_filepath(self, input_path, output_path, **kwargs):
            assert kwargs == {'source_lang': source, 'target_lang': target}
            Path(output_path).write_bytes(b'translated')
    assert translate_document(b'input', '.pdf', target, 'fake', client=Client(), source_language=source) == b'translated'


@pytest.mark.parametrize('source,text', [('EN', 'Incident report'), ('ZH', '事件报告')])
def test_openai_to_french(source, text):
    class Client:
        def __init__(self):
            self.responses = self
        def create(self, **kwargs):
            assert f"{'English' if source == 'EN' else 'Simplified Chinese'} text block into French" in kwargs['instructions']
            return SimpleNamespace(status='completed', output_text=json.dumps({'translations': {'block_000': 'Rapport d’incident'}}))
    data = translate_openai_document(b'', '.pdf', 'FR', 'fake', client=Client(), blocks=[text], source_language=source)
    assert 'Rapport d’incident' in PdfReader(BytesIO(data)).pages[0].extract_text()


@pytest.mark.parametrize('source,target', [('FR', 'FR'), ('EN', 'EN-GB'), ('ZH', 'ZH-HANS'), ('ES', 'ES'), ('DE', 'DE')])
def test_same_language_rejected_before_api(source, target):
    with pytest.raises(ValueError, match='différente'):
        translate_document(b'', '.pdf', target, 'fake', source_language=source)
    with pytest.raises(ValueError, match='différente'):
        translate_openai_document(b'', '.pdf', target, 'fake', source_language=source, blocks=['Text'])


@pytest.mark.parametrize('provider', ['GPT (OpenAI)', 'DeepL'])
def test_ui_source_to_french_and_same_language_disabled(monkeypatch, provider):
    import streamlit as st
    import services.translation
    import services.openai_translation
    from streamlit.testing.v1 import AppTest
    sample = Path('examples/rapport_incident_FR.pdf').read_bytes()
    class Upload:
        name = 'report.pdf'
        def getvalue(self):
            return sample
    monkeypatch.setenv('OPENAI_API_KEY', 'fake')
    monkeypatch.setenv('DEEPL_API_KEY', 'fake')
    monkeypatch.setattr(st, 'file_uploader', lambda *a, **kw: [Upload()])
    calls = []
    def translate(*args, **kwargs):
        calls.append((args, kwargs))
        return sample
    monkeypatch.setattr(services.translation, 'translate_document', translate)
    monkeypatch.setattr(services.openai_translation, 'translate_openai_document', translate)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
    app.selectbox[1].select(provider).run()
    app.checkbox[0].check().run()
    app.selectbox[0].select('Français').run()
    assert app.button[0].disabled
    app.selectbox[2].select('Anglais').run()
    assert not app.button[0].disabled
    app.button[0].click().run()
    assert not app.exception
    assert calls[0][0][2] == 'FR'
    assert calls[0][1]['source_language'] == 'EN'
    assert app.session_state['result_source'] == 'Anglais'

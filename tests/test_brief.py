"""Fiche de contexte : oriente terminologie et ton, sans passer avant la fidélité du sens."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import streamlit as st

import services.openai_translation
import services.translation
from services.openai_translation import brief_guidance, translate_openai_document
from services.translation import translate_document

ROOT = Path(__file__).resolve().parents[1]


def test_empty_brief_adds_nothing():
    assert brief_guidance(None) == brief_guidance({'description': '  ', 'tone': None}) == ''


def test_brief_is_bounded_and_subordinate_to_fidelity_rules():
    guidance = brief_guidance({'description': 'Procédure ferroviaire. ' + 'x' * 900, 'tone': 'formal'})
    payload = json.loads(guidance[guidance.index('{'):])
    assert len(payload['description']) == 500
    assert 'vous, Sie, usted' in payload['register']
    assert 'never overrides' in guidance


def test_gpt_receives_the_brief_in_its_instructions():
    class Client:
        def __init__(self):
            self.responses, self.calls = self, []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            blocks = json.loads(kwargs['input'])['blocks']
            return SimpleNamespace(status='completed', output_text=json.dumps(
                {'translations': {key: 'T ' + value for key, value in blocks.items()}, 'doubts': []}))
    client = Client()
    translate_openai_document(b'', '.pdf', 'DE', 'fake', client=client, blocks=['Contrôle du frein.'],
                              brief={'description': '« contrôle » = Prüfung', 'tone': 'formal'})
    assert '« contrôle » = Prüfung' in client.calls[0]['instructions']


@pytest.mark.parametrize('formality,expected', [(None, {}), ('prefer_more', {'formality': 'prefer_more'})])
def test_deepl_receives_formality_only_when_chosen(formality, expected):
    calls = []

    class Client:
        def translate_document_from_filepath(self, source, target, **kwargs):
            calls.append(kwargs)
            Path(target).write_bytes(b'PDF')
    translate_document(b'PDF', '.pdf', 'DE', 'fake', client=Client(), formality=formality)
    assert {key: value for key, value in calls[0].items() if key == 'formality'} == expected


@pytest.mark.parametrize('provider', ['GPT (OpenAI)', 'DeepL'])
def test_interface_sends_brief_and_tone_and_records_them(monkeypatch, provider):
    from streamlit.testing.v1 import AppTest
    sample = (ROOT / 'examples' / 'rapport_incident_FR.pdf').read_bytes()

    class Upload:
        name = 'rapport.pdf'

        def getvalue(self):
            return sample
    calls = []

    def translate(*args, **kwargs):
        calls.append(kwargs)
        return sample
    monkeypatch.setenv('OPENAI_API_KEY', 'fake')
    monkeypatch.setenv('DEEPL_API_KEY', 'fake')
    monkeypatch.setattr(st, 'file_uploader', lambda *a, **kw: [Upload()])
    monkeypatch.setattr(services.translation, 'translate_document', translate)
    monkeypatch.setattr(services.openai_translation, 'translate_openai_document', translate)
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=10).run()
    app.selectbox[1].select(provider).run()
    app.checkbox[0].check().run()
    app.text_area(key='brief_description').input('Procédure de maintenance pour techniciens.').run()
    app.selectbox(key='brief_tone').select('Formel (vouvoiement)').run()
    app.button[0].click().run()
    assert not app.exception
    if provider == 'DeepL':
        assert calls[0]['formality'] == 'prefer_more'
    else:
        assert calls[0]['brief'] == {'description': 'Procédure de maintenance pour techniciens.', 'tone': 'formal'}
    assert app.session_state['results'][0]['quality']['brief']['tone'] == 'formal'

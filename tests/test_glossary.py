"""Vérifier la couverture des langues et les limites du contrôle lexical."""
from copy import deepcopy
from io import BytesIO
import json
from types import SimpleNamespace

from docx import Document
import pytest

from services.glossary import load_glossary, select_pairs, contains_term, prompt_guidance
from services.openai_translation import translate_openai_document
from services.quality import check_translation
from services.review import build_review


@pytest.mark.parametrize('source', ['FR', 'EN', 'ES', 'DE'])
@pytest.mark.parametrize('target', ['FR', 'EN-GB', 'ES', 'DE'])
def test_all_language_pairs_available(source, target):
    glossary = load_glossary()
    pairs = select_pairs(glossary, source, target)
    assert len(pairs) == (0 if source == target.split('-')[0] else 50)
    assert glossary['status'] == 'proposed'
    assert len(glossary['sha256']) == 64


def test_boundaries_and_variants():
    assert not contains_term('transporter', 'porte', 'FR')
    assert contains_term('Un RAPPORT D’INCIDENT.', "rapport d'incident", 'FR')
    pairs = select_pairs(load_glossary(), 'FR', 'ES', 'Les portes sont fermées.')
    assert [pair['id'] for pair in pairs] == ['door']
    assert check_translation('Les portes sont fermées.', 'Las puertas están cerradas.', pairs)['issues'] == []


def test_missing_term_alert_and_prompt_contains_only_relevant_entries():
    pairs = select_pairs(load_glossary(), 'FR', 'EN-GB')
    report = check_translation('Le capteur est prêt.', 'The device is ready.', pairs)
    assert report['checks'] == ['numbers', 'references', 'terminology']
    assert report['issues'][0]['term_id'] == 'sensor'
    guidance = prompt_guidance(pairs, 'Le capteur est prêt.')
    assert 'sensor' in guidance
    assert 'mechanical clearance' not in guidance
    assert prompt_guidance(pairs, 'Bonjour.') == ''


@pytest.mark.parametrize('mutation', ['missing_language', 'duplicate_id', 'conflicting_term', 'fake_approval'])
def test_invalid_glossary_rejected_before_use(tmp_path, mutation):
    document = deepcopy(load_glossary())
    if mutation == 'missing_language':
        del document['entries'][0]['terms']['DE']
    elif mutation == 'duplicate_id':
        document['entries'][1]['id'] = document['entries'][0]['id']
    elif mutation == 'conflicting_term':
        document['entries'][1]['terms']['FR'] = ['porte']
    else:
        document['status'] = 'approved'
    path = tmp_path / 'invalid.json'
    path.write_text(json.dumps(document), encoding='utf-8')
    with pytest.raises(ValueError, match='Glossaire absent ou invalide'):
        load_glossary(path)


def test_openai_receives_preferences_and_report_records_exact_glossary():
    class Client:
        def __init__(self):
            self.responses = self
        def create(self, **kwargs):
            assert 'sensor' in kwargs['instructions']
            assert 'preferred_target' in kwargs['instructions']
            return SimpleNamespace(status='completed', output_text=json.dumps({'translations': {'block_000': 'The sensor is ready.'}}))
    glossary = load_glossary()
    pairs = select_pairs(glossary, 'FR', 'EN-GB')
    result = translate_openai_document(b'', '.docx', 'EN-GB', 'fake', client=Client(),
                                       blocks=['Le capteur est prêt.'], glossary_pairs=pairs)
    assert Document(BytesIO(result)).paragraphs[0].text == 'The sensor is ready.'
    report = build_review(b'', result, '.docx', 'FR', 'EN-GB', 'GPT (OpenAI)',
                          source_blocks=['Le capteur est prêt.'], glossary=glossary)
    assert report['issues'] == []
    assert report['glossary']['sha256'] == glossary['sha256']
    assert report['glossary_usage'] == 'prompt_and_check'


def test_failed_extraction_keeps_glossary_trace_and_no_fake_success():
    report = build_review(b'bad', b'bad', '.docx', 'FR', 'DE', 'DeepL', glossary=load_glossary())
    assert report['status'] == 'unavailable'
    assert report['checks'] == []
    assert report['glossary_usage'] == 'check_only'


@pytest.mark.parametrize('provider', ['GPT (OpenAI)', 'DeepL'])
def test_ui_opt_in_uses_glossary_and_keeps_last_report(monkeypatch, provider):
    import streamlit as st
    import services.openai_translation
    import services.translation
    from streamlit.testing.v1 import AppTest
    from pathlib import Path
    source = Document()
    source.add_paragraph('Le capteur est prêt.')
    buffer = BytesIO()
    source.save(buffer)
    class Upload:
        name = 'sensor.docx'
        def getvalue(self):
            return buffer.getvalue()
    target = Document()
    target.add_paragraph('The device is ready.')
    output = BytesIO()
    target.save(output)
    calls = []
    def translate(*args, **kwargs):
        calls.append(kwargs)
        return output.getvalue()
    monkeypatch.setenv('OPENAI_API_KEY', 'fake')
    monkeypatch.setenv('DEEPL_API_KEY', 'fake')
    monkeypatch.setattr(st, 'file_uploader', lambda *a, **kw: [Upload()])
    monkeypatch.setattr(services.openai_translation, 'translate_openai_document', translate)
    monkeypatch.setattr(services.translation, 'translate_document', translate)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
    assert not app.checkbox(key='use_glossary').value
    app.selectbox[1].select(provider).run()
    app.checkbox[0].check().run()
    app.checkbox(key='use_glossary').check().run()
    app.button[0].click().run()
    assert not app.exception
    report = app.session_state['results'][0]['quality']
    assert report['glossary']['status'] == 'proposed'
    assert report['issues'][0]['term_id'] == 'sensor'
    if provider == 'GPT (OpenAI)':
        assert [pair['id'] for pair in calls[0]['glossary_pairs']] == ['sensor']
    else:
        assert 'glossary_pairs' not in calls[0]
        assert report['glossary_usage'] == 'check_only'
    app.checkbox(key='use_glossary').uncheck().run()
    assert len(calls) == 1
    assert app.session_state['results'][0]['quality'] == report

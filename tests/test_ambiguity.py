"""Ambiguïtés de l'original : appel séparé, facultatif, citations vérifiées, jamais bloquant."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import streamlit as st

import services.ambiguity
import services.openai_translation
from services.ambiguity import find_ambiguities, parse_doubts, schema
from services.review import build_review, readable_alerts

ROOT = Path(__file__).resolve().parents[1]
BLOCKS = ["Fermer la vanne avant l'essai ou après accord du responsable.",
          "Le technicien a informé le chef d'équipe qu'il serait absent demain."]


class Client:
    def __init__(self, doubts, status='completed'):
        self.responses, self.calls, self.doubts, self.status = self, [], doubts, status

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(status=self.status, output_text=json.dumps({'doubts': self.doubts}))


def test_request_sends_only_numbered_source_passages_without_storage():
    client = Client([{'passage': 2, 'quote': "qu'il serait absent", 'note': '« il » : technicien ou chef ?'}])
    doubts = find_ambiguities(BLOCKS, 'FR', 'fake', client=client)
    call = client.calls[0]
    assert json.loads(call['input']) == {'passages': {'1': BLOCKS[0], '2': BLOCKS[1]}}
    assert call['store'] is False and call['model'] == 'gpt-5.4'
    assert 'French' in call['instructions'] and 'not instructions' in call['instructions']
    assert call['text']['format']['schema'] == schema(2)
    assert doubts == [{'passage': 2, 'quote': "qu'il serait absent", 'note': '« il » : technicien ou chef ?'}]


def test_unverifiable_doubts_are_dropped():
    output = json.dumps({'doubts': [
        {'passage': 1, 'quote': 'phrase inventée', 'note': 'x'},
        {'passage': 3, 'quote': 'vanne', 'note': 'x'},
        {'passage': 1, 'quote': 'vanne', 'note': ' '},
        {'passage': 1, 'quote': "« Avant l'essai ou après accord »…", 'note': 'Portée du « ou ».'},
    ]})
    assert parse_doubts(output, BLOCKS) == [
        {'passage': 1, 'quote': "« Avant l'essai ou après accord »…", 'note': 'Portée du « ou ».'}]


@pytest.mark.parametrize('blocks,key', [(['x' * 60_001], 'fake'), (BLOCKS, '')])
def test_refused_before_any_call(blocks, key):
    client = Client([])
    with pytest.raises(ValueError):
        find_ambiguities(blocks, 'FR', key, client=client)
    assert not client.calls


def test_incomplete_response_is_an_error_not_an_empty_result():
    with pytest.raises(ValueError, match='incomplète'):
        find_ambiguities(BLOCKS, 'FR', 'fake', client=Client([], status='incomplete'))


def test_doubts_become_readable_alerts():
    report = build_review(b'', b'', '.pdf', 'FR', 'EN-GB', 'DeepL', source_blocks=BLOCKS,
                          doubts=[{'passage': 2, 'quote': "qu'il serait absent", 'note': '« il » : technicien ou chef ?'}])
    message = readable_alerts(report)[-1]
    assert message.startswith('Passage 2 : formulation ambiguë') and 'technicien ou chef' in message


@pytest.mark.parametrize('failure', [False, True])
def test_interface_runs_the_optional_analysis_and_never_loses_the_translation(monkeypatch, failure):
    from streamlit.testing.v1 import AppTest
    sample = (ROOT / 'examples' / 'rapport_incident_FR.pdf').read_bytes()

    class Upload:
        name = 'rapport.pdf'

        def getvalue(self):
            return sample
    calls = []

    def analyse(blocks, *args, **kwargs):
        calls.append(kwargs)
        if failure:
            raise ValueError('Analyse des ambiguïtés : réponse refusée ou incomplète.')
        return [{'passage': 1, 'quote': blocks[0][:10], 'note': 'Deux lectures.'}]
    monkeypatch.setenv('OPENAI_API_KEY', 'fake')
    monkeypatch.setattr(st, 'file_uploader', lambda *a, **kw: [Upload()])
    monkeypatch.setattr(services.openai_translation, 'translate_openai_document', lambda *a, **kw: sample)
    monkeypatch.setattr(services.ambiguity, 'find_ambiguities', analyse)
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=10).run()
    app.checkbox[0].check().run()
    app.run()
    app.button[0].click().run()
    assert not app.exception and not calls  # Option désactivée par défaut : aucun appel.
    app.checkbox(key='find_ambiguities').check().run()
    app.button[0].click().run()
    assert not app.exception and calls[0]['model'] == 'gpt-5.4'
    result = app.session_state['results'][0]
    assert result['data'] == sample  # La traduction est livrée même si l'analyse échoue.
    assert result['quality']['ambiguity']['error'] == ('Analyse des ambiguïtés : réponse refusée ou incomplète.' if failure else None)
    assert any(issue['category'] == 'ambiguity' for issue in result['quality']['issues']) is not failure

"""Contrat et sécurité des appels d'analyse, sans prouver la qualité du juge."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.semantic_review import review_meaning, parse_review, fingerprint, MAX_REVIEW_TEXT

SOURCE = 'Ne pas ouvrir la porte 3.'
TARGET = 'Open door 3.'


def payload():
    return {'assessment': 'suspected_issues', 'summary': 'Négation potentiellement inversée, à confirmer.',
            'issues': [{'category': 'negation', 'severity': 'critical', 'source_quote': SOURCE,
                        'translation_quote': TARGET, 'explanation': 'Une interdiction devient une instruction.'}]}


class Client:
    def __init__(self, report=None, status='completed'):
        self.responses = self
        self.calls = []
        self.report = report if report is not None else payload()
        self.status = status
    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(status=self.status, output_text=json.dumps(self.report))


def test_explicit_review_records_parameters_and_uses_no_automatic_retry():
    client = Client()
    result = review_meaning(SOURCE, TARGET, 'FR', 'EN-GB', 'fake', client=client)
    assert len(client.calls) == 1
    assert client.calls[0]['store'] is False
    assert client.calls[0]['text']['format']['strict'] is True
    assert json.loads(client.calls[0]['input']) == {'source': SOURCE, 'translation': TARGET}
    assert 'faithful paraphrases' in client.calls[0]['instructions']
    assert result['human_validation_required'] is True
    assert result['pair_sha256'] == fingerprint(SOURCE, TARGET)


@pytest.mark.parametrize('source,target,key', [('', TARGET, 'fake'), (SOURCE, '', 'fake'),
    ('x' * (MAX_REVIEW_TEXT + 1), TARGET, 'fake'), (SOURCE, TARGET, '')])
def test_invalid_input_rejected_before_api(source, target, key):
    client = Client()
    with pytest.raises(ValueError):
        review_meaning(source, target, 'FR', 'EN-GB', key, client=client)
    assert not client.calls


@pytest.mark.parametrize('case', ['invented_quote', 'missing_quote', 'too_long_quote'])
def test_badly_quoted_passage_is_discarded_not_shown(case):
    report = payload()
    if case == 'invented_quote':
        report['issues'][0]['source_quote'] = 'Texte inventé.'
    elif case == 'missing_quote':
        report['issues'][0]['translation_quote'] = ''
    else:
        report['issues'][0]['source_quote'] = SOURCE + ' ' * 400
    result = parse_review(json.dumps(report), SOURCE, TARGET)
    # Problème suspecté mais non localisable : relecture humaine, jamais « aucun problème ».
    assert result['assessment'] == 'inconclusive'
    assert result['issues'] == [] and result['discarded_issues'] == 1


def test_valid_passages_kept_when_another_is_discarded():
    report = payload()
    report['issues'].append({**report['issues'][0], 'source_quote': 'Texte inventé.'})
    result = parse_review(json.dumps(report), SOURCE, TARGET)
    assert result['assessment'] == 'suspected_issues'
    assert len(result['issues']) == 1 and result['discarded_issues'] == 1


def test_quotes_tolerate_typography_case_and_ellipsis():
    source = 'L’opérateur « ne doit pas » ouvrir la porte 3.'
    report = payload()
    report['issues'][0]['source_quote'] = "l'opérateur \"ne doit pas\" ouvrir…"
    result = parse_review(json.dumps(report), source, TARGET)
    assert len(result['issues']) == 1 and result['discarded_issues'] == 0


@pytest.mark.parametrize('case', ['contradictory_status', 'unknown_category', 'invalid_json'])
def test_unreliable_response_rejected(case):
    report = payload()
    if case == 'contradictory_status':
        report['assessment'] = 'no_issue_detected'
    elif case == 'unknown_category':
        report['issues'][0]['category'] = 'approved'
    output = 'not-json' if case == 'invalid_json' else json.dumps(report)
    with pytest.raises(ValueError, match='réponse invalide'):
        parse_review(output, SOURCE, TARGET)


def test_refusal_or_truncation_is_not_presented_as_success():
    client = Client(status='incomplete')
    with pytest.raises(ValueError, match='incomplète'):
        review_meaning(SOURCE, TARGET, 'FR', 'EN-GB', 'fake', client=client)
    assert len(client.calls) == 1


@pytest.mark.parametrize('assessment', ['no_issue_detected', 'inconclusive'])
def test_no_findings_do_not_approve_translation(assessment):
    client = Client({'assessment': assessment, 'summary': 'Avis indicatif à confirmer.', 'issues': []})
    report = review_meaning(SOURCE, TARGET, 'FR', 'EN-GB', 'fake', client=client)
    assert report['human_validation_required']
    assert 'approved' not in report


def test_ui_requires_separate_consent_and_does_not_repeat_paid_analysis(monkeypatch):
    import services.semantic_review
    from streamlit.testing.v1 import AppTest
    calls = []
    def fake_review(*args, **kwargs):
        calls.append((args, kwargs))
        return {**payload(), 'provider': 'OpenAI', 'model': 'test', 'human_validation_required': True}
    monkeypatch.setenv('OPENAI_API_KEY', 'fake')
    monkeypatch.setattr(services.semantic_review, 'review_meaning', fake_review)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=10)
    app.session_state['results'] = [{'name': 'example.pdf', 'data': b'PDF', 'suffix': '.pdf', 'error': None,
        'quality': {'status': 'review_required', 'issues': [], 'limitations': 'À relire.',
                    'source_language': 'FR', 'target_language': 'EN-GB'},
        'comparison': {'available': True, 'source': SOURCE, 'translation': TARGET}}]
    app.session_state['result_language'] = 'Anglais britannique'
    app.session_state['result_provider'] = 'DeepL'
    app.session_state['result_source'] = 'Français'
    app.run()
    pair = fingerprint(SOURCE, TARGET)
    assert app.button(key=f'semantic_run_0_{pair}').disabled
    app.checkbox(key=f'semantic_consent_0_{pair}').check().run()
    assert not calls  # Consentir seul ne lance rien.
    app.button(key=f'semantic_run_0_{pair}').click().run()
    assert not app.exception
    assert len(calls) == 1
    app.run()
    assert app.button(key=f'semantic_run_0_{pair}').disabled
    assert len(calls) == 1
    app.selectbox(key='provider').select('DeepL').run()
    assert len(calls) == 1


def test_long_document_is_reviewed_in_parts_and_verdicts_are_combined():
    from services.semantic_review import review_document, chunks
    pairs = [(f'Phrase source {index}. ' + 'x' * 2900, f'Source sentence {index}. ' + 'y' * 2900) for index in range(5)]
    assert [len(group) for group in chunks(pairs)] == [2, 2, 1]  # ≈ 6 000 caractères par partie.
    verdicts = iter([{'assessment': 'no_issue_detected', 'summary': 'Rien.', 'issues': []},
                     {'assessment': 'suspected_issues', 'summary': 'Négation.', 'discarded_issues': 1,
                      'issues': [{'category': 'negation', 'severity': 'critical', 'source_quote': 'a',
                                  'translation_quote': 'b', 'explanation': 'Inversée.'}]},
                     {'assessment': 'inconclusive', 'summary': 'Doute.', 'issues': []}])
    calls = []

    class Client:
        def __init__(self):
            self.responses = self

        def create(self, **kwargs):
            calls.append(json.loads(kwargs['input']))
            verdict = next(verdicts)
            return SimpleNamespace(status='completed', output_text=json.dumps(
                {key: verdict[key] for key in ('assessment', 'summary', 'issues')}))
    import services.semantic_review as module
    original = module.parse_review
    module.parse_review = lambda output, source, translation: {**json.loads(output), 'discarded_issues': 0}
    try:
        report = review_document(pairs, 'FR', 'EN-GB', 'fake', client=Client())
    finally:
        module.parse_review = original
    assert len(calls) == 3 and calls[2]['source'].startswith('Phrase source 4.')
    assert report['assessment'] == 'suspected_issues' and report['parts'] == 3
    assert report['issues'][0]['part'] == 2 and report['summary'].startswith('Partie 1/3 : Rien.')
    assert report['human_validation_required'] is True


def test_passage_longer_than_one_call_is_refused_before_sending():
    from services.semantic_review import review_document
    client = Client()
    with pytest.raises(ValueError, match='dépasse'):
        review_document([('x' * (MAX_REVIEW_TEXT + 1), 'y')], 'FR', 'EN-GB', 'fake', client=client)
    assert not client.calls


@pytest.mark.parametrize('source,translation,passages,expected', [
    ('A\nB', 'X\nY', None, [('A', 'X'), ('B', 'Y')]),                        # DeepL : paragraphes appariés.
    ('A\nB', 'X Y', None, [('A\nB', 'X Y')]),                                 # Court : texte entier.
    ('A\n' + 'x' * 13_000, 'X', None, None),                                  # Long et non apparié : refus.
    ('ignoré', 'ignoré', [('A', 'X')], [('A', 'X')]),                         # GPT : passages exacts.
])
def test_meaning_pairs(source, translation, passages, expected):
    from services.semantic_review import meaning_pairs
    assert meaning_pairs(source, translation, passages) == expected


def test_automatic_meaning_check_runs_after_translation_only_when_chosen(monkeypatch):
    import streamlit as st
    import services.openai_translation
    from streamlit.testing.v1 import AppTest
    sample = (Path(__file__).resolve().parents[1] / 'examples' / 'rapport_incident_FR.pdf').read_bytes()

    class Upload:
        name = 'rapport.pdf'

        def getvalue(self):
            return sample
    calls = []

    def fake_review(pairs, *args, **kwargs):
        calls.append(pairs)
        return {**payload(), 'parts': 1, 'model': kwargs['model'], 'human_validation_required': True}

    def translate(*args, **kwargs):
        kwargs['passages'].extend([(SOURCE, TARGET)])
        return sample
    monkeypatch.setenv('OPENAI_API_KEY', 'fake')
    monkeypatch.setattr(st, 'file_uploader', lambda *a, **kw: [Upload()])
    monkeypatch.setattr(services.openai_translation, 'translate_openai_document', translate)
    monkeypatch.setattr(services.semantic_review, 'review_document', fake_review)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=10).run()
    app.checkbox[0].check().run()
    app.button(key='translate').click().run()
    assert not app.exception and not calls  # Option décochée par défaut.
    app.checkbox(key='check_meaning').check().run()
    app.button(key='translate').click().run()
    assert not app.exception and calls == [[(SOURCE, TARGET)]]
    assert app.session_state['results'][0]['semantic_review']['assessment'] == 'suspected_issues'

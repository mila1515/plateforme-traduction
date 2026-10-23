"""Pages de relecture : décisions enregistrées sans toucher aux traductions, glossaire validé avec trace."""
from datetime import date
import json
from pathlib import Path
import shutil

import pytest
from streamlit.testing.v1 import AppTest

from services.glossary import DEFAULT_PATH, load_glossary, set_review_status
from services.trials import evaluate, list_trials, review_summary, save_review

ROOT = Path(__file__).resolve().parents[1]
CORPUS = [{'id': 'C01', 'source': 'Ne pas ouvrir la porte 3.', 'focus': 'négation'},
          {'id': 'C02', 'source': 'Porte 3 fermée.', 'focus': 'nombres'}]


def make_trial(directory):
    trial = {'metadata': {'provider': 'GPT (OpenAI)', 'source_language': 'FR', 'target_language': 'EN-GB'},
             'results': [{'id': 'C01', 'source': CORPUS[0]['source'], 'translation': 'Open door 3.',
                          'human_decision': 'pending', 'reviewer': '', 'review_notes': ''},
                         {'id': 'C02', 'source': CORPUS[1]['source'], 'translation': 'Door 4 closed.',
                          'human_decision': 'pending', 'reviewer': '', 'review_notes': ''}]}
    path = directory / 'essai.json'
    path.write_text(json.dumps(trial, ensure_ascii=False), encoding='utf-8')
    (directory / 'essai-report.json').write_text(json.dumps({'results': [{'id': 'C01', 'control': {}}]}), encoding='utf-8')
    (directory / 'corpus.json').write_text(json.dumps(CORPUS, ensure_ascii=False), encoding='utf-8')
    return path


def test_only_trials_are_listed_not_reports_or_corpus(tmp_path):
    path = make_trial(tmp_path)
    assert list_trials(tmp_path) == [path]
    assert list_trials(tmp_path / 'absent') == []


def test_review_changes_only_decision_fields(tmp_path):
    path = make_trial(tmp_path)
    before = json.loads(path.read_text(encoding='utf-8'))
    changed = save_review(path, {'C01': {'human_decision': 'rejected', 'review_notes': 'Négation inversée.'},
                                 'C02': {'human_decision': 'accepted', 'review_notes': ''}}, 'Réviseur bilingue')
    after = json.loads(path.read_text(encoding='utf-8'))
    assert changed == 2
    assert [r['translation'] for r in after['results']] == [r['translation'] for r in before['results']]
    assert after['results'][0]['reviewer'] == 'Réviseur bilingue' and after['results'][0]['reviewed_at']
    assert after['results'][1]['human_decision'] == 'accepted'
    assert sorted(item.name for item in tmp_path.iterdir()) == ['corpus.json', 'essai-report.json', 'essai.json']


@pytest.mark.parametrize('decisions,reviewer,message', [
    ({'C01': {'human_decision': 'rejected', 'review_notes': ''}}, 'R', 'note'),
    ({'C01': {'human_decision': 'accepted', 'review_notes': ''}}, ' ', 'réviseur'),
])
def test_invalid_review_writes_nothing(tmp_path, decisions, reviewer, message):
    path = make_trial(tmp_path)
    before = path.read_text(encoding='utf-8')
    with pytest.raises(ValueError, match=message):
        save_review(path, decisions, reviewer)
    assert path.read_text(encoding='utf-8') == before


def test_summary_crosses_decisions_and_automatic_alerts(tmp_path):
    path = make_trial(tmp_path)
    save_review(path, {'C01': {'human_decision': 'rejected', 'review_notes': 'Négation inversée.'},
                       'C02': {'human_decision': 'rejected', 'review_notes': 'Mauvais numéro.'}}, 'R')
    report = evaluate(CORPUS, json.loads(path.read_text(encoding='utf-8')))
    # C01 : la négation perdue est signalée par passage ; C02 : nombre modifié.
    assert review_summary(report) == {'rejected_with_alert': 2, 'rejected_without_alert': 0,
                                      'accepted_with_alert': 0, 'accepted_without_alert': 0, 'pending': 0}


def test_review_page_saves_decisions(monkeypatch, tmp_path):
    path = make_trial(tmp_path)
    monkeypatch.setenv('EVALUATION_RUNS_PATH', str(tmp_path))
    monkeypatch.setenv('EVALUATION_CORPUS_PATH', str(tmp_path / 'corpus.json'))
    app = AppTest.from_file(str(ROOT / 'pages' / '1_Relecture_des_essais.py'), default_timeout=20).run()
    assert not app.exception
    assert any('négation' in warning.value for warning in app.warning)  # Alerte automatique affichée.
    app.text_input(key='reviewer').input('Réviseur bilingue').run()
    # Dans un formulaire, les saisies partent ensemble au clic sur « Enregistrer ».
    app.radio(key='decision_essai_C01').set_value('rejected')
    app.text_area(key='notes_essai_C01').input('Négation inversée.')
    app.button(key='save_review').click().run()
    assert not app.exception and not app.error
    assert json.loads(path.read_text(encoding='utf-8'))['results'][0]['human_decision'] == 'rejected'
    assert any('1 décision' in message.value for message in app.success)


def test_review_page_explains_when_no_trial(monkeypatch, tmp_path):
    monkeypatch.setenv('EVALUATION_RUNS_PATH', str(tmp_path))
    app = AppTest.from_file(str(ROOT / 'pages' / '1_Relecture_des_essais.py'), default_timeout=20).run()
    assert not app.exception and 'Aucun essai' in app.info[0].value


def test_glossary_approval_keeps_terms_and_can_be_reverted(tmp_path):
    path = tmp_path / 'technical.json'
    shutil.copy(DEFAULT_PATH, path)
    original = load_glossary(path)
    with pytest.raises(ValueError, match='nom'):
        set_review_status(path, 'approved', ' ')
    approved = set_review_status(path, 'approved', 'Responsable maintenance', date(2026, 10, 23))
    assert (approved['status'], approved['reviewed_by'], approved['reviewed_at']) == \
        ('approved', 'Responsable maintenance', '2026-10-23')
    assert approved['entries'] == original['entries']
    reverted = set_review_status(path, 'proposed')
    assert (reverted['status'], reverted['reviewed_by']) == ('proposed', None)


def test_glossary_page_requires_confirmation_then_approves(monkeypatch, tmp_path):
    path = tmp_path / 'technical.json'
    shutil.copy(DEFAULT_PATH, path)
    monkeypatch.setenv('GLOSSARY_PATH', str(path))
    app = AppTest.from_file(str(ROOT / 'pages' / '2_Validation_du_glossaire.py'), default_timeout=20).run()
    assert not app.exception
    app.text_input[1].input('Responsable maintenance')
    app.button(key='approve_glossary').click().run()
    assert 'confirmation' in app.error[0].value and load_glossary(path)['status'] == 'proposed'
    app.text_input[1].input('Responsable maintenance')
    app.checkbox[0].check()
    app.button(key='approve_glossary').click().run()
    assert not app.exception and load_glossary(path)['reviewed_by'] == 'Responsable maintenance'
    assert 'validée par Responsable maintenance' in app.success[0].value

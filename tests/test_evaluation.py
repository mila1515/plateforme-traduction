import pytest
import json
from pathlib import Path
from evaluation.run import evaluate
from services.glossary import load_glossary


def test_pilot_corpus_has_thirty_distinct_cases():
    corpus = json.loads((Path(__file__).resolve().parents[1] / 'evaluation' / 'corpus.json').read_text(encoding='utf-8'))
    assert len(corpus) == len({case['id'] for case in corpus}) == 30
    assert all(case['source'].strip() and case['focus'].strip() for case in corpus)


def test_trial_reports_missing_cases_alerts_and_pending_review():
    corpus = [{'id': 'one', 'source': 'RN 204 : porte 3'}, {'id': 'two', 'source': 'Ne pas ouvrir.'}]
    report = evaluate(corpus, {'results': [{'id': 'one', 'translation': 'RN 204: door 4'}]})
    assert report['missing_ids'] == ['two']
    assert report['cases_with_alerts'] == 1
    assert report['human_decisions'] == {'pending': 1}


@pytest.mark.parametrize('results', [
    [{'id': 'one', 'translation': ''}],
    [{'id': 'other', 'translation': 'text'}],
    [{'id': 'one', 'translation': 'text'}] * 2,
    [{'id': 'one', 'translation': 'text', 'human_decision': 'accepted'}],
])
def test_invalid_evidence_rejected(results):
    with pytest.raises(ValueError):
        evaluate([{'id': 'one', 'source': 'texte'}], {'results': results})


def test_documented_human_review_kept_separate_from_automatic_checks():
    report = evaluate([{'id': 'one', 'source': 'Ne pas ouvrir la porte 3.'}], {
        'metadata': {'provider': 'manual-test'},
        'results': [{'id': 'one', 'translation': 'Open door 3.', 'human_decision': 'rejected',
                     'reviewer': 'Bilingual reviewer', 'review_notes': 'Négation inversée.'}]})
    assert report['cases_with_alerts'] == 0
    assert report['human_decisions'] == {'rejected': 1}


def test_optional_glossary_requires_languages_and_reports_missing_term():
    corpus = [{'id': 'sensor', 'source': 'Le capteur est prêt.'}]
    trial = {'results': [{'id': 'sensor', 'translation': 'The device is ready.'}]}
    glossary = load_glossary()
    with pytest.raises(ValueError, match='langues source et cible'):
        evaluate(corpus, trial, glossary=glossary)
    trial['metadata'] = {'source_language': 'FR', 'target_language': 'EN-GB'}
    report = evaluate(corpus, trial, glossary=glossary)
    assert report['results'][0]['control']['issues'][0]['term_id'] == 'sensor'
    assert report['control_glossary']['sha256'] == glossary['sha256']

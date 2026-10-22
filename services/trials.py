"""Essais réels : relecture humaine des traductions et bilan face aux alertes automatiques.

Les fichiers d'essai (``evaluation/runs``, ignoré par Git) contiennent les
traductions obtenues ; la relecture ne modifie que les champs de décision,
jamais la traduction enregistrée.
"""
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from services.glossary import select_pairs
from services.passages import check_passages
from services.quality import check_translation

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / 'evaluation' / 'runs'
CORPUS_PATH = ROOT / 'evaluation' / 'corpus.json'
DECISIONS = ('pending', 'accepted', 'rejected')


def evaluate(corpus, trial, glossary=None):
    """Séparer alertes locales et décisions humaines, avec glossaire optionnel."""
    metadata = trial.get('metadata', {})
    if glossary is not None and not all(metadata.get(key) for key in ('source_language', 'target_language')):
        raise ValueError('Les langues source et cible sont nécessaires au contrôle du glossaire.')
    expected = {case['id']: case for case in corpus}
    if len(expected) != len(corpus):
        raise ValueError('Identifiants du corpus dupliqués.')
    results = trial['results']
    ids = [result['id'] for result in results]
    if len(ids) != len(set(ids)) or set(ids) - set(expected):
        raise ValueError('Identifiants de résultats dupliqués ou inconnus.')
    rows = []
    for result in results:
        if not isinstance(result.get('translation'), str) or not result['translation'].strip():
            raise ValueError('Chaque résultat fourni doit contenir une traduction non vide.')
        decision = result.get('human_decision', 'pending')
        if decision not in ('pending', 'accepted', 'rejected'):
            raise ValueError('Décision humaine invalide.')
        if decision != 'pending' and not result.get('reviewer'):
            raise ValueError('Une décision exige le nom du réviseur.')
        if decision == 'rejected' and not result.get('review_notes'):
            raise ValueError('Un rejet exige une note expliquant l’erreur.')
        rows.append({'id': result['id'], 'human_decision': decision,
                     'reviewer': result.get('reviewer'), 'review_notes': result.get('review_notes'),
                     'control': check_translation(expected[result['id']]['source'], result['translation'],
                         glossary_pairs=select_pairs(glossary, metadata['source_language'], metadata['target_language'])
                         if glossary is not None else None),
                     # Indices de l'application (négation, obligation, longueur…), à confronter à la relecture.
                     'passage_alerts': [{key: value for key, value in issue.items() if key not in ('category', 'passage', 'excerpt')}
                                        for issue in check_passages([(expected[result['id']]['source'], result['translation'])],
                                                                    metadata['source_language'], metadata['target_language'])]
                     if metadata.get('source_language') and metadata.get('target_language') else None})
    decisions = Counter(row['human_decision'] for row in rows)
    return {'metadata': metadata,
            'control_glossary': None if glossary is None else {key: glossary[key] for key in ('id', 'version', 'status', 'sha256')},
            'expected': len(corpus), 'received': len(rows),
            'missing_ids': sorted(set(expected) - set(ids)),
            'cases_with_alerts': sum(bool(row['control']['issues']) for row in rows),
            'cases_with_passage_alerts': sum(bool(row['passage_alerts']) for row in rows),
            'human_decisions': dict(decisions), 'results': rows,
            'notice': 'Aucun score linguistique automatique. Les décisions humaines sont déclarées, non vérifiées par cet outil.'}


def is_trial(data):
    """Un essai à relire, pas un rapport : chaque résultat a une traduction et une décision."""
    results = data.get('results') if isinstance(data, dict) else None
    return (isinstance(results, list) and bool(results)
            and all(isinstance(item, dict) and 'translation' in item and 'human_decision' in item
                    and 'control' not in item for item in results))


def list_trials(directory=RUNS_DIR):
    trials = []
    for path in sorted(Path(directory).glob('*.json')) if Path(directory).is_dir() else []:
        try:
            if is_trial(json.loads(path.read_text(encoding='utf-8'))):
                trials.append(path)
        except (OSError, ValueError):
            continue
    return trials


def load_trial(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save_review(path, decisions, reviewer):
    """Enregistrer les décisions modifiées ; renvoie le nombre de cas changés.

    Seuls ``human_decision``, ``reviewer``, ``review_notes`` et ``reviewed_at``
    changent. Tout est vérifié avant l'écriture, qui est atomique.
    """
    trial = load_trial(path)
    reviewer = (reviewer or '').strip()
    changed, missing = 0, []
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    for result in trial['results']:
        decision = decisions.get(result['id'])
        if decision is None:
            continue
        status, notes = decision['human_decision'], decision['review_notes'].strip()
        if status not in DECISIONS:
            raise ValueError(f"Décision invalide pour {result['id']}.")
        if (status, notes) == (result['human_decision'], (result.get('review_notes') or '').strip()):
            continue
        if status != 'pending' and not reviewer:
            raise ValueError('Indiquez votre nom de réviseur avant d’enregistrer une décision.')
        if status == 'rejected' and not notes:
            missing.append(result['id'])
        result.update({'human_decision': status, 'review_notes': notes,
                       'reviewer': reviewer if status != 'pending' else '',
                       'reviewed_at': now if status != 'pending' else ''})
        changed += 1
    if missing:
        raise ValueError('Un rejet exige une note expliquant l’erreur : ' + ', '.join(missing) + '.')
    if changed:
        handle, temporary = tempfile.mkstemp(dir=Path(path).parent, prefix='.essai_', suffix='.json')
        try:
            with os.fdopen(handle, 'w', encoding='utf-8') as stream:
                json.dump(trial, stream, ensure_ascii=False, indent=2)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
    return changed


def review_summary(report):
    """Croiser décisions humaines et alertes automatiques (contrôles locaux et par passage)."""
    summary = Counter()
    for row in report['results']:
        alerted = bool(row['control']['issues']) or bool(row['passage_alerts'])
        summary[(row['human_decision'], alerted)] += 1
    return {'rejected_with_alert': summary[('rejected', True)],
            'rejected_without_alert': summary[('rejected', False)],
            'accepted_with_alert': summary[('accepted', True)],
            'accepted_without_alert': summary[('accepted', False)],
            'pending': summary[('pending', True)] + summary[('pending', False)]}

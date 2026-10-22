"""Prepare or audit a real translation trial without calling a provider."""
import argparse
from collections import Counter
import json
from pathlib import Path

from services.passages import check_passages
from services.quality import check_translation
from services.glossary import load_glossary, select_pairs


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
        if decision != 'pending' and not all(result.get(key) for key in ('reviewer', 'review_notes')):
            raise ValueError('Une décision exige un réviseur et des notes de relecture.')
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=Path(__file__).with_name('corpus.json'))
    parser.add_argument('--trial', type=Path, help='Résultats réels à contrôler (JSON).')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--glossary', type=Path, help='Glossaire JSON pour le contrôle terminologique local.')
    args = parser.parse_args()
    corpus = json.loads(args.corpus.read_text(encoding='utf-8'))
    if args.trial:
        output = evaluate(corpus, json.loads(args.trial.read_text(encoding='utf-8')),
                          glossary=load_glossary(args.glossary) if args.glossary else None)
    else:
        output = {'metadata': {'provider': '', 'model': '', 'date': '', 'prompt_version': '',
                               'source_language': 'FR', 'target_language': 'EN-GB',
                               'cost_eur': None, 'duration_seconds': None},
                  'results': [{'id': case['id'], 'source': case['source'], 'translation': '',
                               'human_decision': 'pending', 'reviewer': '', 'review_notes': ''} for case in corpus]}
    # Prevent accidental overwriting of collected evidence.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(output, stream, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()

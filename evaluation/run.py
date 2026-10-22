"""Prepare or audit a real translation trial without calling a provider."""
import argparse
import json
from pathlib import Path

from services.glossary import load_glossary
from services.trials import evaluate


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

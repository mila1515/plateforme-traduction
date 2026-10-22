"""Traduire le corpus avec un vrai moteur et préparer le formulaire de relecture.

Appel payant : exige --confirm. GPT passe par le même service que l'application
(consignes, protection des codes, contrôles). DeepL utilise l'API texte : le
document de l'application passe par l'API documentaire, facturée au minimum
50 000 caractères par fichier, ce qui serait disproportionné pour 30 phrases.
Les décisions humaines restent « pending » : ce script ne relit rien.
"""
import argparse
from datetime import date
import json
import os
from pathlib import Path
import time

import deepl
from dotenv import load_dotenv

from services.glossary import load_glossary, select_pairs
from services.openai_translation import TRANSLATION_PROMPT_VERSION, translate_openai_document

ROOT = Path(__file__).resolve().parents[1]


def translate_gpt(sources, model, target, brief=None, glossary=None):
    passages = []
    pairs = select_pairs(glossary, 'FR', target, '\n'.join(sources)) if glossary else ()
    translate_openai_document(b'', '.pdf', target, os.environ['OPENAI_API_KEY'].strip(), model=model,
                              blocks=sources, source_language='FR', passages=passages, brief=brief,
                              glossary_pairs=pairs)
    return [translation for _, translation in passages]


def translate_deepl(sources, target):
    client = deepl.DeepLClient(os.environ['DEEPL_API_KEY'].strip())
    return [result.text for result in client.translate_text(sources, source_lang='FR', target_lang=target)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=['gpt', 'deepl'], required=True)
    parser.add_argument('--model', default='gpt-4.1-mini', help='Modèle OpenAI (ignoré pour DeepL).')
    parser.add_argument('--target', default='EN-GB')
    parser.add_argument('--corpus', type=Path, default=Path(__file__).with_name('corpus.json'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--brief', default='', help='Fiche de contexte transmise à GPT (description du document).')
    parser.add_argument('--glossary', type=Path, help='Glossaire JSON transmis à GPT pendant la traduction.')
    parser.add_argument('--confirm', action='store_true', help='Accepter l’envoi du corpus et l’appel payant.')
    args = parser.parse_args()
    if not args.confirm:
        parser.error('appel payant : relancer avec --confirm.')
    load_dotenv(ROOT / '.env')
    corpus = json.loads(args.corpus.read_text(encoding='utf-8'))
    sources = [case['source'] for case in corpus]
    started = time.monotonic()
    if args.engine == 'gpt':
        glossary = load_glossary(args.glossary) if args.glossary else None
        translations = translate_gpt(sources, args.model, args.target,
                                     brief={'description': args.brief, 'tone': None} if args.brief else None,
                                     glossary=glossary)
    else:
        translations = translate_deepl(sources, args.target)
    trial = {
        'metadata': {'provider': 'GPT (OpenAI)' if args.engine == 'gpt' else 'DeepL (API texte)',
                     'model': args.model if args.engine == 'gpt' else None,
                     'date': date.today().isoformat(),
                     'prompt_version': TRANSLATION_PROMPT_VERSION if args.engine == 'gpt' else None,
                     'source_language': 'FR', 'target_language': args.target,
                     'brief': args.brief or None,
                     'glossary_in_prompt': None if args.engine != 'gpt' or not args.glossary
                     else {key: glossary[key] for key in ('id', 'version', 'sha256')},
                     'cost_eur': None, 'duration_seconds': round(time.monotonic() - started, 1)},
        'results': [{'id': case['id'], 'source': case['source'], 'translation': translation,
                     'human_decision': 'pending', 'reviewer': '', 'review_notes': ''}
                    for case, translation in zip(corpus, translations, strict=True)],
    }
    # Ne jamais écraser un essai déjà payé.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(trial, stream, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()

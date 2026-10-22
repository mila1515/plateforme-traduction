"""Appliquer les corrections d'un relecteur sans nouvel appel au moteur.

Les passages non modifiés gardent leur traduction d'origine (balises Word
comprises, donc leur mise en forme). Un passage corrigé est réinséré tel que
saisi : dans un paragraphe Word mis en forme, le gras ou le lien est alors
réparti proportionnellement. Les contrôles locaux sont recalculés.
"""
from datetime import datetime, timezone

from services.memory import normalize
from services.openai_translation import rebuild_document
from services.review import build_review
from services.word_documents import strip_tags

KEPT = ('brief', 'ambiguity', 'memory')


def apply_corrections(source_data, suffix, report, passages, tagged, edited, glossary=None):
    """Renvoie (fichier, rapport, comparaison, passages, traductions balisées, numéros corrigés)."""
    if len(edited) != len(passages):
        raise ValueError('Corrections : nombre de passages incorrect.')
    empty = [number for number, text in enumerate(edited, 1) if not isinstance(text, str) or not text.strip()]
    if empty:
        raise ValueError(f"Corrections : passage(s) vide(s) n° {', '.join(map(str, empty))}. Aucune modification appliquée.")
    changed = [index for index, ((_, before), after) in enumerate(zip(passages, edited, strict=True))
               if normalize(after) != normalize(before)]
    new_tagged = [edited[index].strip() if index in changed else tagged[index] for index in range(len(passages))]
    translated = rebuild_document(source_data, suffix, report['target_language'], new_tagged)
    new_passages = [(source, strip_tags(text)) for (source, _), text in zip(passages, new_tagged, strict=True)]
    doubts = [{key: value for key, value in issue.items() if key != 'category'}
              for issue in report.get('issues', []) if issue['category'] == 'ambiguity']
    comparison = {}
    quality = build_review(source_data, translated, suffix, report['source_language'], report['target_language'],
                           report['provider'], model=report.get('model'), source_blocks=[source for source, _ in passages],
                           glossary=glossary, comparison=comparison, passages=new_passages, doubts=doubts)
    for key in KEPT:
        if key in report:
            quality[key] = report[key]
    previous = set(report.get('corrections', {}).get('passages', []))
    quality['corrections'] = {'passages': sorted(previous | {index + 1 for index in changed}),
                              'last_applied_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    return translated, quality, comparison, new_passages, new_tagged, [index + 1 for index in changed]

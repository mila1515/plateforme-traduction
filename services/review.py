"""Construire le rapport après traduction sans coupler les contrôles à Streamlit."""
import logging

from services.glossary import select_pairs
from services.openai_translation import extract_blocks, TRANSLATION_PROMPT_VERSION
from services.passages import check_passages
from services.quality import check_translation
from services.word_documents import WordDocument

log = logging.getLogger(__name__)


def build_review(source_data, target_data, suffix, source_language, target_language,
                 provider, model=None, source_blocks=None, glossary=None, comparison=None, passages=None, doubts=None):
    """Garder les résultats téléchargeables même si l'extraction de contrôle échoue.

    Ce service ne lance aucun appel API. Les métadonnées identifient le moteur
    et le glossaire choisis ; le rapport ne contient pas le document complet.
    Si ``comparison`` est fourni, ce dictionnaire reçoit séparément les textes
    pour la session d'interface. Une extraction échouée ne laisse pas de paire partielle.
    Avec ``passages`` (paires alignées, GPT), nombres et références sont contrôlés
    passage par passage, avec négations, obligations, longueur et non-traduction.
    ``doubts`` : ambiguïtés de l'original repérées par l'analyse dédiée, ajoutées comme alertes.
    """
    if comparison is not None:
        comparison.update({'available': False, 'source': '', 'translation': ''})
    try:
        # Les contrôles locaux ne sont pas soumis à la limite d'envoi OpenAI (cas DeepL).
        source_text = '\n'.join(source_blocks if source_blocks is not None else extract_blocks(source_data, suffix, None))
        target_text = '\n'.join(extract_blocks(target_data, suffix, None))
        pairs = select_pairs(glossary, source_language, target_language, source_text) if glossary is not None else None
        report = check_translation(source_text, target_text, glossary_pairs=pairs)
        if passages:
            # Les alertes localisées remplacent les comparaisons globales des nombres et références.
            report['issues'] = ([issue for issue in report['issues'] if issue['category'] == 'terminology']
                                + check_passages(passages, source_language, target_language))
            report['checks'] = report['checks'] + ['passages']
        if comparison is not None:
            comparison.update({'available': True, 'source': source_text, 'translation': target_text})
    except Exception as exc:
        # Le type suffit au diagnostic ; le message pourrait citer le document.
        log.warning('Contrôle indisponible pour un document %s : %s', suffix, type(exc).__name__)
        report = {'status': 'unavailable', 'checks': [], 'issues': [],
                  'limitations': 'Contrôle automatique indisponible : extraction impossible. Relecture humaine nécessaire.'}
    # Un doute ne dépend pas de l'extraction : il reste signalé même si les contrôles échouent.
    report['issues'] = report['issues'] + [{'category': 'ambiguity', **doubt} for doubt in doubts or []]
    report.update({'provider': provider, 'model': model,
                   'translation_prompt_version': TRANSLATION_PROMPT_VERSION if provider == 'GPT (OpenAI)' else None,
                   'source_language': source_language, 'target_language': target_language,
                   'glossary': None if glossary is None else {
                       key: glossary[key] for key in ('id', 'version', 'status', 'sha256', 'reviewed_by', 'reviewed_at')},
                   'glossary_usage': 'disabled' if glossary is None else
                       ('prompt_and_check' if provider == 'GPT (OpenAI)' else 'check_only'),
                   'untranslated_parts': untranslated_parts(source_data, suffix, provider)})
    return report


def untranslated_parts(source_data, suffix, provider):
    """Parties Word laissées en langue source par la traduction GPT (DeepL traite le fichier seul)."""
    if suffix != '.docx' or provider != 'GPT (OpenAI)':
        return []
    try:
        return WordDocument(source_data).untranslated
    except ValueError:
        return []


PASSAGE_MESSAGES = {
    ('untranslated', None): 'semble non traduit (identique à l’original).',
    ('length', 'shorter'): 'traduction nettement plus courte que l’original : omission possible.',
    ('length', 'longer'): 'traduction nettement plus longue que l’original : ajout possible.',
    ('negation', 'missing'): 'négation de l’original absente de la traduction : sens peut-être inversé.',
    ('negation', 'added'): 'négation absente de l’original mais présente dans la traduction : sens peut-être inversé.',
    ('obligation', 'missing'): 'obligation de l’original (doit, obligatoire…) absente de la traduction.',
    ('obligation', 'added'): 'obligation ajoutée dans la traduction, absente de l’original.',
}


def _values(counts):
    return ', '.join(f'{value} (×{count})' for value, count in counts.items())


def passage_detail(issue):
    """Message d'une alerte par passage, sans le rappel du passage."""
    if issue['check'] in ('numbers', 'references'):
        label = 'nombres' if issue['check'] == 'numbers' else 'références'
        parts = ([f"{label} absents : {_values(issue['missing'])}"] if issue['missing'] else []) \
            + ([f"{label} ajoutés : {_values(issue['added'])}"] if issue['added'] else [])
        detail = ' ; '.join(parts) + '.'
    else:
        detail = PASSAGE_MESSAGES[(issue['check'], issue.get('direction'))]
    return detail


def _passage_message(issue):
    return f"Passage {issue['passage']} (« {issue['excerpt']}… ») : {passage_detail(issue)}"


def readable_alerts(report):
    """Présenter les écarts sans inventer d'alignement entre valeurs ou phrases."""
    messages = []
    for issue in report.get('issues', []):
        if issue['category'] == 'passage':
            messages.append(_passage_message(issue))
        elif issue['category'] == 'ambiguity':
            messages.append(f"Passage {issue['passage']} : formulation ambiguë dans l’original (« {issue['quote']} »). "
                            f"{issue['note']} La traduction a retenu la lecture la plus probable : à confirmer.")
        elif issue['category'] == 'terminology':
            messages.append('Terme attendu absent : ' + ', '.join(issue['expected_terms'])
                            + ' (source : ' + ', '.join(issue['source_terms']) + ').')
        else:
            label = 'Nombres' if issue['category'] == 'numbers' else 'Références'
            for key, description in [('missing', 'absents ou moins présents dans la traduction'),
                                     ('added', 'ajoutés ou plus présents dans la traduction')]:
                if issue.get(key):
                    values = ', '.join(f'{value} (×{count})' for value, count in issue[key].items())
                    messages.append(f'{label} {description} : {values}.')
    return messages

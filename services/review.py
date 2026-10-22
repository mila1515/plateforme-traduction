"""Construire le rapport après traduction sans coupler les contrôles à Streamlit."""
from services.glossary import select_pairs
from services.openai_translation import extract_blocks, TRANSLATION_PROMPT_VERSION
from services.quality import check_translation


def build_review(source_data, target_data, suffix, source_language, target_language,
                 provider, model=None, source_blocks=None, glossary=None, comparison=None):
    """Garder les résultats téléchargeables même si l'extraction de contrôle échoue.

    Ce service ne lance aucun appel API. Les métadonnées identifient le moteur
    et le glossaire choisis ; le rapport ne contient pas le document complet.
    Si ``comparison`` est fourni, ce dictionnaire reçoit séparément les textes
    pour la session d'interface. Une extraction échouée ne laisse pas de paire partielle.
    """
    if comparison is not None:
        comparison.update({'available': False, 'source': '', 'translation': ''})
    try:
        # Les contrôles locaux ne sont pas soumis à la limite d'envoi OpenAI (cas DeepL).
        source_text = '\n'.join(source_blocks if source_blocks is not None else extract_blocks(source_data, suffix, None))
        target_text = '\n'.join(extract_blocks(target_data, suffix, None))
        pairs = select_pairs(glossary, source_language, target_language, source_text) if glossary is not None else None
        report = check_translation(source_text, target_text, glossary_pairs=pairs)
        if comparison is not None:
            comparison.update({'available': True, 'source': source_text, 'translation': target_text})
    except Exception:
        report = {'status': 'unavailable', 'checks': [], 'issues': [],
                  'limitations': 'Contrôle automatique indisponible : extraction impossible. Relecture humaine nécessaire.'}
    report.update({'provider': provider, 'model': model,
                   'translation_prompt_version': TRANSLATION_PROMPT_VERSION if provider == 'GPT (OpenAI)' else None,
                   'source_language': source_language, 'target_language': target_language,
                   'glossary': None if glossary is None else {
                       key: glossary[key] for key in ('id', 'version', 'status', 'sha256', 'reviewed_by', 'reviewed_at')},
                   'glossary_usage': 'disabled' if glossary is None else
                       ('prompt_and_check' if provider == 'GPT (OpenAI)' else 'check_only')})
    return report


def readable_alerts(report):
    """Présenter les écarts sans inventer d'alignement entre valeurs ou phrases."""
    messages = []
    for issue in report.get('issues', []):
        if issue['category'] == 'terminology':
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

"""Construire le rapport après traduction sans coupler les contrôles à Streamlit."""
from services.glossary import select_pairs
from services.openai_translation import extract_blocks
from services.quality import check_translation


def build_review(source_data, target_data, suffix, source_language, target_language,
                 provider, model=None, source_blocks=None, glossary=None):
    """Garder les résultats téléchargeables même si l'extraction de contrôle échoue.

    Ce service ne lance aucun appel API. Les métadonnées identifient le moteur
    et le glossaire choisis ; le rapport ne contient pas le document complet.
    """
    try:
        source_text = '\n'.join(source_blocks if source_blocks is not None else extract_blocks(source_data, suffix))
        target_text = '\n'.join(extract_blocks(target_data, suffix))
        pairs = select_pairs(glossary, source_language, target_language, source_text) if glossary is not None else None
        report = check_translation(source_text, target_text, glossary_pairs=pairs)
    except Exception:
        report = {'status': 'unavailable', 'checks': [], 'issues': [],
                  'limitations': 'Contrôle automatique indisponible : extraction impossible ou limite de texte dépassée. Relecture humaine nécessaire.'}
    report.update({'provider': provider, 'model': model,
                   'source_language': source_language, 'target_language': target_language,
                   'glossary': None if glossary is None else {
                       key: glossary[key] for key in ('id', 'version', 'status', 'sha256', 'reviewed_by', 'reviewed_at')},
                   'glossary_usage': 'disabled' if glossary is None else
                       ('prompt_and_check' if provider == 'GPT (OpenAI)' else 'check_only')})
    return report

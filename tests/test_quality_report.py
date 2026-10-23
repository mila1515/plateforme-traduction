"""Rapport qualité Word : lisible sans connaissance technique, fidèle au rapport de contrôle."""
from io import BytesIO

from docx import Document

from services.glossary import load_glossary, select_pairs
from services.openai_translation import render_document
from services.passages import check_passages
from services.quality_report import build_quality_report
from services.review import build_review, readable_alerts

PASSAGES = [('La consignation doit être confirmée par le responsable.', 'The entry must be confirmed by the manager.'),
            ("L'opérateur ne doit pas ouvrir la porte 3.", 'The operator must open door 4.')]
SEMANTIC = {'assessment': 'suspected_issues', 'summary': 'Négation inversée, à confirmer.', 'parts': 1,
            'model': 'gpt-4.1-mini', 'discarded_issues': 0,
            'issues': [{'category': 'negation', 'severity': 'critical', 'source_quote': 'ne doit pas ouvrir',
                        'translation_quote': 'must open', 'explanation': 'Une interdiction devient une obligation.'}]}


def report_for(passages, glossary=None):
    quality = build_review(b'', render_document([t for _, t in passages], '.pdf', 'EN-GB'), '.pdf', 'FR', 'EN-GB',
                           'GPT (OpenAI)', model='gpt-4.1-mini', source_blocks=[s for s, _ in passages],
                           glossary=glossary, passages=passages)
    quality['language_pair_evaluated'] = True
    return quality


def text_of(data):
    document = Document(BytesIO(data))
    cells = [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    return '\n'.join([paragraph.text for paragraph in document.paragraphs] + cells)


def test_glossary_term_is_checked_in_the_passage_itself():
    glossary = load_glossary()
    lockout = [pair for pair in select_pairs(glossary, 'FR', 'EN-GB') if pair['id'] == 'lockout']
    issues = check_passages(PASSAGES, 'FR', 'EN-GB', glossary_pairs=lockout)
    assert [(issue['passage'], issue['check'], issue['term_id']) for issue in issues if issue['check'] == 'terminology'] \
        == [(1, 'terminology', 'lockout')]
    message = readable_alerts({'issues': [issue for issue in issues if issue['check'] == 'terminology']})[0]
    assert message.startswith('Passage 1') and 'lockout' in message


def test_report_contains_summary_meaning_alerts_with_both_texts_and_review_box():
    quality = report_for(PASSAGES, glossary=load_glossary())
    text = text_of(build_quality_report('procedure_EN-GB.pdf', quality, PASSAGES, SEMANTIC))
    assert 'Rapport qualité de la traduction' in text and 'français → anglais britannique' in text
    assert 'Problèmes de sens suspectés : 1, dont 1 critique(s) ou majeur(s).' in text
    assert 'Une interdiction devient une obligation.' in text
    assert 'The operator must open door 4.' in text  # Traduction affichée à côté de l'alerte.
    assert 'terme attendu absent : lockout' in text and 'négation' in text
    assert 'Relu par' in text and '☐ Traduction validée' in text
    assert 'ne valide pas la traduction' in text
    assert '{' not in text  # Aucune donnée brute JSON.


def test_report_without_meaning_analysis_or_alerts_says_so_plainly():
    clean = [('Porte 3 fermée.', 'Door 3 closed.')]
    text = text_of(build_quality_report('ok.pdf', report_for(clean), clean, None))
    assert 'Analyse du sens par IA : non réalisée.' in text
    assert 'Aucune alerte. Le sens reste à vérifier.' in text

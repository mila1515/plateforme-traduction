"""Comparaison en session et alertes, séparées du rapport téléchargeable."""
from io import BytesIO
from docx import Document

from services.review import build_review, readable_alerts


def docx(text):
    document = Document()
    document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_comparison_contains_exact_texts_without_exporting_them_in_report():
    comparison = {}
    report = build_review(docx('Porte 3'), docx('Door 4'), '.docx', 'FR', 'EN-GB', 'DeepL', comparison=comparison)
    assert comparison == {'available': True, 'source': 'Porte 3', 'translation': 'Door 4'}
    assert 'source' not in report and 'translation' not in report and 'comparison' not in report
    messages = readable_alerts(report)
    assert len(messages) == 2
    assert 'absents ou moins présents' in messages[0] and '3 (×1)' in messages[0]
    assert 'ajoutés ou plus présents' in messages[1] and '4 (×1)' in messages[1]


def test_failed_extraction_has_no_misleading_partial_comparison():
    comparison = {}
    report = build_review(docx('Porte 3'), b'invalid', '.docx', 'FR', 'DE', 'DeepL', comparison=comparison)
    assert report['status'] == 'unavailable'
    assert comparison == {'available': False, 'source': '', 'translation': ''}


def test_glossary_alert_is_readable_without_claiming_a_translation_is_wrong():
    messages = readable_alerts({'issues': [{'category': 'terminology', 'source_terms': ['capteur'],
                                         'expected_terms': ['sensor', 'sensors']}]})
    assert messages == ['Terme attendu absent : sensor, sensors (source : capteur).']


def test_long_deepl_document_is_still_checked_locally():
    long_text = 'Porte 3. ' * 8000  # Plus de 60 000 caractères : limite OpenAI, pas DeepL.
    report = build_review(docx(long_text), docx(long_text.replace('Porte', 'Door')), '.docx', 'FR', 'EN-GB', 'DeepL')
    assert report['status'] == 'review_required'

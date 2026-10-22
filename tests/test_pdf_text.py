"""Découpage PDF : phrases complètes malgré sauts de page, césures et en-têtes."""
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from services.openai_translation import extract_blocks
from services.pdf_text import pdf_paragraphs


def pdf(pages, header='RailNova — Rapport interne', footer='Page {page}/{total}'):
    """Chaque page : liste de paragraphes, eux-mêmes listes de lignes."""
    buffer = BytesIO()
    document = canvas.Canvas(buffer, pagesize=A4)
    for number, paragraphs in enumerate(pages, 1):
        if header:
            document.drawString(50, 800, header)
        y = 760
        for lines in paragraphs:
            for line in lines:
                document.drawString(50, y, line)
                y -= 14
            y -= 14  # Ligne vide entre paragraphes.
        if footer:
            document.drawString(280, 40, footer.format(page=number, total=len(pages)))
        document.showPage()
    document.save()
    return buffer.getvalue()


def test_sentence_split_by_page_break_is_rejoined_without_headers_in_between():
    source = pdf([[['Introduction du rapport.'],
                   ["L'opérateur ne doit pas ouvrir la porte tant que le", "train n'est pas arrêté et que la mainte-"]],
                  [["nance n'a pas validé l'intervention."], ['Fin de la maintenance.']]])
    assert pdf_paragraphs(source) == [
        'RailNova — Rapport interne',  # Gardé une fois, à sa première place.
        'Introduction du rapport.',
        "L'opérateur ne doit pas ouvrir la porte tant que le train n'est pas arrêté "
        "et que la maintenance n'a pas validé l'intervention.",
        'Fin de la maintenance.',
    ]


def test_line_end_hyphen_joins_known_word_but_keeps_compound_words():
    source = pdf([[['Prévoir la mainte-', 'nance et la porte-', 'fenêtre.'], ['Maintenance annuelle.']]],
                 header=None, footer=None)
    assert pdf_paragraphs(source) == ['Prévoir la maintenance et la porte-fenêtre.', 'Maintenance annuelle.']


def test_complete_sentence_or_capital_start_is_not_merged_across_pages():
    source = pdf([[['Première page terminée.']], [['Deuxième page.']]], footer=None)
    assert pdf_paragraphs(source)[-2:] == ['Première page terminée.', 'Deuxième page.']
    source = pdf([[['Titre de section']], [['Nouveau paragraphe.']]], header=None, footer=None)
    assert pdf_paragraphs(source) == ['Titre de section', 'Nouveau paragraphe.']


def test_numbers_inside_body_are_kept():
    source = pdf([[['Porte 3 fermée.'], ['12'], ['Contrôle à 08:10.']]], header=None, footer=None)
    assert extract_blocks(source, '.pdf') == ['Porte 3 fermée.', '12', 'Contrôle à 08:10.']


def test_similar_body_lines_at_page_edges_are_not_mistaken_for_headers():
    source = pdf([[['Porte 3 contrôlée.']], [['Porte 4 contrôlée.']], [['Porte 5 contrôlée.']]], header=None)
    assert pdf_paragraphs(source) == ['Porte 3 contrôlée.', 'Porte 4 contrôlée.', 'Porte 5 contrôlée.']


def test_footer_with_page_number_in_sentence_is_kept_once():
    source = pdf([[['Texte un.']], [['Texte deux.']], [['Texte trois.']]], header=None,
                 footer='Rapport RN-204 · page {page} sur {total} · diffusion interne')
    assert pdf_paragraphs(source) == ['Texte un.', 'Rapport RN-204 · page 1 sur 3 · diffusion interne',
                                      'Texte deux.', 'Texte trois.']

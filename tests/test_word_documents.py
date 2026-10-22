"""Régressions OOXML : texte traduit, structure et ressources conservées."""
from io import BytesIO
import json
from types import SimpleNamespace
from zipfile import ZipFile

from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.shared import Cm
from lxml import etree
from PIL import Image
import pytest

from services.openai_translation import extract_blocks, translate_openai_document
from services.word_documents import WordDocument, W


def save(document):
    output = BytesIO()
    document.save(output)
    return output.getvalue()


class Client:
    def __init__(self):
        self.responses = self
        self.calls = []
    def create(self, **kwargs):
        self.calls.append(kwargs)
        blocks = json.loads(kwargs['input'])['blocks']
        return SimpleNamespace(status='completed', output_text=json.dumps({
            'translations': {key: 'Translated ' + value for key, value in blocks.items()}}))


def structural_xml(payload):
    """Comparer tout le XML sauf les valeurs textuelles intentionnellement modifiées."""
    root = etree.fromstring(payload)
    for node in root.iter(W + 't'):
        node.text = 'TEXT'
        node.attrib.pop('{http://www.w3.org/XML/1998/namespace}space', None)
    return etree.tostring(root, method='c14n')


def test_complete_word_preserves_tables_sections_images_headers_and_styles():
    document = Document()
    title = document.add_paragraph(style='Title')
    title.add_run('Rapport ').bold = True
    title.add_run('technique').italic = True
    table = document.add_table(rows=2, cols=2)
    table.style = 'Table Grid'
    table.autofit = False
    table.columns[0].width = Cm(4)
    table.cell(0, 0).merge(table.cell(0, 1)).text = 'Cellule fusionnée'
    table.cell(1, 0).text = 'Porte 3'
    nested = table.cell(1, 1).add_table(rows=1, cols=1)
    nested.cell(0, 0).text = 'Capteur'
    document.add_page_break()
    document.add_paragraph('Seconde page')
    # Petite image embarquée : aucun fichier externe, ni accès réseau.
    image = BytesIO()
    Image.new('RGB', (8, 8), 'blue').save(image, format='PNG')
    image.seek(0)
    document.add_picture(image, width=Cm(1))
    document.sections[0].header.paragraphs[0].text = 'En-tête technique'
    footer = document.sections[0].footer.paragraphs[0]
    footer.add_run('Page ')
    field = OxmlElement('w:fldSimple')
    field.set(qn('w:instr'), 'PAGE')
    run, text = OxmlElement('w:r'), OxmlElement('w:t')
    text.text = '1'
    run.append(text)
    field.append(run)
    footer._p.append(field)
    document.add_section(WD_SECTION_START.NEW_PAGE)
    document.add_paragraph('Troisième section')
    link_paragraph = document.add_paragraph()
    link = OxmlElement('w:hyperlink')
    link.set(qn('r:id'), document.part.relate_to('https://example.org', RT.HYPERLINK, is_external=True))
    link_run, link_text = OxmlElement('w:r'), OxmlElement('w:t')
    link_text.text = 'Documentation'
    link_run.append(link_text)
    link.append(link_run)
    link_paragraph._p.append(link)
    source = save(document)
    blocks = extract_blocks(source, '.docx')
    assert blocks.count('Cellule fusionnée') == 1
    assert blocks.count('En-tête technique') == 1  # En-tête partagé par les sections.
    assert '1' not in blocks  # Le champ PAGE reste dynamique.
    translated = translate_openai_document(source, '.docx', 'EN-GB', 'fake', client=Client())
    result = Document(BytesIO(translated))
    assert len(result.tables) == 1
    assert result.tables[0].cell(0, 0).text == 'Translated Cellule fusionnée'
    assert result.tables[0].cell(1, 1).tables[0].cell(0, 0).text == 'Translated Capteur'
    assert len(result.inline_shapes) == len(document.inline_shapes) == 1
    assert result.paragraphs[0].runs[0].bold
    assert result.paragraphs[0].runs[1].italic
    assert len(result.sections) == len(document.sections)
    with ZipFile(BytesIO(source)) as before, ZipFile(BytesIO(translated)) as after:
        assert before.namelist() == after.namelist()
        for name in before.namelist():
            if name in WordDocument(source).parts:
                assert structural_xml(before.read(name)) == structural_xml(after.read(name))
            else:
                assert before.read(name) == after.read(name)


def test_vertical_merge_not_translated_twice_and_breaks_are_retained():
    document = Document()
    table = document.add_table(rows=2, cols=1)
    table.cell(0, 0).merge(table.cell(1, 0)).text = 'Texte fusionné'
    paragraph = document.add_paragraph()
    paragraph.add_run('Avant\tAprès\nSuite')
    source = save(document)
    # Un seul passage : la phrase n'est plus coupée aux tabulations et sauts de ligne.
    assert extract_blocks(source, '.docx') == ['Texte fusionné', 'Avant\tAprès\nSuite']
    client = Client()
    result = translate_openai_document(source, '.docx', 'DE', 'fake', client=client)
    assert 'Avant⟪1/⟫Après⟪2/⟫Suite' in client.calls[0]['input']
    assert Document(BytesIO(result)).paragraphs[0].text == 'Translated Avant\tAprès\nSuite'


def test_long_word_paragraph_returns_to_original_cell():
    document = Document()
    # Trois phrases font trois fragments, alors qu'un découpage fixe en ferait deux.
    document.add_table(rows=1, cols=1).cell(0, 0).text = ('A' * 3500 + '. ') * 3
    source = save(document)
    result = translate_openai_document(source, '.docx', 'DE', 'fake', client=Client())
    restored = Document(BytesIO(result))
    assert len(restored.tables[0].cell(0, 0).paragraphs) == 1
    assert restored.tables[0].cell(0, 0).text.count('A') == 10500


def test_mismatched_source_blocks_rejected_before_billable_call():
    document = Document()
    document.add_paragraph('Texte réel')
    client = Client()
    with pytest.raises(ValueError, match='ne correspondent pas'):
        translate_openai_document(save(document), '.docx', 'DE', 'fake', client=client, blocks=['Autre texte'])
    assert not client.calls


def test_complex_field_spanning_paragraphs_remains_untranslated():
    document = Document()
    begin = OxmlElement('w:fldChar')
    begin.set(qn('w:fldCharType'), 'begin')
    document.add_paragraph().add_run()._r.append(begin)
    document.add_paragraph('Résultat automatique du champ')
    end = OxmlElement('w:fldChar')
    end.set(qn('w:fldCharType'), 'end')
    document.add_paragraph().add_run()._r.append(end)
    document.add_paragraph('Texte à traduire')
    source = save(document)
    assert extract_blocks(source, '.docx') == ['Texte à traduire']
    output = translate_openai_document(source, '.docx', 'DE', 'fake', client=Client())
    result = Document(BytesIO(output))
    assert result.paragraphs[1].text == 'Résultat automatique du champ'
    assert result.paragraphs[-1].text == 'Translated Texte à traduire'


def test_style_boundaries_do_not_split_translated_words():
    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run('Attention').bold = True
    paragraph.add_run(' : ne pas ouvrir.')
    word = WordDocument(save(document))
    # Coupure proportionnelle : 28 × 9 / 26 ≈ 10, soit « Danger war|ning ».
    result = Document(BytesIO(word.render(['Danger warning: do not open.'])))
    runs = result.paragraphs[0].runs
    assert runs[0].bold and runs[0].text == 'Danger '
    assert runs[1].text == 'warning: do not open.'


@pytest.mark.parametrize('text,position,start,expected', [
    ('abc def', 5, 0, 4), ('abc def', 4, 0, 4), ('abcdef', 3, 0, 3), ('abc def', 1, 0, 4), ('ab cd ef', 7, 6, 7)])
def test_word_boundary(text, position, start, expected):
    from services.word_documents import word_boundary
    assert word_boundary(text, position, start) == expected


def with_parts(source, parts):
    """Ajouter des parties OOXML (notes, commentaires) absentes de l'API python-docx."""
    output = BytesIO()
    with ZipFile(BytesIO(source)) as before, ZipFile(output, 'w') as after:
        for item in before.infolist():
            after.writestr(item, before.read(item.filename))
        for name, xml in parts.items():
            after.writestr(name, xml)
    return output.getvalue()


NOTES = ('<w:{kind}s xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
         '<w:{kind} w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:{kind}>'
         '<w:{kind} w:id="1"><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:{kind}></w:{kind}s>')


def test_footnotes_and_endnotes_are_translated_with_the_body():
    document = Document()
    document.add_paragraph('Corps du rapport')
    source = with_parts(save(document), {
        'word/footnotes.xml': NOTES.format(kind='footnote', text='Note de bas de page'),
        'word/endnotes.xml': NOTES.format(kind='endnote', text='Note de fin'),
    })
    assert {'Note de bas de page', 'Note de fin'} <= set(extract_blocks(source, '.docx'))
    translated = translate_openai_document(source, '.docx', 'EN-GB', 'fake', client=Client())
    with ZipFile(BytesIO(translated)) as archive:
        assert b'Translated Note de bas de page' in archive.read('word/footnotes.xml')
        assert b'Translated Note de fin' in archive.read('word/endnotes.xml')
    assert WordDocument(source).untranslated == []


def add_field(paragraph, instruction, result):
    """Champ complexe : début, instruction, séparation, texte affiché, fin."""
    run = paragraph.add_run()
    for kind, text in (('begin', None), (None, instruction), ('separate', None)):
        element = OxmlElement('w:fldChar' if kind else 'w:instrText')
        if kind:
            element.set(qn('w:fldCharType'), kind)
        else:
            element.text = text
        run._r.append(element)
    shown = OxmlElement('w:t')
    shown.text = result
    run._r.append(shown)
    end = OxmlElement('w:fldChar')
    end.set(qn('w:fldCharType'), 'end')
    run._r.append(end)


def test_field_results_and_comments_are_reported_as_untranslated():
    from services.review import build_review
    document = Document()
    paragraph = document.add_paragraph('Voir la section ')
    add_field(paragraph, ' REF _Ref123 \\h ', 'Sécurité')
    source = with_parts(save(document), {'word/comments.xml':
        '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:comment w:id="0"><w:p><w:r><w:t>À vérifier</w:t></w:r></w:p></w:comment></w:comments>'})
    word = WordDocument(source)
    assert word.blocks == ['Voir la section ']
    assert word.tagged == ['Voir la section ⟪1/⟫']  # Le renvoi reste dynamique, à sa place.
    assert len(word.untranslated) == 2
    report = build_review(source, source, '.docx', 'FR', 'EN-GB', 'GPT (OpenAI)')
    assert report['untranslated_parts'] == word.untranslated
    # DeepL traduit lui-même le fichier Word : pas d'avertissement inventé.
    assert build_review(source, source, '.docx', 'FR', 'EN-GB', 'DeepL')['untranslated_parts'] == []


def test_sentence_around_link_and_line_break_is_sent_whole_and_link_text_translated():
    document = Document()
    paragraph = document.add_paragraph('Contactez le service ')
    add_field(paragraph, ' HYPERLINK "https://example.org" ', 'via le portail')
    paragraph.add_run(' avant de couper le courant.')
    second = document.add_paragraph('Ne pas redémarrer')
    second.add_run().add_break()
    second.add_run('sans autorisation écrite.')
    word = WordDocument(save(document))
    assert word.tagged == ['Contactez le service ⟪1⟫via le portail⟪/1⟫ avant de couper le courant.',
                           'Ne pas redémarrer⟪1/⟫sans autorisation écrite.']
    assert word.untranslated == []
    result = Document(BytesIO(word.render([
        'Contact the department ⟪1⟫through the portal⟪/1⟫ before cutting the power.',
        'Do not restart⟪1/⟫ without written authorisation.'])))  # Espace réelle de gpt-4.1-mini, retirée.
    assert result.paragraphs[0].text == 'Contact the department through the portal before cutting the power.'
    assert result.paragraphs[1].text == 'Do not restart\nwithout written authorisation.'
    assert word.approximate == 0


def test_formatting_follows_the_translated_words_even_when_word_order_changes():
    document = Document()
    paragraph = document.add_paragraph('Appuyer sur le bouton ')
    paragraph.add_run('rouge').bold = True
    paragraph.add_run(' du panneau.')
    word = WordDocument(save(document))
    assert word.tagged == ['Appuyer sur le bouton ⟪1⟫rouge⟪/1⟫ du panneau.']
    # En anglais, l'adjectif passe avant le nom : le gras suit « red ».
    result = Document(BytesIO(word.render(['Press the ⟪1⟫red⟪/1⟫ button on the panel.'])))
    runs = result.paragraphs[0].runs
    assert [(run.text, bool(run.bold)) for run in runs] == [
        ('Press the ', False), ('red', True), (' button on the panel.', False)]


@pytest.mark.parametrize('translation', ['Press the red button on the panel.', 'Press ⟪1⟫the ⟪1⟫red⟪/1⟫ button.',
                                         'Press the ⟪2⟫red⟪/2⟫ button.'])
def test_lost_or_altered_tags_keep_the_whole_paragraph_translated(translation):
    document = Document()
    paragraph = document.add_paragraph('Appuyer sur le bouton ')
    paragraph.add_run('rouge').bold = True
    paragraph.add_run(' du panneau.')
    word = WordDocument(save(document))
    result = Document(BytesIO(word.render([translation])))
    text = result.paragraphs[0].text
    assert '⟪' not in text and 'red' in text and 'Appuyer' not in text
    assert word.approximate == 1


def test_plain_text_for_checks_has_no_markup():
    from services.word_documents import strip_tags
    assert strip_tags('Do not restart⟪1/⟫without ⟪2⟫written⟪/2⟫ authorisation.') == \
        'Do not restart without written authorisation.'


def test_invisible_run_properties_do_not_create_tags():
    document = Document()
    paragraph = document.add_paragraph()
    for text, language in (('Contrôle ', 'fr-FR'), ('du capteur', 'en-GB')):
        run = paragraph.add_run(text)
        lang = OxmlElement('w:lang')
        lang.set(qn('w:val'), language)
        run._r.get_or_add_rPr().append(lang)
    assert WordDocument(save(document)).tagged == ['Contrôle du capteur']

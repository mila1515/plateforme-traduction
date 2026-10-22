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
    assert extract_blocks(source, '.docx') == ['Texte fusionné', 'Avant', 'Après', 'Suite']
    result = translate_openai_document(source, '.docx', 'DE', 'fake', client=Client())
    assert Document(BytesIO(result)).paragraphs[0].text == 'Translated Avant\tTranslated Après\nTranslated Suite'


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

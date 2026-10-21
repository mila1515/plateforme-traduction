from io import BytesIO
import json
import re
from pathlib import Path
from types import SimpleNamespace

from docx import Document
from pypdf import PdfReader
import pytest

from services.openai_translation import extract_blocks, batches, render_document, translate_openai_document, parse_translations, translation_schema

ROOT = Path(__file__).resolve().parents[1]


class FakeClient:
    def __init__(self, translations=None, status='completed'):
        self.calls = []
        self.translations = translations
        self.status = status
        self.responses = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        blocks = json.loads(kwargs['input'])['blocks']
        items = self.translations if self.translations is not None else ['Translated ' + text for text in blocks.values()]
        return SimpleNamespace(status=self.status, output_text=json.dumps({'translations': dict(zip(blocks, items))}))


def test_openai_pdf_output_and_api_options():
    sample = (ROOT / 'examples' / 'rapport_incident_FR.pdf').read_bytes()
    client = FakeClient(['Incident report', 'A simulated door failure was reported at 08:10.'])
    result = translate_openai_document(sample, '.pdf', 'EN-GB', 'fake', client=client, blocks=['Rapport d’incident', 'Une anomalie est signalée.'])
    reader = PdfReader(BytesIO(result))
    assert 'Incident report' in reader.pages[0].extract_text()
    assert client.calls[0]['model'] == 'gpt-4.1-mini'
    assert client.calls[0]['store'] is False
    assert client.calls[0]['text']['format']['strict'] is True
    assert client.calls[0]['text']['format']['schema']['properties']['translations']['required'] == ['block_000', 'block_001']
    assert client.calls[0]['text']['format']['schema']['properties']['translations']['properties']['block_000']['pattern'] == r'\S'
    assert 'British English' in client.calls[0]['instructions']


def test_docx_body_and_tables_in_order():
    doc = Document()
    doc.add_paragraph('Avant le tableau')
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = 'Équipement'
    table.cell(0, 1).text = 'Porte 3'
    doc.add_paragraph('Après le tableau')
    buffer = BytesIO()
    doc.save(buffer)
    assert extract_blocks(buffer.getvalue(), '.docx') == ['Avant le tableau', 'Équipement', 'Porte 3', 'Après le tableau']
    client = FakeClient(['Antes de la tabla', 'Equipo', 'Puerta 3', 'Después de la tabla'])
    result = translate_openai_document(buffer.getvalue(), '.docx', 'ES', 'fake', client=client)
    translated = Document(BytesIO(result))
    assert [p.text for p in translated.paragraphs] == ['Antes de la tabla', 'Después de la tabla']
    assert [[cell.text for cell in row.cells] for row in translated.tables[0].rows] == [['Equipo', 'Puerta 3']]


@pytest.mark.parametrize('language,text', [
    ('EN-GB', 'Technical monitoring sheet'),
    ('ES', 'Informe de incidente y coordinación'),
    ('DE', 'Störungsbericht und technische Überprüfung'),
    ('FR', 'Fiche de suivi technique et contrôle des équipements.'),
])
def test_pdf_unicode_and_printable_pages(language, text):
    data = render_document([text, 'RN 204 | 12/10/2026 | 08:10'], '.pdf', language)
    reader = PdfReader(BytesIO(data))
    assert len(reader.pages) == 1
    assert text in reader.pages[0].extract_text()


def test_chunking_keeps_all_text_bounded():
    blocks = ['A' * 9000, 'B' * 4000]
    groups = list(batches(blocks))
    assert all(sum(map(len, group)) <= 6000 for group in groups)
    assert ''.join(piece for group in groups for piece in group) == ''.join(blocks)


@pytest.mark.parametrize('client', [FakeClient([], 'completed'), FakeClient(['partial'], 'incomplete')])
def test_incomplete_response_not_exported(client):
    with pytest.raises(ValueError, match='incompl'):
        translate_openai_document(b'', '.pdf', 'DE', 'fake', client=client, blocks=['Texte'])


def test_oversized_text_rejected_before_api():
    client = FakeClient()
    with pytest.raises(ValueError, match='60 000'):
        translate_openai_document(b'', '.pdf', 'DE', 'fake', client=client, blocks=['x' * 60001])
    assert not client.calls


def test_interface_openai_works_without_deepl_and_keeps_results(monkeypatch):
    import streamlit as st
    import services.openai_translation
    from streamlit.testing.v1 import AppTest
    sample = (ROOT / 'examples' / 'fiche_suivi_technique_FR.pdf').read_bytes()
    class Upload:
        name = 'fiche.pdf'
        def getvalue(self):
            return sample
    monkeypatch.setenv('OPENAI_API_KEY', 'fake')
    monkeypatch.setenv('DEEPL_API_KEY', '')
    monkeypatch.setattr(st, 'file_uploader', lambda *a, **kw: [Upload()])
    calls = []
    def fake_translate(*args, **kwargs):
        calls.append((args, kwargs))
        return sample
    monkeypatch.setattr(services.openai_translation, 'translate_openai_document', fake_translate)
    app = AppTest.from_file(str(ROOT / 'app.py')).run()
    assert app.selectbox[1].value == 'GPT (OpenAI)'
    app.checkbox[0].check().run()
    assert not app.button[0].disabled
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state['result_provider'] == 'GPT (OpenAI)'
    assert app.session_state['results'][0]['data'] == sample
    assert app.session_state['results'][0]['quality']['status'] == 'review_required'
    assert app.session_state['results'][0]['quality']['issues'] == []
    assert app.session_state['results'][0]['comparison']['available']
    assert app.session_state['results'][0]['comparison']['source'] == '\n'.join(extract_blocks(sample, '.pdf'))
    assert app.session_state['results'][0]['comparison']['translation'] == app.session_state['results'][0]['comparison']['source']
    assert 'source' not in app.session_state['results'][0]['quality']
    assert calls[0][1]['blocks']
    app.run()
    assert len(calls) == 1
    app.selectbox[1].select('DeepL').run()
    assert app.button[0].disabled
    assert not app.checkbox[0].value


def test_technical_pdf_wraps_are_joined_without_losing_text():
    data = (ROOT / 'examples' / 'fiche_suivi_technique_FR.pdf').read_bytes()
    blocks = extract_blocks(data, '.pdf')
    assert any('Date : 12 octobre 2026. Responsable du dossier' in block for block in blocks)
    old_text = ' '.join((page.extract_text() or '') for page in PdfReader(BytesIO(data)).pages)
    assert ''.join(''.join(blocks).split()) == ''.join(old_text.split())


@pytest.mark.parametrize('text', ['', ' ', '\n\t'])
def test_empty_translations_rejected_with_specific_message(text):
    with pytest.raises(ValueError, match=r'1 passage\(s\) vide'):
        parse_translations(json.dumps({'translations': {'block_000': text}}), ['block_000'])
    assert not re.search(translation_schema(['block_000'])['properties']['translations']['properties']['block_000']['pattern'], text)


def test_many_short_blocks_are_bounded():
    groups = list(batches(['text'] * 100))
    assert max(map(len, groups)) <= 40
    assert sum(map(len, groups)) == 100

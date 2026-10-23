from io import BytesIO
import json
import re
from pathlib import Path
from types import SimpleNamespace

from docx import Document
from pypdf import PdfReader
import pytest

from services.openai_translation import extract_blocks, batches, split_block, render_document, translate_openai_document, parse_translations, translation_schema

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
        return SimpleNamespace(status=self.status, output_text=json.dumps({'translations': dict(zip(blocks, items, strict=False))}))


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
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=10).run()
    assert app.selectbox(key='provider').value == 'GPT (OpenAI)'
    app.checkbox[0].check().run()
    assert not app.button(key='translate').disabled
    app.button(key='translate').click().run()
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
    app.selectbox(key='provider').select('DeepL').run()
    assert app.button(key='translate').disabled
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


def test_long_passage_prefers_sentence_boundary_without_losing_source():
    first = 'A' * 4000 + '. '
    second = 'B' * 3000 + '.'
    pieces = list(split_block(first + second))
    assert pieces == [first, second]
    assert ''.join(pieces) == first + second
    assert max(map(len, pieces)) <= 6000


def test_context_crosses_batches_but_is_not_exported_as_extra_content():
    blocks = [f'Passage {index}.' for index in range(41)]
    client = FakeClient()
    result = translate_openai_document(b'', '.pdf', 'EN-GB', 'fake', client=client, blocks=blocks)
    assert len(client.calls) == 2
    first_input, second_input = [json.loads(call['input']) for call in client.calls]
    assert 'Passage 40.' in first_input['context']['after']
    assert 'Passage 39.' in second_input['context']['before']
    assert first_input['context']['before'] == ''
    assert second_input['context']['after'] == ''
    assert 'not word-for-word' in client.calls[0]['instructions']
    assert 'negation' in client.calls[0]['instructions']
    text = '\n'.join(page.extract_text() for page in PdfReader(BytesIO(result)).pages)
    assert text.count('Translated Passage') == 41


class FailingAfter(FakeClient):
    """Simule un échec réseau au n-ième appel, après des lots déjà facturés."""
    def __init__(self, fail_at):
        super().__init__()
        self.fail_at = fail_at

    def create(self, **kwargs):
        if len(self.calls) + 1 == self.fail_at:
            self.calls.append(kwargs)
            raise ConnectionError('réseau')
        return super().create(**kwargs)


def test_relaunch_reuses_paid_batches_from_session_cache():
    blocks = [f'Paragraphe {index}. ' + 'x' * 5000 for index in range(3)]  # Un lot par paragraphe.
    cache = {}
    first = FailingAfter(fail_at=3)
    with pytest.raises(ConnectionError):
        translate_openai_document(b'', '.pdf', 'EN-GB', 'fake', client=first, blocks=blocks, cache=cache)
    assert len(first.calls) == 3 and len(cache) == 2
    second = FakeClient()
    translate_openai_document(b'', '.pdf', 'EN-GB', 'fake', client=second, blocks=blocks, cache=cache)
    assert len(second.calls) == 1  # Seul le lot en échec est renvoyé.
    other_language = FakeClient()
    translate_openai_document(b'', '.pdf', 'DE', 'fake', client=other_language, blocks=blocks, cache=cache)
    assert len(other_language.calls) == 3  # Une autre requête n'utilise jamais le cache.


def rate_limit(code=None):
    import httpx
    import openai
    response = httpx.Response(429, request=httpx.Request('POST', 'https://api.openai.com/v1/responses'))
    return openai.RateLimitError('limite', response=response, body={'code': code} if code else None)


@pytest.mark.parametrize('code,expected_calls', [(None, 2), ('insufficient_quota', 1)])
def test_only_temporary_rate_limit_is_retried(monkeypatch, code, expected_calls):
    import openai
    import services.openai_translation as module
    monkeypatch.setattr(module.time, 'sleep', lambda delay: None)
    client = FakeClient()
    original = client.create
    def create(**kwargs):
        if not client.calls:
            client.calls.append(kwargs)
            raise rate_limit(code)
        return original(**kwargs)
    client.create = create
    if code:
        with pytest.raises(openai.RateLimitError):
            translate_openai_document(b'', '.pdf', 'EN-GB', 'fake', client=client, blocks=['Porte 3'])
    else:
        translate_openai_document(b'', '.pdf', 'EN-GB', 'fake', client=client, blocks=['Porte 3'])
    assert len(client.calls) == expected_calls


def test_timeout_is_not_retried_because_it_may_be_billed():
    client = FailingAfter(fail_at=1)
    with pytest.raises(ConnectionError):
        translate_openai_document(b'', '.pdf', 'EN-GB', 'fake', client=client, blocks=['Porte 3'])
    assert len(client.calls) == 1


def test_logs_record_statistics_but_never_document_text(caplog):
    import logging
    from services.review import build_review
    from services.semantic_review import review_meaning
    secret = 'Contrat confidentiel numéro SECRET-42'
    caplog.set_level(logging.INFO)
    cache = {}
    translate_openai_document(b'', '.pdf', 'EN-GB', 'fake', client=FakeClient(), blocks=[secret], cache=cache)
    translate_openai_document(b'', '.pdf', 'EN-GB', 'fake', client=FakeClient(), blocks=[secret], cache=cache)
    build_review(b'invalide', b'invalide', '.docx', 'FR', 'EN-GB', 'DeepL')
    review = {'assessment': 'no_issue_detected', 'summary': 'Avis à confirmer.', 'issues': []}
    review_client = SimpleNamespace(responses=SimpleNamespace(
        create=lambda **kwargs: SimpleNamespace(status='completed', output_text=json.dumps(review))))
    review_meaning(secret, 'Confidential contract', 'FR', 'EN-GB', 'fake', client=review_client)
    messages = [record.getMessage() for record in caplog.records]
    assert any('1 appel(s)' in message for message in messages)
    assert any('repris du cache' in message for message in messages)
    assert any('Contrôle indisponible' in message for message in messages)
    assert any('Analyse du sens' in message for message in messages)
    assert not any('SECRET' in message or 'confidentiel' in message.lower() for message in messages)

from pathlib import Path
from io import BytesIO
from zipfile import ZipFile
import pytest
from services.files import validate_document, make_zip, output_name
from services.translation import translate_document

ROOT = Path(__file__).resolve().parents[1]


def test_examples_are_readable():
    paths = list((ROOT / 'examples').glob('*.pdf'))
    assert len(paths) == 3
    for path in paths:
        assert validate_document(path.name, path.read_bytes()) == '.pdf'


def test_reject_invalid_pdf():
    with pytest.raises(ValueError):
        validate_document('invalid.pdf', b'not a pdf')


@pytest.mark.parametrize('xml', ['<invalid', '<invalid/>'])
def test_reject_corrupt_word_xml(xml):
    from services.word_documents import WordDocument
    buffer = BytesIO()
    with ZipFile(buffer, 'w') as archive:
        archive.writestr('word/document.xml', xml)
    for operation in (lambda: validate_document('corrupt.docx', buffer.getvalue()),
                      lambda: WordDocument(buffer.getvalue())):
        with pytest.raises(ValueError, match='Word'):
            operation()


@pytest.mark.parametrize('provider', ['GPT (OpenAI)', 'DeepL'])
def test_corrupt_word_shows_message_without_api_call(monkeypatch, provider):
    import streamlit as st
    import services.translation
    import services.openai_translation
    from streamlit.testing.v1 import AppTest
    buffer = BytesIO()
    with ZipFile(buffer, 'w') as archive:
        archive.writestr('word/document.xml', '<invalid')
    class Upload:
        name = 'corrupt.docx'
        def getvalue(self):
            return buffer.getvalue()
    def forbidden(*args, **kwargs):
        raise AssertionError('Aucun document corrompu ne doit être envoyé.')
    monkeypatch.setattr(st, 'file_uploader', lambda *a, **kw: [Upload()])
    monkeypatch.setenv('OPENAI_API_KEY', 'fake')
    monkeypatch.setenv('DEEPL_API_KEY', 'fake')
    monkeypatch.setattr(services.translation, 'translate_document', forbidden)
    monkeypatch.setattr(services.openai_translation, 'translate_openai_document', forbidden)
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=10).run()
    app.selectbox[1].select(provider).run()
    app.checkbox[0].check().run()
    app.button[0].click().run()
    assert not app.exception
    assert any('endommagé' in error.value for error in app.error)
    assert 'results' not in app.session_state


def test_unique_safe_output_names():
    assert output_name('../report.pdf', 'DE', 1) == '01_report_DE.pdf'
    assert output_name('report.pdf', 'DE', 2) != output_name('report.pdf', 'DE', 1)
    assert output_name('01_report.docx', 'EN-GB', 1) == '01_report_EN-GB.docx'
    data = make_zip([('01_report_DE.pdf', b'one'), ('02_report_DE.pdf', b'two')])
    with ZipFile(BytesIO(data)) as archive:
        assert len(archive.namelist()) == 2


def test_translation_preserves_bytes_and_cleans_temp():
    class FakeClient:
        def translate_document_from_filepath(self, source, target, **kwargs):
            self.source = Path(source)
            assert self.source.read_bytes() == b'input'
            assert kwargs == {'source_lang': 'FR', 'target_lang': 'DE'}
            Path(target).write_bytes(b'translated')
    client = FakeClient()
    assert translate_document(b'input', '.pdf', 'DE', 'fake', client) == b'translated'
    assert not client.source.parent.exists()


def test_interface_without_key(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('DEEPL_API_KEY', '')
    monkeypatch.setenv('OPENAI_API_KEY', '')
    app = AppTest.from_file(str(ROOT / 'app.py')).run()
    assert not app.exception
    assert len(app.tabs) == 0
    assert app.button[0].label == 'Traduire le lot'
    assert app.button[0].disabled
    app.selectbox[0].select('Allemand').run()
    assert not app.exception


def test_downloading_results_does_not_translate(monkeypatch):
    from streamlit.testing.v1 import AppTest
    import services.translation
    def forbidden(*args, **kwargs):
        raise AssertionError('Unexpected translation')
    monkeypatch.setattr(services.translation, 'translate_document', forbidden)
    app = AppTest.from_file(str(ROOT / 'app.py'))
    app.session_state['results'] = [{'name': 'result.pdf', 'data': b'PDF', 'suffix': '.pdf', 'error': None}]
    app.session_state['result_language'] = 'Allemand'
    app.run()
    assert not app.exception
    app.run()
    assert not app.exception
    app.button[-1].click().run()
    assert 'results' not in app.session_state


def test_batch_continues_after_service_failure(monkeypatch):
    import streamlit as st
    import services.translation
    from streamlit.testing.v1 import AppTest
    sample = (ROOT / 'examples' / 'rapport_incident_FR.pdf').read_bytes()
    class Upload:
        name = 'incident.pdf'
        def getvalue(self):
            return sample
    monkeypatch.setattr(st, 'file_uploader', lambda *a, **kw: [Upload(), Upload()])
    monkeypatch.setenv('DEEPL_API_KEY', 'fake')
    calls = []
    def fake_translate(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise RuntimeError('simulated failure')
        return sample
    monkeypatch.setattr(services.translation, 'translate_document', fake_translate)
    app = AppTest.from_file(str(ROOT / 'app.py')).run()
    app.selectbox[1].select('DeepL').run()
    app.checkbox[0].check().run()
    app.button[0].click().run()
    assert not app.exception
    assert len(calls) == 2
    results = app.session_state['results']
    assert results[0]['error']
    assert results[1]['data'] == sample
    assert results[1]['quality']['status'] == 'review_required'
    assert results[1]['quality']['issues'] == []
    assert results[1]['quality']['provider'] == 'DeepL'
    app.run()
    assert len(calls) == 2

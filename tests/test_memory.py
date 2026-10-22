"""Mémoire de traduction : réutiliser sans appel ce qu'un relecteur a validé."""
from io import BytesIO
import json
from types import SimpleNamespace

from docx import Document
import pytest

from services.memory import load_memory, lookup, remember, save_memory
from services.openai_translation import translate_openai_document


class Client:
    def __init__(self):
        self.responses, self.calls = self, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        blocks = json.loads(kwargs['input'])['blocks']
        return SimpleNamespace(status='completed', output_text=json.dumps(
            {'translations': {key: 'Translated ' + value for key, value in blocks.items()}}))


def test_missing_file_is_an_empty_memory_and_round_trip_is_exact(tmp_path):
    path = tmp_path / 'memoire' / 'translation_memory.json'
    memory = load_memory(path)
    assert memory == {'version': 1, 'entries': {}}
    assert remember(memory, [('Porte  3 fermée.', 'Door 3 closed.'), ('', 'ignored'), ('Vide', ' ')], 'FR', 'EN-GB') == 1
    save_memory(memory, path)
    assert load_memory(path) == memory
    assert [item.name for item in path.parent.iterdir()] == ['translation_memory.json']  # Aucun fichier temporaire.


def test_lookup_ignores_spacing_but_not_case_or_language_pair():
    memory = load_memory('absent.json')
    remember(memory, [('Porte 3 fermée.', 'Door 3 closed.')], 'FR', 'EN-GB')
    assert lookup(memory, 'Porte   3 fermée.', 'FR', 'EN-GB') == 'Door 3 closed.'
    assert lookup(memory, 'porte 3 fermée.', 'FR', 'EN-GB') is None
    assert lookup(memory, 'Porte 3 fermée.', 'FR', 'DE') is None
    assert lookup(memory, 'Porte 3 fermée.', 'ES', 'EN-GB') is None


@pytest.mark.parametrize('content', ['pas du json', '{"version": 2, "entries": {}}', '{"version": 1, "entries": {"k": {}}}'])
def test_damaged_file_gives_a_readable_error(tmp_path, content):
    path = tmp_path / 'translation_memory.json'
    path.write_text(content, encoding='utf-8')
    with pytest.raises(ValueError, match='Mémoire de traduction illisible'):
        load_memory(path)


def test_remembered_passages_are_not_sent_and_are_reported():
    memory = load_memory('absent.json')
    remember(memory, [('Porte 3 fermée.', 'Door 3 is closed.')], 'FR', 'EN-GB')
    client, reused, passages = Client(), [], []
    translate_openai_document(b'', '.pdf', 'EN-GB', 'fake', client=client, memory=memory, reused=reused,
                              passages=passages, blocks=['Introduction.', 'Porte 3 fermée.'])
    assert json.loads(client.calls[0]['input'])['blocks'] == {'block_000': 'Introduction.'}
    assert reused == [2]
    assert passages[1] == ('Porte 3 fermée.', 'Door 3 is closed.')


def test_fully_remembered_document_makes_no_call():
    memory = load_memory('absent.json')
    remember(memory, [('Porte 3 fermée.', 'Door 3 is closed.')], 'FR', 'EN-GB')
    client = Client()
    translate_openai_document(b'', '.pdf', 'EN-GB', 'fake', client=client, memory=memory, blocks=['Porte 3 fermée.'])
    assert not client.calls


def test_formatted_word_paragraph_is_never_taken_from_memory():
    document = Document()
    document.add_paragraph('Porte 3 fermée.')
    formatted = document.add_paragraph('Porte ')
    formatted.add_run('3').bold = True
    formatted.add_run(' fermée.')
    buffer = BytesIO()
    document.save(buffer)
    memory = load_memory('absent.json')
    remember(memory, [('Porte 3 fermée.', 'Door 3 is closed.')], 'FR', 'EN-GB')
    client, reused, tagged = Client(), [], []
    result = translate_openai_document(buffer.getvalue(), '.docx', 'EN-GB', 'fake', client=client, memory=memory,
                                       reused=reused, tagged=tagged)
    assert reused == [1]  # Le paragraphe en gras est retraduit pour garder sa mise en forme.
    assert list(json.loads(client.calls[0]['input'])['blocks'].values()) == ['Porte ⟪1⟫3⟪/1⟫ fermée.']
    assert tagged == ['Door 3 is closed.', 'Translated Porte ⟪1⟫3⟪/1⟫ fermée.']
    paragraphs = Document(BytesIO(result)).paragraphs
    assert paragraphs[0].text == 'Door 3 is closed.' and paragraphs[1].runs[1].bold


def test_interface_empties_memory_only_after_confirmation(monkeypatch, tmp_path):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    path = tmp_path / 'translation_memory.json'
    memory = load_memory(path)
    remember(memory, [('Porte 3 fermée.', 'Door 3 is closed.')], 'FR', 'EN-GB')
    save_memory(memory, path)
    monkeypatch.setenv('TRANSLATION_MEMORY_PATH', str(path))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=10).run()
    assert app.button(key='memory_clear').disabled
    app.checkbox(key='memory_confirm_clear').check().run()
    app.button(key='memory_clear').click().run()
    assert not app.exception
    assert load_memory(path)['entries'] == {}

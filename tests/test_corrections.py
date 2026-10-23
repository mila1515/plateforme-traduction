"""Corrections du relecteur : fichier reconstruit sans appel, contrôles recalculés, mémoire alimentée."""
from io import BytesIO
import json
from pathlib import Path

from docx import Document
from pypdf import PdfReader
import pytest

from services.corrections import apply_corrections
from services.memory import load_memory, lookup
from services.openai_translation import render_document
from services.review import build_review

ROOT = Path(__file__).resolve().parents[1]
PASSAGES = [('Introduction.', 'Introduction.'), ('Porte 3 fermée.', 'Door 4 closed.')]


def report(passages, suffix='.pdf', **extra):
    """Rapport d'une vraie traduction PDF (ou rapport minimal pour Word, reconstruit ensuite)."""
    translated = render_document([t for _, t in passages], '.pdf', 'EN-GB') if suffix == '.pdf' else b''
    base = build_review(b'', translated, suffix, 'FR', 'EN-GB', 'GPT (OpenAI)', source_blocks=[s for s, _ in passages],
                        passages=passages)
    base.update(extra)
    return base


def test_pdf_correction_rebuilds_file_and_clears_the_fixed_alert():
    before = report(PASSAGES, brief={'description': 'x', 'tone': None})
    assert any(issue.get('check') == 'numbers' for issue in before['issues'])
    data, quality, comparison, passages, tagged, changed = apply_corrections(
        b'', '.pdf', before, PASSAGES, [t for _, t in PASSAGES], ['Introduction.', 'Door 3 closed.'])
    assert changed == [2]
    assert 'Door 3 closed.' in PdfReader(BytesIO(data)).pages[0].extract_text()
    assert passages[1] == ('Porte 3 fermée.', 'Door 3 closed.')
    assert not any(issue.get('check') == 'numbers' for issue in quality['issues'])
    assert quality['corrections']['passages'] == [2] and quality['brief'] == {'description': 'x', 'tone': None}
    assert comparison['available']


def test_unchanged_word_passage_keeps_its_formatting():
    document = Document()
    paragraph = document.add_paragraph('Appuyer sur le bouton ')
    paragraph.add_run('rouge').bold = True
    paragraph.add_run(' du panneau.')
    document.add_paragraph('Porte 3 fermée.')
    buffer = BytesIO()
    document.save(buffer)
    passages = [('Appuyer sur le bouton rouge du panneau.', 'Press the red button on the panel.'),
                ('Porte 3 fermée.', 'Door 4 closed.')]
    tagged = ['Press the ⟪1⟫red⟪/1⟫ button on the panel.', 'Door 4 closed.']
    data, *_ , changed = apply_corrections(buffer.getvalue(), '.docx', report(passages, '.docx'), passages, tagged,
                                          ['Press the red button on the panel.', 'Door 3 closed.'])
    result = Document(BytesIO(data)).paragraphs
    assert changed == [2]
    assert [(run.text, bool(run.bold)) for run in result[0].runs] == [('Press the ', False), ('red', True), (' button on the panel.', False)]
    assert result[1].text == 'Door 3 closed.'


def test_empty_correction_is_refused_without_change():
    with pytest.raises(ValueError, match='vide'):
        apply_corrections(b'', '.pdf', report(PASSAGES), PASSAGES, [t for _, t in PASSAGES], ['Introduction.', '  '])


def test_ambiguity_alerts_and_previous_corrections_are_kept():
    before = report(PASSAGES, corrections={'passages': [1], 'last_applied_at': 'x'})
    before['issues'].append({'category': 'ambiguity', 'passage': 2, 'quote': 'Porte', 'note': 'Deux lectures.'})
    *_, quality, comparison, passages, tagged, changed = apply_corrections(
        b'', '.pdf', before, PASSAGES, [t for _, t in PASSAGES], ['Introduction.', 'Door 3 closed.'])
    assert quality['corrections']['passages'] == [1, 2]
    assert any(issue['category'] == 'ambiguity' for issue in quality['issues'])


@pytest.mark.parametrize('mode,expected', [('Mémoriser toute la traduction (entièrement relue)', 2),
                                           ('Mémoriser seulement les passages corrigés', 0),
                                           ('Ne rien mémoriser', None)])
def test_interface_applies_and_saves_to_memory(monkeypatch, tmp_path, mode, expected):
    from streamlit.testing.v1 import AppTest
    path = tmp_path / 'translation_memory.json'
    monkeypatch.setenv('TRANSLATION_MEMORY_PATH', str(path))
    monkeypatch.setenv('OPENAI_API_KEY', 'fake')
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=10)
    app.session_state['results'] = [{'name': 'rapport_EN-GB.pdf', 'data': b'PDF', 'suffix': '.pdf', 'error': None,
                                     'source': b'', 'passages': PASSAGES, 'tagged': [t for _, t in PASSAGES],
                                     'quality': report(PASSAGES), 'comparison': {'available': False}}]
    app.session_state['result_language'] = 'Anglais britannique'
    app.session_state['result_provider'] = 'GPT (OpenAI)'
    app.run()
    assert not app.exception
    app.radio(key='memory_mode_0_0').set_value(mode).run()
    app.button(key='apply_corrections_0_0').click().run()
    assert not app.exception
    assert app.session_state['results'][0]['revision'] == 1  # Aucun texte modifié : fichier reconstruit à l'identique.
    if expected is None:
        assert not path.exists()
    else:
        memory = load_memory(path)
        assert len(memory['entries']) == expected
        if expected:
            assert lookup(memory, 'Porte 3 fermée.', 'FR', 'EN-GB') == 'Door 4 closed.'
    assert any('fichier reconstruit' in message.value for message in app.success)


def test_interface_passes_memory_to_gpt_only_when_enabled(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest
    import streamlit as st
    import services.openai_translation
    path = tmp_path / 'translation_memory.json'
    path.write_text(json.dumps({'version': 1, 'entries': {'k': {
        'source': 'Porte', 'target': 'Door', 'source_language': 'FR', 'target_language': 'EN'}}}), encoding='utf-8')
    sample = (ROOT / 'examples' / 'rapport_incident_FR.pdf').read_bytes()

    class Upload:
        name = 'rapport.pdf'

        def getvalue(self):
            return sample
    calls = []

    def translate(*args, **kwargs):
        calls.append(kwargs)
        kwargs['reused'].append(1)
        return sample
    monkeypatch.setenv('TRANSLATION_MEMORY_PATH', str(path))
    monkeypatch.setenv('OPENAI_API_KEY', 'fake')
    monkeypatch.setattr(st, 'file_uploader', lambda *a, **kw: [Upload()])
    monkeypatch.setattr(services.openai_translation, 'translate_openai_document', translate)
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=10).run()
    assert app.checkbox(key='use_memory').label.startswith('Réutiliser la mémoire de traduction (1 passage')
    app.checkbox[0].check().run()
    app.button(key='translate').click().run()
    assert calls[-1]['memory']['entries']
    assert app.session_state['results'][0]['quality']['memory'] == {'reused_passages': [1]}
    app.checkbox(key='use_memory').uncheck().run()
    app.button(key='translate').click().run()
    assert calls[-1]['memory'] is None

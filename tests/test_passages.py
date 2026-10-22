"""Indices par passage : signaler les erreurs graves sans alerter sur une bonne traduction."""
import json
from types import SimpleNamespace

import pytest

from services.openai_translation import translate_openai_document
from services.passages import check_passages
from services.review import build_review, readable_alerts


def checks(source, translation, source_language='FR', target_language='EN-GB'):
    return [(issue['check'], issue.get('direction')) for issue in
            check_passages([(source, translation)], source_language, target_language)]


@pytest.mark.parametrize('target,translation', [
    ('EN-GB', "The operator must not open door 3 until the train has completely stopped."),
    ('DE', 'Der Bediener darf Tür 3 nicht öffnen, bevor der Zug vollständig angehalten hat.'),
    ('ES', 'El operador no debe abrir la puerta 3 hasta que el tren se haya detenido por completo.'),
])
def test_correct_translations_raise_no_alert(target, translation):
    source = "L'opérateur ne doit pas ouvrir la porte 3 tant que le train n'est pas totalement arrêté."
    assert checks(source, translation, target_language=target) == []


@pytest.mark.parametrize('source,translation,target', [
    ("Il est interdit d'ouvrir la porte.", 'Opening the door is prohibited.', 'EN-GB'),
    ("Il est interdit d'ouvrir la porte.", 'You must not open the door.', 'EN-GB'),
    ("Il est interdit d'ouvrir la porte.", 'Das Öffnen der Tür ist verboten.', 'DE'),
    ('Le port du casque est obligatoire.', 'Es obligatorio llevar casco.', 'ES'),
    ('Voir la référence n° 5 du registre.', 'See reference No. 5 in the register.', 'EN-GB'),
])
def test_prohibitions_and_equivalent_wordings_raise_no_alert(source, translation, target):
    assert checks(source, translation, target_language=target) == []


@pytest.mark.parametrize('source,translation,expected', [
    ("L'opérateur ne doit pas ouvrir la porte 3.", 'The operator must open door 3.', ('negation', 'missing')),
    ('Le technicien peut couper le courant.', 'The technician must not cut the power.', ('negation', 'added')),
    ('Le port du casque est obligatoire sur le chantier.', 'Wearing a helmet is recommended on site.', ('obligation', 'missing')),
    ('Contrôler la porte puis signer le registre de maintenance avant le départ du train.', 'Check the door.',
     ('length', 'shorter')),
    ('Contrôler la porte avant le départ.', 'Contrôler la porte avant le départ.', ('untranslated', None)),
    ('Porte 3 à 08:10.', 'Door 4 at 08:10.', ('numbers', None)),
])
def test_serious_errors_are_located(source, translation, expected):
    assert expected in checks(source, translation)


def test_alert_names_the_passage_without_copying_the_whole_document():
    long_source = "Ne pas ouvrir la porte. " + 'Texte de contexte. ' * 20
    issues = check_passages([('Introduction.', 'Introduction.'), (long_source, 'Open the door. ' + 'Context text. ' * 20)],
                            'FR', 'EN-GB')
    assert [issue['passage'] for issue in issues] == [2]
    assert len(issues[0]['excerpt']) <= 80
    message = readable_alerts({'issues': issues})[0]
    assert message.startswith('Passage 2 (« Ne pas ouvrir la porte.') and 'négation' in message


def test_gpt_translation_exposes_aligned_passages_to_the_report():
    translations = iter(['Door 4 is closed.', 'The operator must open the door.'])

    class Client:
        responses = None

        def create(self, **kwargs):
            blocks = json.loads(kwargs['input'])['blocks']
            return SimpleNamespace(status='completed', output_text=json.dumps(
                {'translations': {key: next(translations) for key in blocks}}))
    client = Client()
    client.responses = client
    passages = []
    blocks = ['La porte 3 est fermée.', "L'opérateur ne doit pas ouvrir la porte."]
    result = translate_openai_document(b'', '.pdf', 'EN-GB', 'fake', client=client, blocks=blocks, passages=passages)
    assert passages == [(blocks[0], 'Door 4 is closed.'), (blocks[1], 'The operator must open the door.')]
    report = build_review(b'', result, '.pdf', 'FR', 'EN-GB', 'GPT (OpenAI)', source_blocks=blocks, passages=passages)
    assert 'passages' in report['checks']
    assert {(issue['passage'], issue['check']) for issue in report['issues']} == {(1, 'numbers'), (2, 'negation')}

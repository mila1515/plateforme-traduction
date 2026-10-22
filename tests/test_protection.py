"""Codes, références et liens : jamais modifiés par le moteur, même s'il se trompe."""
import json
from types import SimpleNamespace

import pytest

from services.openai_translation import translate_openai_document
from services.pdf_text import pdf_paragraphs
from services.protection import protect, restore

SOURCE = 'Voir RN-204 sur https://ex.org/doc?id=7. Contact : jean.dupont@ex.fr, pièce PX-45B.'


def test_codes_links_and_emails_are_replaced_and_restored_exactly():
    protected, mappings = protect([SOURCE, 'Norme ISO9001 et COVID-19.'])
    assert protected == ['Voir ⟦1⟧ sur ⟦2⟧. Contact : ⟦3⟧, pièce ⟦4⟧.', 'Norme ⟦5⟧ et ⟦6⟧.']
    assert mappings[0]['⟦2⟧'] == 'https://ex.org/doc?id=7'  # Point final exclu du lien.
    assert restore('See ⟦1⟧ at ⟦2⟧. Contact: ⟦3⟧, part ⟦4⟧.', mappings[0]) == \
        'See RN-204 at https://ex.org/doc?id=7. Contact: jean.dupont@ex.fr, part PX-45B.'


@pytest.mark.parametrize('text', ['1 500,50 EUR', 'le 3e étage', 'format A4', 'à 08:10', 'porte-fenêtre', 'peut-être'])
def test_numbers_and_ordinary_words_stay_translatable(text):
    assert protect([text]) == ([text], [{}])


@pytest.mark.parametrize('translation', ['See ⟦1⟧ at ⟦2⟧.', 'See ⟦1⟧ ⟦1⟧ ⟦2⟧ ⟦3⟧ ⟦4⟧.', 'See ⟦1⟧ ⟦2⟧ ⟦3⟧ ⟦4⟧ ⟦9⟧.'])
def test_lost_duplicated_or_invented_token_is_detected(translation):
    _, mappings = protect([SOURCE])
    assert restore(translation, mappings[0]) is None


class Client:
    """Le premier appel peut « perdre » les jetons ; les appels suivants les recopient."""
    def __init__(self, lose_tokens=False):
        self.responses, self.calls, self.lose_tokens = self, [], lose_tokens

    def create(self, **kwargs):
        self.calls.append(kwargs)
        blocks = json.loads(kwargs['input'])['blocks']
        lose = self.lose_tokens and len(self.calls) == 1
        return SimpleNamespace(status='completed', output_text=json.dumps({'translations': {
            key: ('Translated without codes' if lose else 'Translated ' + value) for key, value in blocks.items()}}))


def text_of(pdf_bytes):
    return ' '.join(pdf_paragraphs(pdf_bytes))


def test_model_never_sees_codes_and_output_contains_originals():
    client = Client()
    result = translate_openai_document(b'', '.pdf', 'EN-GB', 'fake', client=client, blocks=[SOURCE])
    sent = json.loads(client.calls[0]['input'])['blocks']['block_000']
    assert 'RN-204' not in sent and '⟦1⟧' in sent
    assert '⟦1⟧' in client.calls[0]['instructions']
    assert 'RN-204' in text_of(result) and 'jean.dupont@ex.fr' in text_of(result)
    assert len(client.calls) == 1


def test_lost_token_triggers_single_unprotected_request(caplog):
    client = Client(lose_tokens=True)
    result = translate_openai_document(b'', '.pdf', 'EN-GB', 'fake', client=client, blocks=[SOURCE], cache={})
    assert len(client.calls) == 2
    assert 'RN-204' in json.loads(client.calls[1]['input'])['blocks']['block_000']
    assert 'Translated Voir RN-204' in text_of(result)
    assert any('non restitué' in record.getMessage() for record in caplog.records)

"""Réglages communs : les tests n'utilisent jamais la vraie mémoire de traduction du poste."""
import pytest


@pytest.fixture(autouse=True)
def isolated_translation_memory(monkeypatch, tmp_path):
    monkeypatch.setenv('TRANSLATION_MEMORY_PATH', str(tmp_path / 'translation_memory.json'))

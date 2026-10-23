"""Identité adaptable : nom, logos et navigation sans toucher au code."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from services.branding import FALLBACK_ICON, brand

ROOT = Path(__file__).resolve().parents[1]


def test_default_identity_uses_bundled_logos():
    identity = brand()
    assert identity['name'] == 'Traduction de documents'
    assert identity['logo'].endswith('logo.svg') and identity['icon'].endswith('logo_icon.svg')
    assert brand('dark')['logo'].endswith('logo_dark.svg')


def test_company_identity_comes_from_environment(monkeypatch, tmp_path):
    logo = tmp_path / 'acme.png'
    logo.write_bytes(b'PNG')
    monkeypatch.setenv('APP_NAME', 'Portail de traduction')
    monkeypatch.setenv('APP_LOGO', str(logo))
    monkeypatch.setenv('APP_LOGO_DARK', str(tmp_path / 'absent.svg'))
    identity = brand('dark')
    assert identity['name'] == 'Portail de traduction'
    assert identity['logo'] == str(logo)  # Pas de logo sombre : le logo principal est utilisé.


def test_missing_logo_falls_back_to_a_neutral_icon(monkeypatch):
    monkeypatch.setenv('APP_LOGO', 'introuvable.svg')
    monkeypatch.setenv('APP_LOGO_DARK', 'introuvable.svg')
    monkeypatch.setenv('APP_LOGO_ICON', 'introuvable.svg')
    identity = brand()
    assert identity['logo'] is None and identity['icon'] == FALLBACK_ICON


@pytest.mark.parametrize('asset', ['logo.svg', 'logo_dark.svg', 'logo_icon.svg'])
def test_bundled_logos_are_accessible_svg(asset):
    content = (ROOT / 'assets' / asset).read_text(encoding='utf-8')
    assert content.startswith('<svg') and 'aria-label=' in content


def test_entry_point_shows_translation_page_by_default():
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=10).run()
    assert not app.exception
    assert app.title[0].value == 'Traduire des documents'
    assert [header.value for header in app.subheader][:3] == [
        ':material/upload_file: 1. Documents', ':material/language: 2. Langues et moteur',
        ':material/verified: 3. Options de qualité']

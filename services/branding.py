"""Identité visuelle adaptable : nom, slogan et logos de l'entreprise.

Rien n'est codé en dur pour une marque : chaque valeur se règle dans ``.env``
(``APP_NAME``, ``APP_TAGLINE``, ``APP_LOGO``, ``APP_LOGO_DARK``, ``APP_LOGO_ICON``).
Les couleurs et polices se règlent dans ``.streamlit/config.toml``.
Un logo introuvable est remplacé par une icône neutre, sans erreur.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets'
FALLBACK_ICON = ':material/translate:'


def _image(variable, default):
    """Chemin d'un logo (relatif à la racine du projet ou absolu), ou None s'il n'existe pas."""
    value = os.getenv(variable, '').strip()
    path = Path(value) if value else ASSETS / default
    path = path if path.is_absolute() else ROOT / path
    return str(path) if path.is_file() else None


def brand(theme_type=None):
    """Valeurs d'identité ; ``theme_type`` (« light » / « dark ») choisit le logo lisible sur ce fond."""
    logo = _image('APP_LOGO', 'logo.svg')
    dark_logo = _image('APP_LOGO_DARK', 'logo_dark.svg')
    icon = _image('APP_LOGO_ICON', 'logo_icon.svg')
    return {
        'name': os.getenv('APP_NAME', '').strip() or 'Traduction de documents',
        'tagline': os.getenv('APP_TAGLINE', '').strip() or 'Traduire, contrôler, relire',
        'logo': (dark_logo or logo) if theme_type == 'dark' else (logo or dark_logo),
        'icon': icon or FALLBACK_ICON,
    }

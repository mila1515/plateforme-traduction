"""Point d'entrée : configuration, identité visuelle et navigation entre les pages.

Les pages vivent dans ``app_pages/`` ; la logique métier reste dans ``services/``.
Nom, logos et couleurs de l'entreprise se règlent sans toucher au code
(``.env`` et ``.streamlit/config.toml``, voir docs/branding.md).
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from services.branding import brand

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
# Sortie standard (visible avec docker compose logs). Aucun nom ni contenu de document n'est journalisé.
logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO').upper(),
                    format='%(asctime)s %(levelname)s %(name)s : %(message)s')

identity = brand(st.context.theme.type)
st.set_page_config(page_title=identity['name'], page_icon=identity['icon'], layout='centered')
if identity['logo']:
    # Menu en haut de page, sans barre latérale : le logo complet (avec le nom) reste toujours visible.
    st.logo(identity['logo'], size='large')

page = st.navigation({
    '': [st.Page('app_pages/traduction.py', title='Traduire', icon=':material/translate:', default=True)],
    'Qualité': [
        st.Page('app_pages/relecture.py', title='Relecture des essais', icon=':material/fact_check:'),
        st.Page('app_pages/glossaire.py', title='Validation du glossaire', icon=':material/menu_book:'),
    ],
}, position='top')
page.run()

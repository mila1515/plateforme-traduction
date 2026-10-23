"""Relire les notions du glossaire et déclarer sa validation métier."""
from datetime import date
import os
from pathlib import Path

import streamlit as st

from services.glossary import DEFAULT_PATH, load_glossary, set_review_status

LANGUAGES = {'FR': 'Français', 'EN': 'Anglais', 'ES': 'Espagnol', 'DE': 'Allemand'}

st.set_page_config(page_title='Validation du glossaire', layout='wide')
st.title('Validation du glossaire', anchor=False)

path = Path(os.getenv('GLOSSARY_PATH', '').strip() or DEFAULT_PATH)
try:
    glossary = load_glossary(path)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

if glossary['status'] == 'approved':
    st.success(f"Version {glossary['version']} validée par {glossary['reviewed_by']} le {glossary['reviewed_at']}. "
               'Le glossaire est utilisé par défaut dans la traduction.')
else:
    st.warning(f"Version {glossary['version']} proposée, non validée : le glossaire est désactivé par défaut.")
st.caption(glossary['description'])

search = st.text_input('Rechercher un terme ou un contexte', key='glossary_search').strip().casefold()
rows = [{'Notion': entry['id'], **{label: ', '.join(entry['terms'][code]) for code, label in LANGUAGES.items()},
         'Contexte': entry['context']} for entry in glossary['entries']]
if search:
    rows = [row for row in rows if any(search in str(value).casefold() for value in row.values())]
st.caption(f"{len(rows)} notion(s) affichée(s) sur {len(glossary['entries'])}. Le premier terme de chaque langue est "
           'la traduction préférée ; les suivants sont des variantes admises.')
st.dataframe(rows, hide_index=True)
st.caption('Pour corriger un terme, modifiez `data/glossaries/technical.json` (voir docs/glossary.md) : toute '
           'modification remet le glossaire à valider.')

st.subheader('Déclarer la validation')
with st.form('glossary_review'):
    reviewer = st.text_input('Nom de la personne qui a vérifié', value=glossary.get('reviewed_by') or '')
    reviewed_at = st.date_input('Date de la vérification', value=date.today(), format='DD/MM/YYYY')
    confirmed = st.checkbox(f"Les quatre langues et les contextes des {len(glossary['entries'])} notions ont été "
                            'vérifiés par une personne bilingue et compétente sur le métier.')
    approve = st.form_submit_button('Valider le glossaire', type='primary', key='approve_glossary')
if approve:
    if not confirmed:
        st.error('Cochez la confirmation : la validation porte sur tout le fichier.')
    else:
        try:
            set_review_status(path, 'approved', reviewer, reviewed_at)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.rerun()
if glossary['status'] == 'approved' and st.button('Remettre le glossaire à valider'):
    set_review_status(path, 'proposed')
    st.rerun()
st.caption('La validation est déclarative : l’application enregistre le nom et la date, sans vérifier le réviseur. '
           'En Docker, le glossaire fait partie de l’image : validez-le en local, puis committez le fichier.')

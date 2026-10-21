"""Interface Streamlit : saisir les choix puis composer les services métier.

Les documents et rapports restent en session. Le glossaire optionnel est lu
localement ; la traduction et les contrôles sont séparés pour rester testables.
"""
import os
import json
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv
from services.files import MAX_FILES, MIMES, validate_document, output_name, make_zip
from services.translation import LANGUAGES, SOURCE_LANGUAGES, translate_document, error_message
from services.openai_translation import extract_blocks, translate_openai_document
from services.glossary import load_glossary, select_pairs
from services.review import build_review, readable_alerts

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
st.set_page_config(page_title='Traduction de documents', page_icon='📄', layout='centered')
st.title('Documents & traduction')
st.caption('Traduisez vos documents entre français, anglais, espagnol et allemand.')
uploads = st.file_uploader('Importer des PDF ou Word', type=['pdf', 'docx'], accept_multiple_files=True, help='Maximum 5 documents de 5 Mo, dans la même langue source. Les PDF doivent contenir du texte.')
selected = st.selectbox('Langue souhaitée', list(LANGUAGES))
language = LANGUAGES[selected]
provider = st.selectbox('Moteur de traduction', ['GPT (OpenAI)', 'DeepL'])
source_selected = st.selectbox('Langue du document', list(SOURCE_LANGUAGES))
source_language = SOURCE_LANGUAGES[source_selected]
same_language = source_language == language.split('-')[0]
if same_language:
    st.warning('Choisissez une langue souhaitée différente de la langue du document.')
key_name = 'OPENAI_API_KEY' if provider == 'GPT (OpenAI)' else 'DEEPL_API_KEY'
api_key = os.getenv(key_name, '').strip()
model = os.getenv('OPENAI_MODEL', '').strip() or 'gpt-4.1-mini'
if provider == 'GPT (OpenAI)':
    st.info('Word : le texte est traduit dans le document d’origine, en conservant les tableaux, images, en-têtes et pieds de page. Un texte plus long peut déplacer la mise en page ; les styles mélangés restent à vérifier. PDF : un nouveau document simple est créé, sans conservation des images ni de la présentation des tableaux. Maximum 60 000 caractères par document.')
    st.caption(f'Modèle : {model} · API payante à l’usage. Un document peut nécessiter plusieurs requêtes.')
if not api_key:
    st.warning(f'La traduction nécessite une clé {provider} : renseignez {key_name} dans .env, puis redémarrez l’application.')
consent = st.checkbox(f'J’accepte l’envoi du contenu de ces documents à {provider} pour traduction (consommation du quota API).', key=f'consent_{provider}')
try:
    glossary = load_glossary()
except ValueError as exc:
    glossary = None
    st.warning(str(exc))
use_glossary = st.checkbox('Utiliser le glossaire technique', value=False, key='use_glossary', disabled=glossary is None)
active_glossary = glossary if use_glossary and glossary is not None else None
if active_glossary is not None and active_glossary['status'] == 'proposed':
    st.warning('Glossaire de démonstration non validé : vérifiez les termes avec une personne bilingue et le métier.')
if glossary is not None:
    with st.expander('Voir le glossaire et son utilisation'):
        status = 'proposé — à valider' if glossary['status'] == 'proposed' else 'validation déclarée'
        st.caption(f"Version {glossary['version']} · {status}")
        st.write(glossary['description'])
        st.table([{'Source': pair['source_terms'][0], 'Traduction proposée': pair['target_terms'][0],
                   'Contexte': pair['context']} for pair in select_pairs(glossary, source_language, language)])
        st.caption('GPT : aide à la traduction et contrôle des termes. DeepL : contrôle après traduction uniquement. '
                   'Une alerte indique un terme attendu absent ; une variante correcte peut être signalée. '
                   'La présence du terme ne garantit pas le sens de la phrase.')
if st.button('Traduire le lot', type='primary', disabled=not uploads or not api_key or not consent or same_language):
    if len(uploads) > MAX_FILES:
        st.error('Importez au maximum 5 fichiers.')
    else:
        prepared, issues = [], []
        for index, upload in enumerate(uploads, 1):
            data = upload.getvalue()
            try:
                suffix = validate_document(upload.name, data)
                blocks = extract_blocks(data, suffix) if provider == 'GPT (OpenAI)' else None
                prepared.append((index, upload.name, data, suffix, blocks))
            except ValueError as exc:
                issues.append(f'{upload.name} : {exc}')
        # Validate the complete batch before making any billable calls.
        if issues:
            for issue in issues:
                st.error(issue)
        else:
            results = []
            progress = st.progress(0)
            for position, (index, name, data, suffix, blocks) in enumerate(prepared, 1):
                with st.spinner(f'Traduction de {name}…'):
                    try:
                        if provider == 'GPT (OpenAI)':
                            pairs = select_pairs(active_glossary, source_language, language, '\n'.join(blocks)) if active_glossary else []
                            translated = translate_openai_document(data, suffix, language, api_key, model=model, blocks=blocks, source_language=source_language, glossary_pairs=pairs)
                        else:
                            translated = translate_document(data, suffix, language, api_key, source_language=source_language)
                        comparison = {}
                        quality = build_review(data, translated, suffix, source_language, language, provider,
                                               model=model if provider == 'GPT (OpenAI)' else None,
                                               source_blocks=blocks, glossary=active_glossary, comparison=comparison)
                        results.append({'name': output_name(name, language, index), 'data': translated, 'suffix': suffix, 'error': None, 'quality': quality, 'comparison': comparison})
                    except Exception as exc:
                        results.append({'name': name, 'data': None, 'suffix': suffix, 'error': error_message(exc)})
                progress.progress(position / len(prepared))
            st.session_state['results'] = results
            st.session_state['result_language'] = selected
            st.session_state['result_provider'] = provider
            st.session_state['result_source'] = source_selected
if 'results' in st.session_state:
    st.subheader('Résultats')
    st.caption(f"{st.session_state.get('result_source', 'Français')} → {st.session_state['result_language']} · {st.session_state.get('result_provider', 'DeepL')}")
    st.caption('Traductions automatiques à relire avant utilisation.')
    successful = []
    for index, result in enumerate(st.session_state['results']):
        if result['error']:
            st.error(f"{result['name']} : {result['error']}")
        else:
            successful.append((result['name'], result['data']))
            with st.container(border=True):
                filename_column, download_column = st.columns([4, 1.5], vertical_alignment='center')
                with filename_column:
                    st.text(result['name'])
                with download_column:
                    st.download_button('Télécharger', result['data'], result['name'], MIMES[result['suffix']], key=f'result_{index}')
                quality = result.get('quality')
                comparison = result.get('comparison', {})
                with st.expander('Comparer les textes'):
                    if comparison.get('available'):
                        source_column, target_column = st.columns(2)
                        with source_column:
                            st.caption(f"Original · {st.session_state.get('result_source', 'Français')}")
                            with st.container(height=320, border=True):
                                st.text(comparison['source'])
                        with target_column:
                            st.caption(f"Traduction · {st.session_state['result_language']}")
                            with st.container(height=320, border=True):
                                st.text(comparison['translation'])
                        st.caption('Texte extrait, sans reproduction de la mise en page ni alignement garanti des paragraphes. Vérifiez les tableaux et images dans les fichiers téléchargés.')
                    else:
                        st.info('Comparaison indisponible pour ce résultat. Vous pouvez toujours télécharger le document.')
                    if quality and quality['status'] != 'unavailable':
                        messages = readable_alerts(quality)
                        if messages:
                            for message in messages:
                                st.warning(message)
                        else:
                            st.caption('Aucun écart détecté par les contrôles activés. Le sens reste à vérifier.')
                if quality:
                    with st.expander('Détails et rapport de contrôle'):
                        if quality['status'] == 'unavailable':
                            st.warning(quality['limitations'])
                        else:
                            if quality['issues']:
                                st.json(quality['issues'])
                            else:
                                st.write('Aucun écart détecté par les contrôles activés. Le sens reste à vérifier.')
                            if quality.get('glossary'):
                                st.caption(f"Glossaire version {quality['glossary']['version']} · {quality['glossary']['status']} · "
                                           + ('aide GPT et contrôle' if quality['glossary_usage'] == 'prompt_and_check' else 'contrôle uniquement'))
                            st.caption(quality['limitations'])
                        st.download_button('Télécharger le rapport de contrôle', json.dumps(quality, ensure_ascii=False, indent=2),
                                           result['name'] + '.quality.json', 'application/json', key=f'quality_{index}')
    if len(successful) > 1:
        st.download_button('Tout télécharger (ZIP)', make_zip(successful), 'documents_traduits.zip', 'application/zip')
    if successful:
        with st.expander('Aide pour imprimer'):
            st.write('Ouvrez le document téléchargé dans Word ou un lecteur PDF, puis utilisez Ctrl + P.')
    if any(result['error'] for result in st.session_state['results']):
        st.caption('Pour relancer un échec, importez uniquement le fichier concerné. Une relance peut consommer à nouveau votre quota.')
    if st.button('Effacer les résultats'):
        del st.session_state['results']
        st.rerun()

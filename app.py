import os
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv
from services.files import MAX_FILES, MIMES, validate_document, output_name, make_zip
from services.translation import LANGUAGES, SOURCE_LANGUAGES, translate_document, error_message
from services.openai_translation import extract_blocks, translate_openai_document

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
st.set_page_config(page_title='Traduction de documents', page_icon='📄', layout='centered')
st.title('Documents & traduction')
st.caption('Traduisez vos documents entre français, anglais, espagnol, allemand et chinois.')
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
    st.info('OpenAI traduit le texte et recrée un PDF ou Word avec une mise en page simple. Les images, en-têtes, pieds de page et la présentation des tableaux ne sont pas conservés. Maximum 60 000 caractères par document.')
    st.caption(f'Modèle : {model} · API payante à l’usage. Un document peut nécessiter plusieurs requêtes.')
if not api_key:
    st.warning(f'La traduction nécessite une clé {provider} : renseignez {key_name} dans .env, puis redémarrez l’application.')
consent = st.checkbox(f'J’accepte l’envoi du contenu de ces documents à {provider} pour traduction (consommation du quota API).', key=f'consent_{provider}')
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
                            translated = translate_openai_document(data, suffix, language, api_key, model=model, blocks=blocks, source_language=source_language)
                        else:
                            translated = translate_document(data, suffix, language, api_key, source_language=source_language)
                        results.append({'name': output_name(name, language, index), 'data': translated, 'suffix': suffix, 'error': None})
                    except Exception as exc:
                        results.append({'name': name, 'data': None, 'suffix': suffix, 'error': error_message(exc)})
                progress.progress(position / len(prepared))
            st.session_state['results'] = results
            st.session_state['result_language'] = selected
            st.session_state['result_provider'] = provider
            st.session_state['result_source'] = source_selected
if 'results' in st.session_state:
    st.subheader(f"Résultats du dernier lot · {st.session_state.get('result_source', 'Français')} → {st.session_state['result_language']} · {st.session_state.get('result_provider', 'DeepL')}")
    successful = []
    for index, result in enumerate(st.session_state['results']):
        if result['error']:
            st.error(f"{result['name']} : {result['error']}")
        else:
            successful.append((result['name'], result['data']))
            st.download_button(f"Télécharger {result['name']}", result['data'], result['name'], MIMES[result['suffix']], key=f'result_{index}')
    if successful:
        st.download_button('Tout télécharger (ZIP)', make_zip(successful), 'documents_traduits.zip', 'application/zip')
        st.info('Pour imprimer : ouvrez le document téléchargé dans votre lecteur PDF ou Word, puis utilisez Ctrl + P.')
    st.caption('Pour relancer un échec, importez uniquement le fichier concerné et cliquez sur Traduire le lot. Une relance peut consommer à nouveau votre quota.')
    if st.button('Effacer les résultats'):
        del st.session_state['results']
        st.rerun()

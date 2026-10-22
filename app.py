"""Interface Streamlit : saisir les choix puis composer les services métier.

Les documents et rapports restent en session. Le glossaire optionnel est lu
localement ; la traduction et les contrôles sont séparés pour rester testables.
"""
import os
import json
import logging
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv
import deepl
import openai
from services.files import MAX_FILES, MIMES, validate_document, output_name, make_zip
from services.translation import LANGUAGES, SOURCE_LANGUAGES, translate_document, error_message
from services.openai_translation import extract_blocks, translate_openai_document
from services.glossary import load_glossary, select_pairs
from services.review import build_review, readable_alerts
from services.semantic_review import review_meaning, fingerprint, MAX_REVIEW_TEXT
from services.ambiguity import find_ambiguities, DEFAULT_MODEL as AMBIGUITY_MODEL
from services.memory import DEFAULT_PATH as MEMORY_PATH, load_memory, save_memory, remember
from services.corrections import apply_corrections
import pandas as pd

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
# Sortie standard (visible avec docker compose logs). Aucun nom ni contenu de document n'est journalisé.
logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO').upper(),
                    format='%(asctime)s %(levelname)s %(name)s : %(message)s')
log = logging.getLogger('app')
EXPECTED_ERRORS = (ValueError, openai.APIError, deepl.DeepLException)

GPT = 'GPT (OpenAI)'
BRIEF_TONES = {'Automatique': None, 'Formel (vouvoiement)': 'formal', 'Courant': 'informal'}
MEMORY_MODES = {'Mémoriser seulement les passages corrigés': 'changed',
                'Mémoriser toute la traduction (entièrement relue)': 'all',
                'Ne rien mémoriser': 'none'}
DEEPL_FORMALITY = {'formal': 'prefer_more', 'informal': 'prefer_less'}
SEVERITIES = {'critical': 'critique', 'major': 'majeur', 'minor': 'mineur'}


def log_failure(action, exc):
    """Erreur attendue : type seul. Erreur imprévue : trace complète pour corriger le code."""
    if isinstance(exc, EXPECTED_ERRORS):
        log.warning('%s : échec %s', action, type(exc).__name__)
    else:
        log.exception('%s : erreur imprévue', action)


def prepare_batch(uploads, provider):
    """Valider tout le lot avant le moindre appel facturé."""
    prepared, issues = [], []
    for index, upload in enumerate(uploads, 1):
        data = upload.getvalue()
        try:
            suffix = validate_document(upload.name, data)
            blocks = extract_blocks(data, suffix) if provider == GPT else None
            prepared.append((index, upload.name, data, suffix, blocks))
        except ValueError as exc:
            issues.append(f'{upload.name} : {exc}')
    return prepared, issues


def translate_one(data, suffix, blocks, provider, source_language, language, api_key, model, glossary, brief,
                  ambiguity_model=None, memory=None):
    """Traduire un document puis construire son rapport et sa comparaison.

    Avec ``ambiguity_model``, un appel OpenAI séparé repère les ambiguïtés du
    texte source ; son échec n'empêche jamais de livrer la traduction.
    """
    passages = []  # Paires alignées (GPT uniquement) pour les contrôles passage par passage.
    tagged, reused = [], []  # Traductions balisées (corrections) et passages repris de la mémoire.
    if provider == GPT:
        pairs = select_pairs(glossary, source_language, language, '\n'.join(blocks)) if glossary else []
        translated = translate_openai_document(data, suffix, language, api_key, model=model, blocks=blocks,
                                               source_language=source_language, glossary_pairs=pairs,
                                               cache=st.session_state.setdefault('translation_cache', {}),
                                               passages=passages, brief=brief, memory=memory,
                                               reused=reused, tagged=tagged)
    else:
        translated = translate_document(data, suffix, language, api_key, source_language=source_language,
                                        formality=DEEPL_FORMALITY.get(brief['tone']))
    doubts, ambiguity_error = [], None
    if ambiguity_model:
        try:
            source_blocks = blocks if blocks is not None else extract_blocks(data, suffix, None)
            doubts = find_ambiguities(source_blocks, source_language, os.getenv('OPENAI_API_KEY', '').strip(),
                                      model=ambiguity_model)
        except Exception as exc:
            log_failure('Analyse des ambiguïtés', exc)
            ambiguity_error = error_message(exc)
    comparison = {}
    quality = build_review(data, translated, suffix, source_language, language, provider,
                           model=model if provider == GPT else None,
                           source_blocks=blocks, glossary=glossary, comparison=comparison, passages=passages,
                           doubts=doubts)
    if brief['description'] or brief['tone']:
        quality['brief'] = brief  # Traçabilité : texte saisi par l'utilisateur, pas le document.
    if ambiguity_model:
        quality['ambiguity'] = {'model': ambiguity_model, 'found': len(doubts), 'error': ambiguity_error}
    if reused:
        quality['memory'] = {'reused_passages': reused}
    return translated, quality, comparison, {'passages': passages, 'tagged': tagged}


def render_semantic_review(result, index, comparison, quality, model):
    """Avis IA à la demande : consentement distinct, un seul appel par paire de textes."""
    st.markdown('**Analyse du sens par IA**')
    st.caption('Cherche les contresens, négations inversées, omissions et ajouts. Avis indicatif à confirmer par une personne bilingue ; les textes ne sont pas corrigés automatiquement.')
    review_key = os.getenv('OPENAI_API_KEY', '').strip()
    review_model = os.getenv('OPENAI_REVIEW_MODEL', '').strip() or model
    pair_id = fingerprint(comparison['source'], comparison['translation'])
    oversized = max(len(comparison['source']), len(comparison['translation'])) > MAX_REVIEW_TEXT
    if oversized:
        st.info('Analyse du sens limitée à 12 000 caractères par texte. Le document complet dépasse cette limite et ne sera pas envoyé pour analyse.')
    if not review_key:
        st.caption('Une clé OpenAI est nécessaire à cette analyse, même si le document a été traduit par DeepL.')
    st.caption(f'Moteur d’analyse : OpenAI · {review_model}. Un appel supplémentaire payant pour les deux textes complets. Le moteur peut être le même que celui de traduction.')
    review_consent = st.checkbox('J’autorise l’envoi de l’original et de la traduction à OpenAI pour cette analyse supplémentaire payante.', key=f'semantic_consent_{index}_{pair_id}')
    if st.button('Analyser le sens', key=f'semantic_run_{index}_{pair_id}',
                 disabled=not review_key or not review_consent or oversized or 'semantic_review' in result):
        with st.spinner('Analyse du sens…'):
            try:
                result['semantic_review'] = review_meaning(
                    comparison['source'], comparison['translation'], quality['source_language'],
                    quality['target_language'], review_key, model=review_model)
                result.pop('semantic_error', None)
            except Exception as exc:
                log_failure('Analyse du sens', exc)
                result['semantic_error'] = error_message(exc)
    if result.get('semantic_error'):
        st.error(result['semantic_error'])
    semantic = result.get('semantic_review')
    if not semantic:
        return
    if semantic['assessment'] == 'suspected_issues':
        st.warning('Des problèmes de sens sont suspectés. Vérifiez les passages ci-dessous.')
    elif semantic['assessment'] == 'inconclusive':
        st.warning('L’IA ne peut pas conclure sur le sens. Relecture humaine nécessaire.')
    else:
        st.info('Aucun problème de sens signalé par l’IA. Cela ne valide pas la traduction.')
    st.text(semantic['summary'])
    if semantic.get('discarded_issues'):
        st.caption(f"{semantic['discarded_issues']} passage(s) signalé(s) par l’IA écarté(s) : "
                   'citation introuvable dans les textes. Relisez le document entier.')
    for number, issue in enumerate(semantic['issues'], 1):
        st.caption(f"Passage {number} · problème potentiel {SEVERITIES[issue['severity']]}")
        st.text('Original : ' + (issue['source_quote'] or '(aucun passage correspondant)'))
        st.text('Traduction : ' + (issue['translation_quote'] or '(passage potentiellement omis)'))
        st.text(issue['explanation'])
    st.download_button('Télécharger l’analyse du sens', json.dumps(semantic, ensure_ascii=False, indent=2),
                       result['name'] + '.semantic.json', 'application/json', key=f'semantic_report_{index}')


def render_comparison(result, index, model):
    """Original et traduction côte à côte, avis IA optionnel et alertes locales."""
    quality = result.get('quality')
    comparison = result.get('comparison', {})
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
        render_semantic_review(result, index, comparison, quality, model)
    else:
        st.info('Comparaison indisponible pour ce résultat. Vous pouvez toujours télécharger le document.')
    if quality and quality['status'] != 'unavailable':
        st.caption('Contrôles complémentaires : nombres, références, glossaire et, avec GPT, indices par passage '
                   '(négation, obligation, longueur, non-traduction). Ce sont des indices à vérifier, pas un jugement du sens.')
        messages = readable_alerts(quality)
        for message in messages:
            st.warning(message)
        if not messages:
            st.caption('Aucun écart détecté par les contrôles activés. Le sens reste à vérifier.')
    for notice in (quality or {}).get('untranslated_parts', []):
        st.info(notice)
    reused = (quality or {}).get('memory', {}).get('reused_passages')
    if reused:
        st.caption(f"{len(reused)} passage(s) repris de la mémoire de traduction (déjà validés) : "
                   + ', '.join(map(str, reused)) + '.')
    ambiguity = (quality or {}).get('ambiguity')
    if ambiguity and ambiguity['error']:
        st.info('Analyse des ambiguïtés indisponible : ' + ambiguity['error'])
    elif ambiguity and not ambiguity['found']:
        st.caption(f"Aucune ambiguïté repérée dans l’original ({ambiguity['model']}). Cela ne valide pas le sens.")


def render_quality_details(result, index, quality):
    """Données techniques du contrôle et rapport JSON téléchargeable."""
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


def render_corrections(result, index):
    """Corriger les passages traduits, reconstruire le fichier et alimenter la mémoire."""
    revision = result.get('revision', 0)
    table = pd.DataFrame({'N°': range(1, len(result['passages']) + 1),
                          'Original': [source for source, _ in result['passages']],
                          'Traduction': [target for _, target in result['passages']]})
    edited = st.data_editor(table, key=f'corrections_{index}_{revision}', hide_index=True, num_rows='fixed',
                            disabled=['N°', 'Original'])
    st.caption('Modifiez la colonne Traduction puis appliquez. Aucun appel au moteur : le fichier est reconstruit '
               'et les contrôles recalculés. Word : un paragraphe corrigé qui contenait du gras ou un lien garde sa '
               'mise en forme de façon approximative.')
    mode = st.radio('Mémoire de traduction', list(MEMORY_MODES), key=f'memory_mode_{index}_{revision}', horizontal=False)
    if st.button('Appliquer les corrections', key=f'apply_corrections_{index}_{revision}'):
        report = result['quality']
        glossary_used = glossary if glossary is not None and report.get('glossary') \
            and report['glossary']['sha256'] == glossary['sha256'] else None
        try:
            translated, quality, comparison, passages, tagged, changed = apply_corrections(
                result['source'], result['suffix'], report, result['passages'], result['tagged'],
                list(edited['Traduction']), glossary=glossary_used)
        except ValueError as exc:
            st.error(str(exc))
            return
        result.update({'data': translated, 'quality': quality, 'comparison': comparison, 'passages': passages,
                       'tagged': tagged, 'revision': revision + 1})
        result.pop('semantic_review', None)  # L'avis portait sur l'ancienne traduction.
        saved = 0
        if MEMORY_MODES[mode] != 'none':
            pairs = passages if MEMORY_MODES[mode] == 'all' else [passages[number - 1] for number in changed]
            try:
                memory = load_memory(memory_path)
                saved = remember(memory, pairs, report['source_language'], report['target_language'])
                save_memory(memory, memory_path)
            except (OSError, ValueError) as exc:
                log_failure('Mémoire de traduction', exc)
                st.session_state['correction_notice'] = f'Corrections appliquées, mais mémoire non enregistrée : {exc}'
                st.rerun()
        st.session_state['correction_notice'] = (f'{len(changed)} passage(s) corrigé(s), fichier reconstruit ; '
                                                 f'{saved} passage(s) enregistré(s) dans la mémoire.')
        st.rerun()


def render_result(result, index, model):
    with st.container(border=True):
        filename_column, download_column = st.columns([4, 1.5], vertical_alignment='center')
        with filename_column:
            st.text(result['name'])
        with download_column:
            st.download_button('Télécharger', result['data'], result['name'], MIMES[result['suffix']], key=f'result_{index}')
        with st.expander('Comparer les textes'):
            render_comparison(result, index, model)
        if result.get('passages') and len(result.get('tagged', [])) == len(result['passages']):
            with st.expander('Corriger la traduction'):
                render_corrections(result, index)
        if result.get('quality'):
            with st.expander('Détails et rapport de contrôle'):
                render_quality_details(result, index, result['quality'])


st.set_page_config(page_title='Traduction de documents', page_icon='📄', layout='centered')
st.title('Documents & traduction')
st.caption('Traduisez vos documents entre français, anglais, espagnol et allemand.')
uploads = st.file_uploader('Importer des PDF ou Word', type=['pdf', 'docx'], accept_multiple_files=True, help='Maximum 5 documents de 5 Mo, dans la même langue source. Les PDF doivent contenir du texte.')
selected = st.selectbox('Langue souhaitée', list(LANGUAGES))
language = LANGUAGES[selected]
provider = st.selectbox('Moteur de traduction', [GPT, 'DeepL'])
source_selected = st.selectbox('Langue du document', list(SOURCE_LANGUAGES))
source_language = SOURCE_LANGUAGES[source_selected]
same_language = source_language == language.split('-')[0]
if same_language:
    st.warning('Choisissez une langue souhaitée différente de la langue du document.')
key_name = 'OPENAI_API_KEY' if provider == GPT else 'DEEPL_API_KEY'
api_key = os.getenv(key_name, '').strip()
model = os.getenv('OPENAI_MODEL', '').strip() or 'gpt-4.1-mini'
if provider == GPT:
    st.info('Word : le texte est traduit dans le document d’origine, en conservant les tableaux, images, en-têtes et pieds de page. Un texte plus long peut déplacer la mise en page ; les styles mélangés restent à vérifier. PDF : un nouveau document simple est créé, sans conservation des images ni de la présentation des tableaux. Maximum 60 000 caractères par document.')
    st.caption(f'Modèle : {model} · API payante à l’usage. Un document peut nécessiter plusieurs requêtes.')
else:
    st.caption('DeepL facture chaque document au minimum 50 000 caractères, même pour une page courte. '
               'Un lot de 5 fichiers consomme donc au moins 250 000 caractères du quota.')
if not api_key:
    st.warning(f'La traduction nécessite une clé {provider} : renseignez {key_name} dans .env, puis redémarrez l’application.')
consent = st.checkbox(f'J’accepte l’envoi du contenu de ces documents à {provider} pour traduction (consommation du quota API).', key=f'consent_{provider}')
with st.expander('Contexte du document (facultatif)'):
    brief_description = st.text_area(
        'Décrivez le document', max_chars=500, key='brief_description',
        placeholder='Ex. : procédure de maintenance ferroviaire pour des techniciens. '
                    '« contrôle » = inspection ; « consignation » = lockout.')
    brief_tone = st.selectbox('Ton de la traduction', list(BRIEF_TONES), key='brief_tone')
    st.caption('GPT : description et ton ajoutés aux consignes, sans priorité sur la fidélité du sens. '
               'DeepL : seul le ton est utilisé (vouvoiement en allemand, espagnol et français).')
brief = {'description': brief_description.strip(), 'tone': BRIEF_TONES[brief_tone]}
try:
    glossary = load_glossary()
except ValueError as exc:
    glossary = None
    st.warning(str(exc))
# Coché par défaut seulement une fois le glossaire validé par le métier.
use_glossary = st.checkbox('Utiliser le glossaire technique', key='use_glossary', disabled=glossary is None,
                           value=glossary is not None and glossary['status'] == 'approved')
active_glossary = glossary if use_glossary and glossary is not None else None
ambiguity_model = os.getenv('OPENAI_AMBIGUITY_MODEL', '').strip() or AMBIGUITY_MODEL
openai_key = bool(os.getenv('OPENAI_API_KEY', '').strip())
find_doubts = st.checkbox(
    f'Repérer les ambiguïtés de l’original (j’accepte l’envoi du texte source à OpenAI, {ambiguity_model}, '
    'appel supplémentaire payant)', value=False, key='find_ambiguities', disabled=not openai_key)
st.caption('Signale les phrases à double sens (pronom, portée d’une négation ou d’une condition, terme à deux sens) '
           'que la traduction a dû trancher. Fonctionne aussi avec DeepL.'
           + ('' if openai_key else ' Nécessite OPENAI_API_KEY dans .env.'))
memory_path = Path(os.getenv('TRANSLATION_MEMORY_PATH', '').strip() or MEMORY_PATH)
try:
    memory = load_memory(memory_path)
    memory_error = None
except ValueError as exc:
    memory, memory_error = None, str(exc)
memory_size = len(memory['entries']) if memory else 0
use_memory = st.checkbox(f'Réutiliser la mémoire de traduction ({memory_size} passage(s) validé(s))',
                         value=True, key='use_memory', disabled=provider != GPT or not memory_size)
if memory_error:
    st.warning(memory_error)
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
    prepared, issues = prepare_batch(uploads, provider) if len(uploads) <= MAX_FILES else ([], ['Importez au maximum 5 fichiers.'])
    for issue in issues:
        st.error(issue)
    if not issues:
        results = []
        progress = st.progress(0)
        for position, (index, name, data, suffix, blocks) in enumerate(prepared, 1):
            with st.spinner(f'Traduction de {name}…'):
                try:
                    translated, quality, comparison, aligned = translate_one(
                        data, suffix, blocks, provider, source_language, language, api_key, model, active_glossary,
                        brief, ambiguity_model if find_doubts else None,
                        memory if use_memory and provider == GPT else None)
                    results.append({'name': output_name(name, language, index), 'data': translated, 'suffix': suffix,
                                    'error': None, 'quality': quality, 'comparison': comparison,
                                    'source': data, **aligned})
                except Exception as exc:
                    log_failure(f'Traduction du document {index} ({provider}, {suffix})', exc)
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
    if 'correction_notice' in st.session_state:
        st.success(st.session_state.pop('correction_notice'))
    successful = []
    for index, result in enumerate(st.session_state['results']):
        if result['error']:
            st.error(f"{result['name']} : {result['error']}")
        else:
            successful.append((result['name'], result['data']))
            render_result(result, index, model)
    if len(successful) > 1:
        st.download_button('Tout télécharger (ZIP)', make_zip(successful), 'documents_traduits.zip', 'application/zip')
    if successful:
        with st.expander('Aide pour imprimer'):
            st.write('Ouvrez le document téléchargé dans Word ou un lecteur PDF, puis utilisez Ctrl + P.')
    if any(result['error'] for result in st.session_state['results']):
        st.caption('Pour relancer un échec, importez uniquement le fichier concerné. Avec GPT, les passages déjà traduits '
                   'dans cette session sont réutilisés ; les autres consomment à nouveau votre quota.')
    if st.button('Effacer les résultats'):
        del st.session_state['results']
        st.session_state.pop('translation_cache', None)
        st.rerun()
# Gestion en bas de page : ses boutons ne précèdent jamais « Traduire le lot ».
with st.expander('Gérer la mémoire de traduction'):
    st.caption('Passages validés par un relecteur, réutilisés sans appel au moteur (GPT uniquement). Le fichier '
               f'reste sur ce poste ({memory_path.name}) et contient des phrases de vos documents.')
    if memory_size:
        st.download_button('Télécharger la mémoire (JSON)', json.dumps(memory, ensure_ascii=False, indent=2),
                           'translation_memory.json', 'application/json', key='memory_download')
        confirm_clear = st.checkbox('Je confirme vouloir vider la mémoire', key='memory_confirm_clear')
        if st.button('Vider la mémoire', disabled=not confirm_clear, key='memory_clear'):
            save_memory({'version': memory['version'], 'entries': {}}, memory_path)
            st.rerun()

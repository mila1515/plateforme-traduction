"""Relecture humaine des essais réels : une décision par cas, sans modifier les traductions."""
import json
import os
from pathlib import Path

import streamlit as st

from services.glossary import load_glossary
from services.passages import check_passages
from services.review import passage_detail, readable_alerts
from services.trials import CORPUS_PATH, RUNS_DIR, evaluate, list_trials, load_trial, review_summary, save_review

LABELS = {'pending': 'En attente', 'accepted': 'Acceptée', 'rejected': 'Rejetée'}

st.set_page_config(page_title='Relecture des essais', page_icon='📝', layout='wide')
st.title('Relecture des essais')
st.caption('Décidez pour chaque traduction si elle est acceptable. Les traductions enregistrées ne sont jamais '
           'modifiées ; seules vos décisions, notes et votre nom sont ajoutés au fichier d’essai.')

runs_dir = Path(os.getenv('EVALUATION_RUNS_PATH', '').strip() or RUNS_DIR)
corpus_path = Path(os.getenv('EVALUATION_CORPUS_PATH', '').strip() or CORPUS_PATH)
trials = list_trials(runs_dir)
if not trials or not corpus_path.exists():
    st.info('Aucun essai à relire. Les essais sont créés en local avec `python -B -m evaluation.live … --confirm` '
            'dans `evaluation/runs/`, qui reste sur ce poste (non inclus dans l’image Docker).')
    st.stop()

path = st.selectbox('Essai', trials, format_func=lambda item: item.stem)
trial = load_trial(path)
corpus = json.loads(corpus_path.read_text(encoding='utf-8'))
focus = {case['id']: case.get('focus', '') for case in corpus}
metadata = trial.get('metadata', {})
source_language, target_language = metadata.get('source_language'), metadata.get('target_language')
st.caption(' · '.join(str(value) for value in (metadata.get('provider'), metadata.get('model'), metadata.get('date'),
                                               f'{source_language} → {target_language}') if value))
try:
    glossary = load_glossary() if source_language and target_language else None
except ValueError:
    glossary = None
report = evaluate(corpus, trial, glossary=glossary)

decided = sum(result['human_decision'] != 'pending' for result in trial['results'])
st.progress(decided / len(trial['results']), text=f'{decided} cas relus sur {len(trial["results"])}')
reviewer = st.text_input('Votre nom (réviseur)', key='reviewer',
                         value=next((result['reviewer'] for result in trial['results'] if result.get('reviewer')), ''))
pending_only = st.toggle('Afficher seulement les cas en attente', key=f'pending_only_{path.stem}')
st.caption('Rejetez toute inversion de négation, d’obligation, de responsabilité ou de valeur. '
           'Un rejet exige une note expliquant l’erreur.')

decisions = {}
with st.form(f'review_{path.stem}'):
    for result, row in zip(trial['results'], report['results'], strict=True):
        if pending_only and result['human_decision'] != 'pending':
            continue
        with st.container(border=True):
            st.markdown(f"**{result['id']}** · {focus.get(result['id'], '')}")
            source_column, target_column = st.columns(2)
            with source_column:
                st.caption('Original')
                st.text(result['source'])
            with target_column:
                st.caption('Traduction')
                st.text(result['translation'])
            # Alertes automatiques : une aide pour cibler, pas un verdict.
            alerts = readable_alerts({'issues': row['control']['issues']})
            if source_language and target_language:
                alerts += [passage_detail(issue) for issue in
                           check_passages([(result['source'], result['translation'])], source_language, target_language)]
            for alert in alerts:
                st.warning(alert)
            key = f"{path.stem}_{result['id']}"
            decision = st.radio('Décision', list(LABELS), format_func=LABELS.get, horizontal=True, key=f'decision_{key}',
                                index=list(LABELS).index(result['human_decision']))
            notes = st.text_area('Notes de relecture', value=result.get('review_notes') or '', key=f'notes_{key}',
                                 height=68, placeholder='Obligatoire pour un rejet : quelle erreur, quelle gravité ?')
            decisions[result['id']] = {'human_decision': decision, 'review_notes': notes}
    submitted = st.form_submit_button('Enregistrer les décisions', type='primary')
if submitted:
    try:
        changed = save_review(path, decisions, reviewer)
    except ValueError as exc:
        st.error(str(exc))
    else:
        st.session_state['review_notice'] = f'{changed} décision(s) enregistrée(s).'
        st.rerun()
if 'review_notice' in st.session_state:
    st.success(st.session_state.pop('review_notice'))

st.subheader('Bilan')
summary = review_summary(report)
columns = st.columns(5)
for column, (label, value) in zip(columns, [
        ('Rejetés, avec alerte', summary['rejected_with_alert']),
        ('Rejetés, sans alerte', summary['rejected_without_alert']),
        ('Acceptés, avec alerte', summary['accepted_with_alert']),
        ('Acceptés, sans alerte', summary['accepted_without_alert']),
        ('En attente', summary['pending'])], strict=True):
    column.metric(label, value)
st.caption('« Rejetés, sans alerte » : erreurs que les contrôles automatiques ont ratées. « Acceptés, avec alerte » : '
           'fausses alertes probables. Ces chiffres ne valent que pour ce corpus et cette relecture.')
st.download_button('Télécharger le rapport de l’essai', json.dumps(report, ensure_ascii=False, indent=2),
                   f'{path.stem}-rapport.json', 'application/json')

"""Rapport qualité en Word, lisible par un relecteur non informaticien.

Même contenu que le rapport JSON (conservé pour l'archivage), présenté en
phrases et en tableaux : synthèse, analyse du sens, alertes avec l'original et
la traduction, ambiguïtés, limites, et un cadre de relecture à signer.
"""
from datetime import date
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from services.review import passage_detail, readable_alerts

LANGUAGE_NAMES = {'FR': 'français', 'EN': 'anglais', 'EN-GB': 'anglais britannique', 'ES': 'espagnol', 'DE': 'allemand'}
SEVERITIES = {'critical': 'Critique', 'major': 'Majeur', 'minor': 'Mineur'}
VERDICTS = {'suspected_issues': 'Des problèmes de sens sont suspectés : vérifiez les passages ci-dessous.',
            'inconclusive': 'L’IA ne peut pas conclure sur le sens : relecture humaine nécessaire.',
            'no_issue_detected': 'Aucun problème de sens signalé par l’IA. Cela ne valide pas la traduction.'}
GREY = RGBColor(0x59, 0x59, 0x59)


def _table(document, headers, rows, widths=None):
    table = document.add_table(rows=1, cols=len(headers))
    table.style = 'Table Grid'
    for cell, header in zip(table.rows[0].cells, headers, strict=True):
        cell.text = ''
        cell.paragraphs[0].add_run(header).bold = True
    for row in rows:
        for cell, value in zip(table.add_row().cells, row, strict=True):
            cell.text = str(value)
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(9)
    return table


def _note(document, text):
    run = document.add_paragraph().add_run(text)
    run.italic, run.font.color.rgb, run.font.size = True, GREY, Pt(9)


def _passage(passages, number):
    return passages[number - 1] if passages and 0 < number <= len(passages) else ('', '')


def build_quality_report(name, quality, passages=None, semantic=None):
    """Renvoie le .docx ; ``passages`` (paires alignées) permet d'afficher original et traduction."""
    document = Document()
    document.styles['Normal'].font.name = 'Calibri'
    document.styles['Normal'].font.size = Pt(10)
    document.add_heading('Rapport qualité de la traduction', level=0)
    source = LANGUAGE_NAMES.get(quality.get('source_language'), quality.get('source_language'))
    target = LANGUAGE_NAMES.get(quality.get('target_language'), quality.get('target_language'))
    glossary = quality.get('glossary')
    _table(document, ['Élément', 'Valeur'], [
        ('Document', name),
        ('Langues', f'{source} → {target}'),
        ('Moteur', ' · '.join(filter(None, [quality.get('provider'), quality.get('model')]))),
        ('Glossaire', f"version {glossary['version']} ({'validé' if glossary['status'] == 'approved' else 'non validé'})"
         if glossary else 'non utilisé'),
        ('Paire de langues', 'évaluée par un essai réel' if quality.get('language_pair_evaluated')
         else 'non évaluée : relecture complète recommandée'),
        ('Rapport établi le', date.today().strftime('%d/%m/%Y')),
    ])

    issues = quality.get('issues', [])
    alerts = [issue for issue in issues if issue['category'] != 'ambiguity']
    doubts = [issue for issue in issues if issue['category'] == 'ambiguity']
    semantic_issues = semantic['issues'] if semantic else []
    serious = sum(issue['severity'] in ('critical', 'major') for issue in semantic_issues)
    document.add_heading('Synthèse', level=1)
    lines = [
        f'Analyse du sens par IA : {VERDICTS[semantic["assessment"]] if semantic else "non réalisée."}',
        f'Problèmes de sens suspectés : {len(semantic_issues)}, dont {serious} critique(s) ou majeur(s).' if semantic else None,
        f'Alertes des contrôles automatiques (nombres, références, termes, négations…) : {len(alerts)}.',
        f'Formulations ambiguës dans l’original : {len(doubts)}.' if quality.get('ambiguity') else None,
        f"Passages corrigés par un relecteur : {len(quality['corrections']['passages'])}." if quality.get('corrections') else None,
        f"Passages repris de la mémoire de traduction : {len(quality['memory']['reused_passages'])}."
        if quality.get('memory') else None,
    ]
    for line in filter(None, lines):
        document.add_paragraph(line, style='List Bullet')
    _note(document, 'Ce rapport aide à cibler la relecture. Il ne valide pas la traduction : seule une personne '
                    'bilingue et compétente sur le sujet peut le faire.')

    document.add_heading('1. Analyse du sens par IA', level=1)
    if not semantic:
        document.add_paragraph('Non réalisée pour ce document.')
    else:
        document.add_paragraph(VERDICTS[semantic['assessment']])
        document.add_paragraph(semantic['summary'])
        if semantic_issues:
            _table(document, ['N°', 'Gravité', 'Original', 'Traduction', 'Explication'], [
                (number, SEVERITIES[issue['severity']], issue['source_quote'] or '(aucun passage correspondant)',
                 issue['translation_quote'] or '(passage potentiellement omis)', issue['explanation'])
                for number, issue in enumerate(semantic_issues, 1)])
        if semantic.get('discarded_issues'):
            _note(document, f"{semantic['discarded_issues']} signalement(s) écarté(s) : citation introuvable dans les textes.")
        _note(document, f"Analyse réalisée par {semantic.get('model')} en {semantic.get('parts', 1)} partie(s). "
                        'Avis indicatif : l’IA peut manquer des erreurs ou signaler à tort une formulation correcte.')

    document.add_heading('2. Alertes des contrôles automatiques', level=1)
    if quality.get('status') == 'unavailable':
        document.add_paragraph(quality['limitations'])
    elif not alerts:
        document.add_paragraph('Aucune alerte. Le sens reste à vérifier.')
    else:
        rows = []
        for issue in alerts:
            if issue['category'] == 'passage':
                original, translation = _passage(passages, issue['passage'])
                rows.append((issue['passage'], original or issue['excerpt'], translation, passage_detail(issue)))
            else:
                rows.append(('Document', '', '', readable_alerts({'issues': [issue]})[0]))
        _table(document, ['Passage', 'Original', 'Traduction', 'Problème signalé'], rows)
        _note(document, 'Indices par mots-clés et par comparaison de valeurs : une formulation correcte peut être '
                        'signalée, une erreur subtile peut passer sans alerte.')

    if doubts:
        document.add_heading('3. Formulations ambiguës dans l’original', level=1)
        _table(document, ['Passage', 'Formulation', 'Lectures possibles'],
               [(doubt['passage'], doubt['quote'], doubt['note']) for doubt in doubts])
        _note(document, 'La traduction a retenu la lecture la plus probable : à confirmer avec l’auteur du document.')

    document.add_heading('Ce qui n’est pas contrôlé', level=1)
    for line in [quality.get('limitations'), *quality.get('untranslated_parts', [])]:
        if line:
            document.add_paragraph(line, style='List Bullet')

    document.add_heading('Relecture humaine', level=1)
    _table(document, ['Rubrique', 'À compléter par le relecteur'],
           [('Relu par', ''), ('Date', ''), ('Décision', '☐ Traduction validée     ☐ À corriger'), ('Remarques', '\n\n')])
    footer = document.sections[0].footer.paragraphs[0]
    footer.text = ' · '.join(filter(None, [
        f"Consignes {quality['translation_prompt_version']}" if quality.get('translation_prompt_version') else None,
        f"glossaire {glossary['sha256'][:12]}" if glossary else None, 'brouillon à relire']))
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()

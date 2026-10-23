"""Produire le bilan d'évaluation de la qualité (français → anglais) au format Word.

Les chiffres viennent de l'essai réel du 22 octobre 2026
(evaluation/RESULTATS_2026-10-22.md). Après la relecture humaine, mettre à jour
les constantes ci-dessous puis relancer :

    python -B -m evaluation.bilan_qualite --output docs/Bilan_evaluation_qualite_FR-EN.docx
"""
import argparse
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ACCENT = RGBColor(0x17, 0x6B, 0x79)  # Couleur principale de l'application.
GREY = RGBColor(0x59, 0x59, 0x59)

RESULTS = [
    ('Erreurs graves de sens', 'gpt-4.1-mini : aucune. DeepL : 2 (« intervention » → presentation, '
     '« consignation » → entry).'),
    ('Interdiction affaiblie', 'gpt-4.1-mini : 1 (« ne doit être réalisée » → should). Corrigé avec le glossaire '
     'et les consignes actuelles (must / may).'),
    ('Codes, liens, montants, dates', 'Corrects pour les trois moteurs (30 cas).'),
    ('Instruction cachée dans le texte', 'Jamais suivie : traduite comme une citation.'),
    ('Mise en forme Word conservée', 'gpt-4.1-mini : 36 paragraphes sur 36. gpt-5.4-mini : 23 sur 36.'),
]
CONTROLS = [
    ('Contrôles par passage (négation, obligation, valeurs)', 'L’affaiblissement de C25.',
     'Les erreurs de vocabulaire.', 'Après correction des règles : 0 fausse alerte sur 90 traductions ; '
     '1 cas connu subsiste (« unconfirmed »).'),
    ('Contrôle des termes (glossaire, par passage)', 'Les 4 erreurs de vocabulaire de DeepL (C05, C10, C12, C15).',
     'Les erreurs de sens sans terme du glossaire.', 'Sans appel IA. Quelques alertes discutables (« fiche » → report).'),
    ('Analyse du sens par IA', 'C05, C10, C12 à chaque essai.', 'C15 (« contrôle » → test).',
     'Avis variable d’un essai à l’autre ; jusqu’à 7 signalements discutables.'),
    ('Repérage des ambiguïtés de l’original', '4 ambiguïtés de test sur 4 ; « consignation » toujours signalée.',
     'Peut manquer une ambiguïté levée par le métier.', 'Aucun faux doute sur les phrases claires de test ; '
     'signalements parfois pointilleux sur le corpus.'),
]
EXAMPLES = [
    ('C12 · terme de sécurité', 'La consignation doit être confirmée par le responsable habilité.',
     'The entry must be confirmed by the authorised manager. (DeepL)',
     'Contrôle des termes et analyse du sens : « consignation » attendu « lockout ».'),
    ('C25 · interdiction', 'Aucune intervention ne doit être réalisée sans consignation préalable.',
     'No intervention should be carried out without prior lockout. (gpt-4.1-mini)',
     'Contrôle par passage : obligation absente de la traduction.'),
    ('C15 · terme imprécis', "Si le témoin reste allumé, suspendre l'essai. Sinon, poursuivre le contrôle.",
     'Otherwise, continue with the test. (DeepL)',
     'Seul le contrôle des termes le repère ; l’analyse du sens par IA l’a manqué.'),
]
DECISIONS = [
    'Garder gpt-4.1-mini par défaut : il conserve la mise en forme Word, contrairement à gpt-5.4-mini.',
    'Ajouter au glossaire 5 notions issues des erreurs observées (consignation, intervention, contrôle, '
    'condamné, fiche).',
    'Confier le repérage des ambiguïtés à une analyse séparée (gpt-5.4) : demandé pendant la traduction, il '
    'ratait la moitié des cas.',
    'Concentrer l’évaluation sur le français → anglais ; espagnol et allemand restent disponibles, signalés '
    'comme non évalués.',
]
LIMITS = [
    '30 phrases fictives et une seule paire de langues : pas encore de documents réels.',
    'Constats issus d’une pré-relecture assistée par IA : la relecture humaine bilingue est en cours.',
    'Les modèles varient d’un essai à l’autre : un résultat isolé ne vaut pas garantie.',
    'Le glossaire n’est pas encore validé par le métier.',
    'Aucun taux de fiabilité universel n’est revendiqué : les chiffres valent pour ce corpus.',
]
NEXT_STEPS = [
    'Relecture humaine des 30 cas dans la page « Relecture des essais » ; le bilan croisant décisions et alertes '
    'se calcule automatiquement.',
    'Validation métier du glossaire dans la page « Validation du glossaire ».',
    'Essai sur des documents réels anonymisés (PDF et Word), avec la même méthode.',
]


def shade(cell, color):
    properties = cell._tc.get_or_add_tcPr()
    fill = OxmlElement('w:shd')
    fill.set(qn('w:val'), 'clear')
    fill.set(qn('w:color'), 'auto')
    fill.set(qn('w:fill'), color)
    properties.append(fill)


def table(document, headers, rows, widths):
    grid = document.add_table(rows=1, cols=len(headers))
    grid.style = 'Table Grid'
    grid.alignment = WD_TABLE_ALIGNMENT.CENTER
    for cell, header in zip(grid.rows[0].cells, headers, strict=True):
        cell.text = ''
        run = cell.paragraphs[0].add_run(header)
        run.bold, run.font.color.rgb = True, RGBColor(0xFF, 0xFF, 0xFF)
        shade(cell, '176B79')
    for row in rows:
        for cell, value in zip(grid.add_row().cells, row, strict=True):
            cell.text = value
    for row in grid.rows:
        for cell, width in zip(row.cells, widths, strict=True):
            cell.width = Cm(width)
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(2)
                for run in paragraph.runs:
                    run.font.size = Pt(9)
    document.add_paragraph()


def heading(document, text):
    paragraph = document.add_heading(text, level=1)
    for run in paragraph.runs:
        run.font.color.rgb = ACCENT


def bullets(document, items):
    for item in items:
        document.add_paragraph(item, style='List Bullet')


def build(output):
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin = section.right_margin = Cm(2)
    section.top_margin = section.bottom_margin = Cm(1.8)
    normal = document.styles['Normal']
    normal.font.name, normal.font.size = 'Calibri', Pt(10.5)
    normal.paragraph_format.space_after = Pt(4)

    title = document.add_heading('Bilan d’évaluation de la qualité de la traduction', level=0)
    for run in title.runs:
        run.font.color.rgb = ACCENT
    subtitle = document.add_paragraph()
    run = subtitle.add_run(f'Français → anglais britannique · essai réel du 22 octobre 2026 · '
                           f'version du {date.today().strftime("%d/%m/%Y")}')
    run.font.color.rgb, run.italic = GREY, True

    heading(document, 'En bref')
    bullets(document, [
        'Sur 30 phrases conçues pour piéger un traducteur, la configuration retenue (gpt-4.1-mini, consignes et '
        'glossaire) n’a commis aucune erreur grave de sens ; DeepL en a commis deux, sur des termes métier.',
        'Aucun contrôle ne suffit seul. Combinés, ils ont repéré les erreurs graves identifiées à la relecture ; '
        'seule une phrase source ambiguë (C26) a été mal tranchée par un modèle ; seul le repérage des '
        'ambiguïtés l’a signalée, et pas à chaque essai.',
        'Ces constats viennent d’une pré-relecture assistée par IA : la relecture humaine bilingue est en cours.',
    ])

    heading(document, '1. Question et périmètre')
    document.add_paragraph('La plateforme produit-elle des traductions fidèles au sens, et ses contrôles repèrent-ils '
                           'les erreurs qui comptent dans un document technique : négations, obligations, valeurs, '
                           'références et termes métier ?')
    document.add_paragraph('Périmètre : français → anglais britannique uniquement. L’espagnol et l’allemand sont '
                           'disponibles dans l’application mais n’ont pas été évalués.')

    heading(document, '2. Méthode')
    bullets(document, [
        'Corpus de 30 phrases fictives de maintenance ferroviaire ; chaque phrase cible un risque précis '
        '(négation liée à une condition, permission ou obligation, montants, codes, terme à double sens, '
        'instruction cachée…).',
        'Trois moteurs comparés : gpt-4.1-mini (configuration par défaut), gpt-5.4-mini et DeepL.',
        'Mesures complémentaires : un document Word piégeux traduit 6 fois par modèle (mise en forme), '
        '6 phrases ambiguës (repérage des doutes), essais avec glossaire et fiche de contexte.',
        'Coût de l’ensemble des essais : quelques centimes d’euro.',
    ])

    heading(document, '3. Résultats')
    table(document, ['Mesure', 'Résultat'], RESULTS, [5, 12])

    heading(document, '4. Ce que chaque contrôle détecte… et rate')
    table(document, ['Contrôle', 'A repéré', 'A raté', 'Fausses alertes'], CONTROLS, [4, 4.3, 3.7, 5])

    heading(document, '5. Exemples')
    table(document, ['Cas', 'Original', 'Traduction', 'Repéré par'], EXAMPLES, [2.6, 5, 5, 4.4])

    heading(document, '6. Décisions prises après l’essai')
    bullets(document, DECISIONS)

    heading(document, '7. Limites')
    bullets(document, LIMITS)

    heading(document, '8. Prochaines étapes')
    bullets(document, NEXT_STEPS)

    note = document.add_paragraph()
    run = note.add_run('Données détaillées : evaluation/RESULTATS_2026-10-22.md, docs/ambiguity-and-brief.md, '
                       'docs/word-translation.md. Les traductions de l’essai restent sur le poste de travail.')
    run.italic, run.font.color.rgb, run.font.size = True, GREY, Pt(9)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    document.save(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, default=Path('docs/Bilan_evaluation_qualite_FR-EN.docx'))
    build(parser.parse_args().output)


if __name__ == '__main__':
    main()

"""Extraire les paragraphes d'un PDF sans les couper aux sauts de page.

La mise en page d'un PDF mélange le texte courant, les en-têtes, pieds de page,
numéros de page et césures de fin de ligne. Traduits tels quels, ces morceaux
séparent une phrase de sa condition. Ces règles sont des heuristiques prudentes :
dans le doute, le texte est conservé plutôt que supprimé.
"""
from collections import Counter
from io import BytesIO
import re

from pypdf import PdfReader

PAGE_NUMBER = re.compile(r'(?:page|seite|página|pagina)?\s*\d{1,4}(?:\s*(?:/|sur|of|von|de)\s*\d{1,4})?', re.IGNORECASE)
SENTENCE_END = '.!?:;…»"”)]'
# Une ligne terminée par « mot- » suivie d'une minuscule : césure ou mot composé.
HYPHEN = re.compile(r'(\w+)-[ \t]*\n\s*([a-zà-ÿß]\w*)')
EDGE = 2  # Lignes de début et fin de page examinées comme en-têtes ou pieds.


def _shape(paragraph, number):
    """« Page 1/3 » (page 1) et « Page 2/3 » (page 2) : même pied de page.

    Seul le numéro de la page courante est neutralisé : « Porte 3 » et « Porte 4 »
    restent deux textes différents et ne sont jamais pris pour un en-tête.
    """
    return re.sub(rf'(?<!\d){number}(?!\d)', '#', paragraph.casefold(), count=1)


def _join_hyphenated(text, vocabulary):
    """« mainte-\\nnance » devient « maintenance » si ce mot existe ailleurs, sinon « porte-fenêtre »."""
    def replace(match):
        joined = match.group(1) + match.group(2)
        return joined if joined.casefold() in vocabulary else f'{match.group(1)}-{match.group(2)}'
    return HYPHEN.sub(replace, text)


def _paragraphs(text, vocabulary):
    return [re.sub(r'\s+', ' ', _join_hyphenated(paragraph, vocabulary)).strip()
            for paragraph in re.split(r'\n[ \t]*\n', text) if paragraph.strip()]


def pdf_paragraphs(data):
    """Paragraphes dans l'ordre de lecture, une seule fois chacun.

    - Un numéro de page seul en première ou dernière ligne est retiré.
    - Un en-tête ou pied répété sur plusieurs pages est gardé à sa première place.
    - Un paragraphe interrompu par un saut de page est recollé à sa suite.
    """
    pages = [page.extract_text(extraction_mode='layout') or '' for page in PdfReader(BytesIO(data)).pages]
    vocabulary = {word.casefold() for word in re.findall(r'\w+', '\n'.join(pages))}
    pages = [_paragraphs(text, vocabulary) for text in pages]
    repeated = Counter(_shape(paragraph, number) for number, page in enumerate(pages, 1)
                       for paragraph in set(page[:EDGE] + page[-EDGE:]))
    # Un en-tête ou pied figure sur au moins la moitié des pages.
    threshold = max(2, (len(pages) + 1) // 2)
    seen, result = set(), []
    for number, page in enumerate(pages, 1):
        kept = []
        for position, paragraph in enumerate(page):
            edge = position < EDGE or position >= len(page) - EDGE
            # Un nombre seul n'est un numéro de page qu'en toute première ou dernière ligne.
            if position in (0, len(page) - 1) and PAGE_NUMBER.fullmatch(paragraph):
                continue
            shape = _shape(paragraph, number)
            if edge and repeated[shape] >= threshold:
                if shape in seen:
                    continue
                seen.add(shape)
            kept.append(paragraph)
        if result and kept and result[-1][-1] not in SENTENCE_END and kept[0][0].islower():
            # Suite de phrase sur la page suivante (la césure éventuelle est déjà traitée).
            separator = '' if result[-1].endswith('-') and (result[-1][:-1].split()[-1] + kept[0].split()[0]).casefold() in vocabulary else ' '
            last = result.pop()
            kept[0] = (last[:-1] if separator == '' else last) + separator + kept[0]
        result.extend(kept)
    return result

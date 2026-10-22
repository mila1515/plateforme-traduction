"""Protéger ce qui ne doit jamais être traduit : codes, références, liens, e-mails.

Chaque élément est remplacé par un jeton ⟦n⟧ avant l'envoi, puis restauré tel
quel. Les nombres, dates et unités ne sont pas protégés : leur format doit
pouvoir s'adapter à la langue (« 1 500,50 » → « 1,500.50 »).
"""
import re

PROTECTED = re.compile('|'.join([
    r'https?://[^\s<>"«»]*[^\s<>"«».,;:!?)\]]',     # URL, sans la ponctuation finale
    r'\bwww\.[^\s<>"«»]*[^\s<>"«».,;:!?)\]]',
    r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+',                 # e-mail
    r'\b(?=[A-Z0-9-]*\d)(?=[A-Z0-9-]*[A-Z])[A-Z0-9]+(?:-[A-Z0-9]+)+\b',  # RN-204, PX-45B, XYZ-2024-001
    r'\b[A-Z]{2,}\d[A-Z0-9]*\b',                     # RN204, ISO9001
]))
TOKEN = re.compile(r'⟦(\d+)⟧')


def protect(texts):
    """Remplacer dans chaque texte ; un jeton par occurrence, numéroté sur tout le lot."""
    protected, mappings, counter = [], [], 0
    for text in texts:
        mapping, parts, position = {}, [], 0
        for match in PROTECTED.finditer(text):
            counter += 1
            token = f'⟦{counter}⟧'
            mapping[token] = match.group(0)
            parts += [text[position:match.start()], token]
            position = match.end()
        protected.append(''.join(parts) + text[position:])
        mappings.append(mapping)
    return protected, mappings


def restore(text, mapping):
    """Rendre le texte d'origine des jetons, ou None si un jeton est perdu, dupliqué ou inventé."""
    found = TOKEN.findall(text)
    if sorted(found) != sorted(token[1:-1] for token in mapping):
        return None
    return TOKEN.sub(lambda match: mapping[match.group(0)], text)

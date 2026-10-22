"""Modifier le texte d'un DOCX sans reconstruire ses tableaux ou ses images.

Le DOCX est une archive OOXML. Seules les parties texte du corps, des en-têtes,
pieds de page et notes sont modifiées ; les autres fichiers sont recopiés à l'identique.
Les champs automatiques et commentaires restent intacts et sont signalés. Les styles de segments sont conservés,
mais leur association aux mots traduits reste approximative.
"""
from io import BytesIO
import re
from zipfile import ZipFile, BadZipFile

from lxml import etree


W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
SPACE = '{http://www.w3.org/XML/1998/namespace}space'
PART = re.compile(r'word/(?:document|header\d*|footer\d*|footnotes|endnotes)\.xml$')


def word_boundary(text, position, start):
    """Déplacer une coupure en plein mot vers l'espace le plus proche après ``start``.

    Sans espace disponible (mot unique, langue sans espaces), la position reste.
    """
    position = min(max(position, start), len(text))
    if position in (start, len(text)) or text[position - 1].isspace() or text[position].isspace():
        return position
    left = next((index for index in range(position - 1, start, -1) if text[index - 1].isspace()), None)
    right = next((index for index in range(position + 1, len(text)) if text[index - 1].isspace()), None)
    candidates = [index for index in (left, right) if index is not None]
    return min(candidates, key=lambda index: abs(index - position)) if candidates else position


class WordDocument:
    """Conserver une archive et les groupes de nœuds textuels à traduire."""

    def __init__(self, data):
        self.data = data
        self.parts = {}
        self.groups = []
        self.field_texts = 0  # Textes affichés par un champ (lien, sommaire…), non traduits.
        self.comment_texts = 0
        try:
            self._load()
        except (BadZipFile, etree.XMLSyntaxError, KeyError, RuntimeError, EOFError, OSError) as exc:
            raise ValueError('Document Word illisible ou endommagé. Essayez de le réenregistrer dans Word.') from exc

    def _load(self):
        """Lire le contenu sans laisser remonter les erreurs techniques du ZIP/XML."""
        with ZipFile(BytesIO(self.data)) as archive:
            if 'word/document.xml' not in archive.namelist():
                raise ValueError('Document Word invalide : contenu principal absent.')
            for name in archive.namelist():
                if not PART.fullmatch(name):
                    continue
                parser = etree.XMLParser(resolve_entities=False, no_network=True)
                root = etree.fromstring(archive.read(name), parser)
                if name == 'word/document.xml' and (root.tag != W + 'document' or root.find(W + 'body') is None):
                    raise ValueError('Document Word invalide : structure du contenu principal incorrecte.')
                self.parts[name] = root
                field_depth = 0  # Un champ complexe peut traverser plusieurs paragraphes.
                # Chaque paragraphe appartient une seule fois à l'arbre XML,
                # y compris dans une cellule fusionnée ou un tableau imbriqué.
                for paragraph in root.iter(W + 'p'):
                    group = []
                    for node in paragraph.iter():
                        # Un paragraphe de zone de texte peut être imbriqué.
                        owner = next(node.iterancestors(W + 'p'), None)
                        if owner is not paragraph:
                            continue
                        if node.tag == W + 'fldChar':
                            kind = node.get(W + 'fldCharType')
                            field_depth += (kind == 'begin') - (kind == 'end')
                            field_depth = max(0, field_depth)
                        ancestors = {parent.tag for parent in node.iterancestors()}
                        in_field = field_depth or W + 'fldSimple' in ancestors
                        if node.tag == W + 't' and not in_field and W + 'del' not in ancestors:
                            group.append(node)
                        elif node.tag == W + 't' and in_field and W + 'del' not in ancestors:
                            self.field_texts += bool((node.text or '').strip())
                        elif node.tag in (W + 'tab', W + 'br', W + 'cr', W + 'drawing', W + 'fldChar'):
                            self._collect(group)
                            group = []
                    self._collect(group)
            if 'word/comments.xml' in archive.namelist():
                comments = etree.fromstring(archive.read('word/comments.xml'),
                                            etree.XMLParser(resolve_entities=False, no_network=True))
                self.comment_texts = sum(bool((node.text or '').strip()) for node in comments.iter(W + 't'))

    @property
    def untranslated(self):
        """Expliquer ce qui reste volontairement dans la langue source."""
        notices = []
        if self.field_texts:
            notices.append('Word : le texte affiché par des champs automatiques (sommaire, liens, renvois, '
                           'numéros) n’est pas traduit. Mettez à jour les champs dans Word et vérifiez-les.')
        if self.comment_texts:
            notices.append('Word : les commentaires de relecture ne sont pas traduits.')
        return notices

    def _collect(self, nodes):
        if ''.join(node.text or '' for node in nodes).strip():
            self.groups.append(nodes)

    @property
    def blocks(self):
        """Ordre commun à l'extraction, aux appels et à la réinsertion."""
        return [''.join(node.text or '' for node in nodes) for nodes in self.groups]

    def render(self, translations):
        """Répartir le nouveau texte dans les nœuds existants sans supprimer le XML.

        Les limites de styles sont réparties proportionnellement puis calées sur
        l'espace le plus proche, pour ne pas couper un mot entre deux styles.
        Ce n'est pas un alignement linguistique : un mot en gras peut changer.
        Les tabulations, sauts, liens, dessins et propriétés des cellules restent.
        """
        if len(translations) != len(self.groups):
            raise ValueError('Word : nombre de passages traduits incorrect.')
        for nodes, translation in zip(self.groups, translations, strict=True):
            lengths = [len(node.text or '') for node in nodes]
            total, used, start = sum(lengths), 0, 0
            for node, length in zip(nodes, lengths, strict=True):
                used += length
                end = word_boundary(translation, round(len(translation) * used / total), start)
                node.text = translation[start:end]
                node.set(SPACE, 'preserve')
                start = end
        output = BytesIO()
        with ZipFile(BytesIO(self.data)) as source, ZipFile(output, 'w') as target:
            for item in source.infolist():
                payload = (etree.tostring(self.parts[item.filename], xml_declaration=True, encoding='UTF-8', standalone=True)
                           if item.filename in self.parts else source.read(item.filename))
                target.writestr(item, payload)
        return output.getvalue()

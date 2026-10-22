"""Modifier le texte d'un DOCX sans reconstruire ses tableaux ou ses images.

Le DOCX est une archive OOXML. Seules les parties texte du corps, des en-têtes,
pieds de page et notes sont modifiées ; les autres fichiers sont recopiés à l'identique.

Chaque paragraphe est traduit en entier. Les passages dont la mise en forme
diffère du reste (gras, lien…) sont balisés ``⟪1⟫…⟪/1⟫`` ; tabulations, sauts,
images et champs sont des marqueurs ``⟪2/⟫``. Le modèle garde les balises autour
des mots traduits, ce qui replace la mise en forme sur les bons mots. Le texte
affiché des liens hypertextes est traduit ; les autres champs automatiques et
les commentaires restent intacts et sont signalés.
"""
from io import BytesIO
import re
from zipfile import ZipFile, BadZipFile

from lxml import etree


W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
SPACE = '{http://www.w3.org/XML/1998/namespace}space'
PART = re.compile(r'word/(?:document|header\d*|footer\d*|footnotes|endnotes)\.xml$')
TAG = re.compile(r'⟪(/?)(\d+)(/?)⟫')
MARKERS = {W + 'tab': '\t', W + 'br': '\n', W + 'cr': '\n', W + 'drawing': ''}
INVISIBLE = {W + 'lang', W + 'noProof', W + 'webHidden'}


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


def strip_tags(text):
    """Texte lisible pour les contrôles : un marqueur devient une espace, une balise disparaît."""
    return TAG.sub(lambda match: ' ' if match.group(3) else '', text)


def _style_key(node, link):
    """Deux textes de même mise en forme et du même lien forment un seul passage.

    Les propriétés invisibles (langue de correction, « pas de vérification »,
    indice de police) varient souvent d'un mot à l'autre : elles ne créent pas
    de balise inutile.
    """
    run = node.getparent()
    properties = run.find(W + 'rPr') if run is not None else None
    if properties is None:
        return (b'', link)
    properties = etree.fromstring(etree.tostring(properties))
    for child in list(properties):
        if child.tag in INVISIBLE:
            properties.remove(child)
    for fonts in properties.iter(W + 'rFonts'):
        fonts.attrib.pop(W + 'hint', None)
    return (etree.tostring(properties, method='c14n'), link)


def _is_hyperlink(field):
    return field['instr'].strip().upper().startswith('HYPERLINK')


class WordDocument:
    """Conserver une archive et, par paragraphe, ses passages et marqueurs."""

    def __init__(self, data):
        self.data = data
        self.parts = {}
        self.units = []  # Un paragraphe : liste de {'kind': 'text'|'marker', ...}
        self.field_texts = 0  # Texte affiché par un champ autre qu'un lien, non traduit.
        self.comment_texts = 0
        self.approximate = 0  # Paragraphes dont les balises n'ont pas été rendues correctement.
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
                fields = []  # Champs complexes ouverts ; un champ peut traverser plusieurs paragraphes.
                # Chaque paragraphe appartient une seule fois à l'arbre XML,
                # y compris dans une cellule fusionnée ou un tableau imbriqué.
                for paragraph in root.iter(W + 'p'):
                    self._collect(self._items(paragraph, fields))
            if 'word/comments.xml' in archive.namelist():
                comments = etree.fromstring(archive.read('word/comments.xml'),
                                            etree.XMLParser(resolve_entities=False, no_network=True))
                self.comment_texts = sum(bool((node.text or '').strip()) for node in comments.iter(W + 't'))

    def _items(self, paragraph, fields):
        """Textes (avec leur clé de style) et marqueurs du paragraphe, dans l'ordre."""
        items = []
        for node in paragraph.iter():
            # Un paragraphe de zone de texte peut être imbriqué : il est traité à part.
            if next(node.iterancestors(W + 'p'), None) is not paragraph:
                continue
            ancestors = list(node.iterancestors())
            if any(parent.tag == W + 'del' for parent in ancestors):
                continue
            if node.tag == W + 'fldChar':
                kind = node.get(W + 'fldCharType')
                if kind == 'begin':
                    fields.append({'instr': '', 'separated': False})
                elif kind == 'separate' and fields:
                    fields[-1]['separated'] = True
                    if len(fields) == 1 and not _is_hyperlink(fields[0]):
                        items.append({'kind': 'marker', 'plain': ''})  # Résultat du champ, intact.
                elif kind == 'end' and fields:
                    fields.pop()
            elif node.tag == W + 'instrText' and fields:
                fields[-1]['instr'] += node.text or ''
            elif node.tag == W + 'fldSimple':
                items.append({'kind': 'marker', 'plain': ''})
            elif node.tag == W + 't':
                simple = any(parent.tag == W + 'fldSimple' for parent in ancestors)
                link_field = len(fields) == 1 and fields[0]['separated'] and _is_hyperlink(fields[0])
                if simple or (fields and not link_field):
                    self.field_texts += bool((node.text or '').strip())
                    continue
                hyperlink = next(node.iterancestors(W + 'hyperlink'), None)
                link = id(fields[0]) if link_field else (id(hyperlink) if hyperlink is not None else None)
                items.append({'kind': 'text', 'node': node, 'key': _style_key(node, link)})
            elif node.tag in MARKERS and not fields:
                items.append({'kind': 'marker', 'plain': MARKERS[node.tag]})
        return items

    def _collect(self, items):
        """Regrouper les textes consécutifs de même style ; baliser ce qui diffère du style dominant."""
        unit = []
        for item in items:
            if item['kind'] == 'text' and unit and unit[-1]['kind'] == 'text' and unit[-1]['key'] == item['key']:
                unit[-1]['nodes'].append(item['node'])
            elif item['kind'] == 'text':
                unit.append({'kind': 'text', 'key': item['key'], 'nodes': [item['node']]})
            else:
                unit.append(dict(item))
        texts = [entry for entry in unit if entry['kind'] == 'text']
        if not ''.join(node.text or '' for entry in texts for node in entry['nodes']).strip():
            return
        sizes = {}
        for entry in texts:
            sizes[entry['key']] = sizes.get(entry['key'], 0) + sum(len(node.text or '') for node in entry['nodes'])
        dominant = max(sizes, key=sizes.get)
        number = 0
        for entry in unit:
            entry['tag'] = None
            if entry['kind'] == 'marker' or entry['key'] != dominant:
                number += 1
                entry['tag'] = number
        self.units.append(unit)

    @property
    def blocks(self):
        """Texte lisible de chaque paragraphe, pour l'extraction, la comparaison et les contrôles."""
        return [''.join(entry['plain'] if entry['kind'] == 'marker' else ''.join(node.text or '' for node in entry['nodes'])
                        for entry in unit) for unit in self.units]

    @property
    def tagged(self):
        """Texte envoyé au moteur, avec balises de mise en forme et marqueurs."""
        result = []
        for unit in self.units:
            parts = []
            for entry in unit:
                if entry['kind'] == 'marker':
                    parts.append(f"⟪{entry['tag']}/⟫")
                else:
                    text = ''.join(node.text or '' for node in entry['nodes'])
                    parts.append(f"⟪{entry['tag']}⟫{text}⟪/{entry['tag']}⟫" if entry['tag'] else text)
            result.append(''.join(parts))
        return result

    def render(self, translations):
        """Replacer chaque paragraphe traduit dans ses nœuds, sans supprimer le XML.

        Balises rendues à l'identique et dans le même ordre : chaque passage
        retrouve sa mise en forme. Sinon, le paragraphe reste traduit en entier et
        le texte est réparti proportionnellement (mise en forme approximative).
        Les tabulations, sauts, liens, dessins et propriétés des cellules restent.
        """
        if len(translations) != len(self.units):
            raise ValueError('Word : nombre de passages traduits incorrect.')
        for unit, translation in zip(self.units, translations, strict=True):
            if not self._apply_tags(unit, translation):
                self.approximate += 1
                self._spread(unit, TAG.sub('', translation))
        output = BytesIO()
        with ZipFile(BytesIO(self.data)) as source, ZipFile(output, 'w') as target:
            for item in source.infolist():
                payload = (etree.tostring(self.parts[item.filename], xml_declaration=True, encoding='UTF-8', standalone=True)
                           if item.filename in self.parts else source.read(item.filename))
                target.writestr(item, payload)
        return output.getvalue()

    @staticmethod
    def _apply_tags(unit, translation):
        # Emplacements entre balises : un passage source, ou rien (texte ajouté par la traduction).
        expected, slots = [], [None]
        for entry in unit:
            if entry['kind'] == 'marker':
                expected.append(('marker', entry['tag']))
                slots.append(None)
            elif entry['tag'] is None:
                slots[-1] = slots[-1] or entry
            else:
                expected += [('open', entry['tag']), ('close', entry['tag'])]
                slots += [entry, None]
        events, pieces, position = [], [], 0
        for match in TAG.finditer(translation):
            pieces.append(translation[position:match.start()])
            events.append(('close' if match.group(1) else 'marker' if match.group(3) else 'open', int(match.group(2))))
            position = match.end()
        pieces.append(translation[position:])
        if events != expected:
            return False
        # Une espace collée à un saut de ligne ou une tabulation (« restart⏎ without ») est invisible et parasite.
        plains = iter(entry['plain'] for entry in unit if entry['kind'] == 'marker')
        for index, (kind, _) in enumerate(events):
            if kind == 'marker' and next(plains) in ('\n', '\t'):
                pieces[index], pieces[index + 1] = pieces[index].rstrip(' '), pieces[index + 1].lstrip(' ')
        texts = {id(entry): '' for entry in unit if entry['kind'] == 'text'}
        for index, piece in enumerate(pieces):
            # Texte sans passage source : rattaché au passage précédent, sinon au suivant.
            owner = slots[index] or next((slot for slot in reversed(slots[:index]) if slot), None) \
                or next((slot for slot in slots[index + 1:] if slot), None)
            texts[id(owner)] += piece
        for entry in unit:
            if entry['kind'] == 'text':
                for position, node in enumerate(entry['nodes']):
                    node.text = texts[id(entry)] if position == 0 else ''
                    node.set(SPACE, 'preserve')
        return True

    @staticmethod
    def _spread(unit, translation):
        """Repli : répartir proportionnellement, coupures calées sur les espaces."""
        nodes = [node for entry in unit if entry['kind'] == 'text' for node in entry['nodes']]
        lengths = [len(node.text or '') for node in nodes]
        total, used, start = sum(lengths), 0, 0
        for node, length in zip(nodes, lengths, strict=True):
            used += length
            end = word_boundary(translation, round(len(translation) * used / total), start)
            node.text = translation[start:end]
            node.set(SPACE, 'preserve')
            start = end

    @property
    def untranslated(self):
        """Expliquer ce qui reste volontairement dans la langue source."""
        notices = []
        if self.field_texts:
            notices.append('Word : le texte affiché par des champs automatiques (sommaire, renvois, '
                           'numéros) n’est pas traduit. Mettez à jour les champs dans Word et vérifiez-les.')
        if self.comment_texts:
            notices.append('Word : les commentaires de relecture ne sont pas traduits.')
        return notices

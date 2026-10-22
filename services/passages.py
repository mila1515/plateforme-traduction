"""Contrôles locaux passage par passage, quand l'alignement source/traduction est connu.

Avec GPT, chaque passage traduit correspond exactement à un passage source :
une alerte peut donc désigner l'endroit précis à relire. Ce sont des indices
lexicaux, sans analyse grammaticale : une paraphrase correcte peut être
signalée (« sans » → « no »), et un contresens subtil peut passer inaperçu.
"""
import re

from services.quality import check_translation

# Marqueurs de négation et d'obligation. Présence/absence uniquement, sans compter :
# une langue peut exprimer la même négation avec un ou deux mots (ne… pas / not).
NEGATION = {
    'FR': r"\bne\b|\bn'|\bpas\b|\bjamais\b|\baucun|\bsans\b|\binterdi|\bnul(?:le)?\b|\bni\b|\bnon\b",
    'EN': r"\bnot\b|n't\b|\bno\b(?!\.\s*\d)|\bnever\b|\bwithout\b|\bnone\b|\bnor\b|\bprohibit|\bforbid|\bnon\b",
    'DE': r"\bnicht\b|\bkein|\bnie\b|\bniemals\b|\bohne\b|\bverboten|\bweder\b|\bnichts\b",
    'ES': r"\bno\b|\bnunca\b|\bsin\b|\bningun|\bningún|\bjamás\b|\bprohibid|\bni\b|\bnada\b",
}
# Une interdiction est une obligation négative : « ne doit pas » = « darf nicht » = « prohibited ».
OBLIGATION = {
    'FR': r"\bdoi[st]\b|\bdoivent\b|\bdevr[ao]|\bobligatoire|\bimpérati|\bil faut\b|\b(?:est|sont) tenue?s?\b|\binterdi",
    'EN': r"\bmust\b|\bshall\b|\brequired?\b|\bmandatory\b|\bha(?:s|ve) to\b|\bneeds? to\b|\bobliged\b|\bprohibit|\bforbid"
          r"|\b(?:is|are) to be\b",
    'DE': r"\bmuss|\bmüss|\bsoll|\bverpflicht|\berforderlich|\b(?:ist|sind) zu\b|\bzwingend|\bverboten"
          r"|\bd(?:arf|ürfen)\b[^.;]*\bnicht\b",
    'ES': r"\bdebe|\bdeber|\bobligatori|\btienen? que\b|\bhay que\b|\bes necesario\b|\bimprescindible|\bprohibid",
}
MIN_LENGTH = 40  # En dessous, le rapport de longueur n'est pas significatif.
SHORT, LONG = 0.5, 2.0


# « ne … que » signifie « seulement » : ce « ne » n'est pas une négation, sauf si
# un vrai mot négatif (pas, jamais, plus…) apparaît avant le « que ».
RESTRICTIVE = re.compile(r"\bn(?:e\b|')(?=(?:(?!\b(?:pas|jamais|plus|rien|personne|aucun\w*|nul\w*|guère|point|ni)\b)[^.;!?])*?\bque\b)")


def _normalize(text):
    return ' '.join(text.casefold().replace('’', "'").split())


def _has(patterns, language, text):
    language = language.split('-')[0]
    text = _normalize(text)
    if patterns is NEGATION and language == 'FR':
        text = RESTRICTIVE.sub('', text)
    return re.search(patterns[language], text) is not None


def check_passages(passages, source_language, target_language):
    """Alertes localisées : nombres, références, non-traduction, longueur, négation, obligation."""
    issues = []
    for number, (source, translation) in enumerate(passages, 1):
        found = []
        for issue in check_translation(source, translation)['issues']:
            found.append({'check': issue['category'], 'missing': issue['missing'], 'added': issue['added']})
        if _normalize(source) == _normalize(translation) and len(re.findall(r'[^\W\d_]{2,}', source)) >= 3:
            found.append({'check': 'untranslated'})
        if len(source.strip()) >= MIN_LENGTH:
            ratio = len(translation.strip()) / len(source.strip())
            if ratio < SHORT or ratio > LONG:
                found.append({'check': 'length', 'direction': 'shorter' if ratio < SHORT else 'longer',
                              'ratio': round(ratio, 2)})
        for check, patterns in (('negation', NEGATION), ('obligation', OBLIGATION)):
            before, after = _has(patterns, source_language, source), _has(patterns, target_language, translation)
            if before != after:
                found.append({'check': check, 'direction': 'missing' if before else 'added'})
        # Un extrait court localise le passage sans copier le document dans le rapport.
        excerpt = ' '.join(source.split())[:80]
        issues.extend({'category': 'passage', 'passage': number, 'excerpt': excerpt, **item} for item in found)
    return issues

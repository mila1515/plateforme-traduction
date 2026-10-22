"""Conservative, local checks: alerts are not a linguistic certification."""
from collections import Counter
import re
from services.glossary import terminology_issues


# Groupes de milliers (« 1 500 », « 1,500 », « 1.500.000 ») avant les nombres simples.
NUMBER = re.compile(r'(?<![\d.,])\d{1,3}(?:[   .,]\d{3}(?!\d))+(?:[.,]\d+)?|\d+(?:[.,]\d+)?')
REFERENCE = re.compile(r'\b[A-Z]{2,8}[- ]\d+(?:[- ]\d+)*\b')


def normalize_number(value):
    """Ramener « 1 500,50 », « 1,500.50 » et « 1.500,50 » à « 1500.50 ».

    Avec deux séparateurs différents, le dernier est décimal. Un séparateur
    unique suivi de trois chiffres est lu comme milliers (« 1,500 » = 1500),
    sauf après 0 (« 0,125 »). « 12,500 » au sens de 12,5 reste donc signalé.
    """
    value = re.sub(r'[   ]', '', value)
    separators = [char for char in value if char in '.,']
    if not separators:
        return value
    *groups, decimals = re.split(r'[.,]', value)
    if len(set(separators)) == 1 and len(decimals) == 3 and (len(separators) > 1 or groups[0].strip('0')):
        return ''.join(groups) + decimals
    return ''.join(groups) + '.' + decimals


def check_translation(source, translation, glossary_pairs=None):
    """Compare occurrences, allowing number formats and reference spacing.

    Dates, written-out numbers and unit conversions can produce legitimate
    differences. No automatic approval or rejection follows.
    """
    issues = []
    checks = (
        ('numbers', NUMBER, normalize_number),
        ('references', REFERENCE, lambda value: re.sub(r'[- ]+', '-', value)),
    )
    for category, pattern, normalize in checks:
        before = Counter(normalize(value) for value in pattern.findall(source))
        after = Counter(normalize(value) for value in pattern.findall(translation))
        missing, added = before - after, after - before
        if missing or added:
            issues.append({'category': category,
                           'missing': dict(missing), 'added': dict(added)})
    checked = ['numbers', 'references']
    if glossary_pairs is not None:
        checked.append('terminology')
        issues.extend(terminology_issues(source, translation, glossary_pairs))
    return {
        'status': 'review_required',
        'checks': checked,
        'issues': issues,
        'limitations': 'Contrôles indicatifs : sens, négations et unités non validés. '
                       'Le contrôle terminologique, si activé, vérifie la présence des termes, pas leur bon emploi. '
                       'Les changements de format peuvent produire des alertes. Relecture humaine nécessaire.',
    }

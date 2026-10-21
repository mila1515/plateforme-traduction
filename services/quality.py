"""Conservative, local checks: alerts are not a linguistic certification."""
from collections import Counter
import re
from services.glossary import terminology_issues


NUMBER = re.compile(r'\d+(?:[.,]\d+)?')
REFERENCE = re.compile(r'\b[A-Z]{2,8}[- ]\d+(?:[- ]\d+)*\b')


def check_translation(source, translation, glossary_pairs=None):
    """Compare occurrences, allowing decimal commas and reference spacing.

    Dates, thousands separators, written-out numbers and unit conversions can
    produce legitimate differences. No automatic approval or rejection follows.
    """
    issues = []
    checks = (
        ('numbers', NUMBER, lambda value: value.replace(',', '.')),
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

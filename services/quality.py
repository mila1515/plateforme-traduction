"""Conservative, local checks: alerts are not a linguistic certification."""
from collections import Counter
import re


NUMBER = re.compile(r'\d+(?:[.,]\d+)?')
REFERENCE = re.compile(r'\b[A-Z]{2,8}[- ]\d+(?:[- ]\d+)*\b')


def check_translation(source, translation):
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
    return {
        'status': 'review_required',
        'checks': ['numbers', 'references'],
        'issues': issues,
        'limitations': 'Contrôles indicatifs : sens, négations, unités et terminologie non validés. '
                       'Les changements de format peuvent produire des alertes. Relecture humaine nécessaire.',
    }

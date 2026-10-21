from services.quality import check_translation


def test_numbers_changed_missing_added_and_repeated():
    report = check_translation('RN 204 : 3 portes, 3 contrôles à 08:10.',
                               'RN 204: 4 doors, 3 checks at 08:20.')
    numbers = next(issue for issue in report['issues'] if issue['category'] == 'numbers')
    assert numbers['missing'] == {'3': 1, '10': 1}
    assert numbers['added'] == {'4': 1, '20': 1}


def test_decimal_separator_and_reference_spacing_allowed():
    report = check_translation('RN 204 : 12,5 mm.', 'RN-204: 12.5 mm.')
    assert report['issues'] == []
    assert report['status'] == 'review_required'


def test_reference_changed_even_when_numbers_unchanged():
    report = check_translation('RN 204', 'ST 204')
    assert report['issues'] == [{'category': 'references', 'missing': {'RN-204': 1}, 'added': {'ST-204': 1}}]


def test_semantic_error_is_not_certified_by_numeric_checks():
    report = check_translation('Ne pas ouvrir la porte 3.', 'Open door 3.')
    assert report['issues'] == []
    assert report['status'] == 'review_required'

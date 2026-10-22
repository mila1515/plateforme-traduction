import pytest

from services.quality import check_translation, normalize_number


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


@pytest.mark.parametrize('source,translation', [
    ('Montant 1 500,50 EUR', 'Amount 1,500.50 EUR'),
    ('Montant 1 500,50 EUR', 'Betrag 1.500,50 EUR'),
    ('3 000 pièces, 2 500 000 m', '3,000 parts, 2,500,000 m'),
    ('Dose 0,125 mg', 'Dose 0.125 mg'),
])
def test_thousands_and_decimal_formats_are_not_reported(source, translation):
    assert check_translation(source, translation)['issues'] == []


def test_changed_amount_is_still_reported_across_formats():
    report = check_translation('Montant 1 500,50 EUR', 'Amount 1,050.50 EUR')
    assert report['issues'] == [{'category': 'numbers', 'missing': {'1500.50': 1}, 'added': {'1050.50': 1}}]


def test_year_followed_by_number_is_not_merged():
    report = check_translation('En 2024, 125 véhicules', 'In 2024, 125 vehicles')
    assert report['issues'] == []
    assert normalize_number('2024') == '2024'


def test_reference_changed_even_when_numbers_unchanged():
    report = check_translation('RN 204', 'ST 204')
    assert report['issues'] == [{'category': 'references', 'missing': {'RN-204': 1}, 'added': {'ST-204': 1}}]


def test_semantic_error_is_not_certified_by_numeric_checks():
    report = check_translation('Ne pas ouvrir la porte 3.', 'Open door 3.')
    assert report['issues'] == []
    assert report['status'] == 'review_required'

"""Tag cleaning.

Calibre splits subjects on commas at every entry point, so a tag containing one
cannot be stored. Rather than lose the information, name headings are rewritten
into a form that says the same thing without a comma.
"""

import pytest

from ebook_metamend.tags import clean, reformat_name_heading


class TestReformatNameHeading:
    @pytest.mark.parametrize(
        ('heading', 'expected'),
        [
            ('Angelou, Maya, 1928-2014', 'Maya Angelou'),
            ('Dalio, Ray, 1949-', 'Ray Dalio'),
            ('Machiavelli, Niccolo, 1469-1527', 'Niccolo Machiavelli'),
            ('Frankl, Viktor E. (Viktor Emil), 1905-1997', 'Viktor E. Frankl'),
        ],
    )
    def test_a_person_as_subject_becomes_a_plain_name(self, heading, expected):
        assert reformat_name_heading(heading) == expected

    @pytest.mark.parametrize(
        'tag',
        [
            'Fiction, general',
            'Business & Economics, Entrepreneurship',
            'Psychology',
            'Self-Help',
            'Political Science, General',
            'Mill, John Stuart',
            '',
        ],
    )
    def test_ordinary_subjects_are_left_alone(self, tag):
        """These have the same shape as a name heading but are not one, or lack
        the life dates that make it unambiguous. Turning 'Political Science,
        General' into 'General Political Science' would be worse than splitting,
        so the rule requires the MARC date signal before it rewrites anything."""
        assert reformat_name_heading(tag) == tag

    def test_the_result_contains_no_comma(self):
        """The whole point: a comma cannot survive being written."""
        assert ',' not in reformat_name_heading('Angelou, Maya, 1928-2014')


class TestClean:
    def test_noise_is_dropped(self):
        assert clean(['Mobilism', 'Psychology', 'New York Times bestseller']) == ['Psychology']

    def test_noise_matching_ignores_case(self):
        assert clean(['MOBILISM', 'mobilism']) == []

    def test_orphaned_life_dates_are_dropped(self):
        """Left behind by an earlier comma split, and meaningless alone."""
        assert clean(['1928-2014', '1949-', 'Psychology']) == ['Psychology']

    def test_a_bare_year_that_is_not_a_range_is_kept(self):
        """'1984' is a legitimate tag, and an earlier cleanup deleted it."""
        assert clean(['1984']) == ['1984']

    def test_duplicates_collapse_case_insensitively(self):
        assert clean(['Psychology', 'psychology', 'PSYCHOLOGY']) == ['Psychology']

    def test_order_is_preserved(self):
        assert clean(['Zebra', 'Apple', 'Moose']) == ['Zebra', 'Apple', 'Moose']

    def test_whitespace_is_normalised(self):
        assert clean(['  Self   Help  ']) == ['Self Help']

    def test_empty_and_blank_tags_disappear(self):
        assert clean(['', '   ', 'Psychology']) == ['Psychology']

    def test_a_name_heading_and_its_fragments_collapse_to_one_name(self):
        """The realistic input after a previous run shredded the heading."""
        assert clean(['Angelou, Maya, 1928-2014', '1928-2014']) == ['Maya Angelou']

    def test_nothing_in_means_nothing_out(self):
        assert clean([]) == []

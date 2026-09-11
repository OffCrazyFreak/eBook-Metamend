"""Tag cleaning.

The writers store a comma, but a Calibre library splits every subject on commas
when it reads the file, so a tag containing one does not survive its next stop.
Rather than lose the information, a name heading naming the book's own author is
rewritten into a form that says the same thing without a comma. Every other
heading is left to split, because splitting is harmless and rewriting is not.
"""

import pytest

from ebook_metamend.tags import clean, reformat_name_heading


class TestReformatNameHeading:
    @pytest.mark.parametrize(
        ('heading', 'author', 'expected'),
        [
            ('Angelou, Maya, 1928-2014', 'Maya Angelou', 'Maya Angelou'),
            ('Dalio, Ray, 1949-', 'Ray Dalio', 'Ray Dalio'),
            ('Machiavelli, Niccolo, 1469-1527', 'Niccolo Machiavelli', 'Niccolo Machiavelli'),
            # The catalogue form carries initials and an expansion the filename
            # does not, so the author match has to be fuzzy.
            ('Frankl, Viktor E. (Viktor Emil), 1905-1997', 'Viktor Frankl', 'Viktor E. Frankl'),
        ],
    )
    def test_the_books_own_author_as_subject_becomes_a_plain_name(self, heading, author, expected):
        assert reformat_name_heading(heading, author) == expected

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
        the life dates that make it unambiguous."""
        assert reformat_name_heading(tag, 'Some Author') == tag

    @pytest.mark.parametrize(
        ('heading', 'author'),
        [
            # MARC period subdivisions. Identical shape to a personal name with
            # life dates, and this used to rewrite them into nonsense:
            # "History United States" was written to real files.
            ('United States, History, 1861-1865', 'James McPherson'),
            ('Europe, History, 1900-1945', 'Tony Judt'),
            ('Holocaust, Jewish (1939-1945)', 'Viktor Frankl'),
            ('Concentration camps, Poland (Oswiecim)', 'Viktor Frankl'),
            ('Psychology, Movements (Existential)', 'Viktor Frankl'),
            ('Science, Life Sciences (Biology)', 'Richard Dawkins'),
            # A different person is still a person, but not this book's, and we
            # cannot tell a biography's subject from a place, so leave it.
            ('Churchill, Winston, 1874-1965', 'Andrew Roberts'),
        ],
    )
    def test_a_heading_that_is_not_this_books_author_is_left_alone(self, heading, author):
        assert reformat_name_heading(heading, author) == heading

    def test_no_author_means_no_rewriting(self):
        assert clean(['Angelou, Maya, 1928-2014']) == ['Angelou, Maya, 1928-2014']

    def test_the_result_contains_no_comma(self):
        """The whole point: a comma cannot survive being written."""
        assert ',' not in reformat_name_heading('Angelou, Maya, 1928-2014', 'Maya Angelou')


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
        got = clean(['Angelou, Maya, 1928-2014', '1928-2014'], 'Maya Angelou')
        assert got == ['Maya Angelou']

    def test_a_period_subdivision_survives_cleaning_unmangled(self):
        got = clean(['United States, History, 1861-1865'], 'James McPherson')
        assert got == ['United States, History, 1861-1865']

    def test_nothing_in_means_nothing_out(self):
        assert clean([]) == []

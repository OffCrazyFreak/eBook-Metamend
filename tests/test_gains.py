"""The gain rules: what gets written, and what must never be.

The tool writes to files that are usually irreplaceable, so the rule that matters
is that a field is only ever added or improved, never emptied.
"""

import pytest

from ebook_metamend.enrich import (
    MAX_MERGED_TAGS,
    TITLE_IMPROVEMENT_MARGIN,
    build_write_args,
    compute_gains,
    merge,
)


def answer(**overrides):
    """A source answer with every key the pipeline expects."""
    base = {
        'title': '',
        'authors': [],
        'publisher': '',
        'description': '',
        'tags': [],
        'series': None,
        'sidx': None,
        'isbn': '',
    }
    base.update(overrides)
    return base


class TestMerge:
    def test_longest_title_wins(self):
        merged = merge(
            {'a': answer(title='Atomic Habits'), 'b': answer(title='Atomic Habits: An Easy Way')}
        )
        assert merged['title'] == 'Atomic Habits: An Easy Way'

    def test_tags_are_the_union_across_sources(self):
        merged = merge(
            {'a': answer(tags=['Self-Help']), 'b': answer(tags=['Psychology', 'Self-Help'])}
        )
        assert set(merged['tags']) == {'Psychology', 'Self-Help'}

    def test_tags_two_sources_agreed_on_come_first(self):
        merged = merge({'a': answer(tags=['Only Mine', 'Shared']), 'b': answer(tags=['Shared'])})
        assert merged['tags'][0] == 'Shared'

    def test_truncation_keeps_agreed_tags_over_alphabetical_ones(self):
        """Sorting then truncating took an alphabetical head, so call numbers
        like '323.44' and 'Jc585 .m6 1999' were written as subjects while the
        real headings were cut."""
        noise = [f'{n}00.1' for n in range(1, 20)]
        merged = merge(
            {
                'a': answer(tags=[*noise, 'Political Science']),
                'b': answer(tags=['Political Science']),
            }
        )
        assert merged['tags'][0] == 'Political Science'

    def test_tags_are_capped(self):
        many = [f'tag{i:02d}' for i in range(40)]
        assert len(merge({'a': answer(tags=many)})['tags']) == MAX_MERGED_TAGS

    def test_first_non_empty_wins_for_identifiers(self):
        merged = merge({'a': answer(isbn=''), 'b': answer(isbn='9780735211292')})
        assert merged['isbn'] == '9780735211292'

    def test_no_answers_yields_empty_record(self):
        merged = merge({})
        assert merged['title'] == '' and merged['tags'] == [] and merged['series'] is None


class TestComputeGains:
    def test_missing_fields_are_gained(self):
        merged = merge({'a': answer(tags=['Psychology'], publisher='Avery', isbn='123')})
        gains = compute_gains(merged, current={}, conf='HIGH')
        assert set(gains) >= {'tags', 'publisher', 'isbn'}

    @pytest.mark.parametrize('field_name', ['tags', 'publisher', 'isbn', 'series'])
    def test_existing_values_are_never_overwritten(self, field_name):
        merged = merge(
            {'a': answer(tags=['New'], publisher='New', isbn='new', series='New', sidx='1')}
        )
        current = {
            'tags': ['Existing'],
            'publisher': 'Existing',
            'isbn': 'existing',
            'series': 'Existing',
        }
        assert field_name not in compute_gains(merged, current, conf='HIGH')

    def test_nothing_is_gained_when_the_book_is_already_complete(self):
        merged = merge(
            {'a': answer(tags=['Psychology'], publisher='Avery', isbn='123', description='x')}
        )
        current = {
            'tags': ['Psychology'],
            'publisher': 'Avery',
            'isbn': '123',
            'description': 'xxxx',
        }
        assert compute_gains(merged, current, conf='HIGH') == {}

    def test_a_longer_description_is_an_improvement(self):
        merged = merge({'a': answer(description='a much longer description')})
        assert 'description' in compute_gains(merged, {'description': 'short'}, conf='HIGH')

    def test_a_shorter_description_is_not(self):
        merged = merge({'a': answer(description='short')})
        assert 'description' not in compute_gains(
            merged, {'description': 'a much longer description'}, conf='HIGH'
        )

    def test_title_is_only_gained_at_high_confidence(self):
        merged = merge({'a': answer(title='Atomic Habits: An Easy and Proven Way')})
        current = {'title': 'Atomic Habits'}
        assert 'title' in compute_gains(merged, current, conf='HIGH')
        for conf in ('MED', 'LOW'):
            assert 'title' not in compute_gains(merged, current, conf=conf)

    def test_title_must_beat_the_existing_one_by_the_margin(self):
        current = {'title': 'Atomic Habits'}
        barely = 'Atomic Habits' + 'x' * TITLE_IMPROVEMENT_MARGIN
        assert 'title' not in compute_gains(merge({'a': answer(title=barely)}), current, 'HIGH')
        assert 'title' in compute_gains(merge({'a': answer(title=barely + 'x')}), current, 'HIGH')

    def test_empty_merge_gains_nothing(self):
        assert compute_gains(merge({}), {}, conf='HIGH') == {}


class TestBuildWriteArgs:
    def test_no_gains_produces_no_arguments(self):
        assert build_write_args({}, merge({})) == []

    def test_series_index_rides_along_with_the_series(self):
        merged = merge({'a': answer(series='Example Saga', sidx='2')})
        args = build_write_args({'series': 'Example Saga'}, merged)
        assert args == ['-s', 'Example Saga', '-i', '2']

    def test_series_without_an_index_omits_it(self):
        merged = merge({'a': answer(series='Example Saga')})
        assert build_write_args({'series': 'Example Saga'}, merged) == ['-s', 'Example Saga']

    def test_every_gain_reaches_the_argument_list(self):
        gains = {
            'title': 'T',
            'tags': ['a', 'b'],
            'description': 'D',
            'publisher': 'P',
            'isbn': 'I',
        }
        args = build_write_args(gains, merge({}))
        # Paired, not merely present. Checking only that each flag appears would
        # pass with two values swapped, which is how a description reaches -t.
        pairs = dict(zip(args[::2], args[1::2], strict=True))
        assert pairs == {
            '-t': 'T',
            '--tags': 'a,b',
            '-c': 'D',
            '--publisher': 'P',
            '--isbn': 'I',
        }


class TestUnreadableMetadata:
    """A book whose existing metadata cannot be read must be left alone.

    Treating a failed read as an empty book makes every field look missing, so
    --apply would overwrite a title, publisher and tags that were there all
    along. This is the one failure mode that silently destroys data.
    """

    def test_no_gains_are_computed_for_an_unreadable_book(self, monkeypatch):
        from ebook_metamend import calibre, enrich
        from ebook_metamend.library import Book

        monkeypatch.setattr(calibre, 'read_book_metadata', lambda *a, **k: None)
        monkeypatch.setattr(
            enrich,
            'query_sources',
            lambda *a, **k: {
                'google': answer(
                    title='Atomic Habits',
                    authors=['James Clear'],
                    tags=['Self-Help'],
                    publisher='Avery',
                    isbn='123',
                )
            },
        )
        book = Book(stem='James Clear - Atomic Habits', formats={'.epub': '/nowhere.epub'})

        proposal = enrich.propose(book)

        assert proposal is not None
        assert proposal.unreadable is True
        assert proposal.gains == {}, 'must propose nothing when the book cannot be read'

    def test_a_readable_empty_book_still_gains(self, monkeypatch):
        """The contrast case: genuinely empty metadata is a normal thing to fill."""
        from ebook_metamend import calibre, enrich
        from ebook_metamend.library import Book

        monkeypatch.setattr(calibre, 'read_book_metadata', lambda *a, **k: {})
        monkeypatch.setattr(
            enrich,
            'query_sources',
            lambda *a, **k: {
                'google': answer(
                    title='Atomic Habits',
                    authors=['James Clear'],
                    tags=['Self-Help'],
                    publisher='Avery',
                )
            },
        )
        book = Book(stem='James Clear - Atomic Habits', formats={'.epub': '/nowhere.epub'})

        proposal = enrich.propose(book)

        assert proposal.unreadable is False
        assert 'tags' in proposal.gains and 'publisher' in proposal.gains


class TestDerivedTitlesInMerge:
    """Longest-wins is right for subtitles and wrong for adaptations."""

    def test_a_genuine_title_beats_a_longer_adaptation(self):
        merged = merge(
            {
                'kobo': answer(title='On Liberty'),
                'google': answer(title='On Liberty (Squashed Edition)'),
            }
        )
        assert merged['title'] == 'On Liberty'

    def test_the_longest_genuine_title_still_wins(self):
        merged = merge(
            {
                'kobo': answer(title='Bad Blood'),
                'google': answer(title='Bad Blood: Secrets and Lies'),
            }
        )
        assert merged['title'] == 'Bad Blood: Secrets and Lies'

    def test_an_adaptation_is_used_only_when_it_is_all_there_is(self):
        merged = merge({'google': answer(title='Atomic Habits (Tamil)')})
        assert merged['title'] == 'Atomic Habits (Tamil)'


class TestFieldsComeFromTheSourcesThatEarnedConfidence:
    """Confidence and content used to be decided separately: two strong sources
    earned HIGH, then the longest title among everything above the floor was
    written, which could be a third answer for a different book.
    """

    def _scores(self, *rows):
        from ebook_metamend.matching import SourceScore

        return [
            SourceScore(name=n, title=t, title_score=ts, author_score=aus) for n, t, ts, aus in rows
        ]

    def test_a_third_weaker_answer_cannot_supply_the_title(self):
        """Verified case: two sources return the real Sapiens, a third returns
        the graphic adaptation, which is longer and so used to win."""
        from ebook_metamend.enrich import trusted_names

        scores = self._scores(
            ('kobo', 'Sapiens: A Brief History of Humankind', 0.95, 1.0),
            ('google', 'Sapiens: A Brief History of Humankind', 0.95, 1.0),
            ('openlib', 'Sapiens: A Graphic History, Volume 1', 0.95, 0.2),
        )
        assert trusted_names(scores) == ['kobo', 'google']

    def test_an_omnibus_cannot_supply_fields_to_the_volume(self):
        from ebook_metamend.enrich import trusted_names

        scores = self._scores(
            ('kobo', 'The Happiest Toddler on the Block', 1.0, 1.0),
            ('google', 'The Happiest Toddler on the Block', 1.0, 1.0),
            ('openlib', 'The Happiest Baby and The Happiest Toddler', 0.69, 1.0),
        )
        assert 'openlib' not in trusted_names(scores)

    def test_a_recognised_adaptation_donates_nothing_at_all(self):
        """Not just the title. It used to supply the translation's ISBN,
        publisher and description into the English edition."""
        from ebook_metamend.enrich import trusted_names
        from ebook_metamend.matching import ADAPTATION_SCORE

        scores = self._scores(('google', 'Atomic Habits (Tamil)', ADAPTATION_SCORE, 1.0))
        assert trusted_names(scores) == [], 'a lone adaptation supplies nothing at all'

        with_real = self._scores(
            ('kobo', 'Atomic Habits', 1.0, 1.0),
            ('google', 'Atomic Habits (Tamil)', ADAPTATION_SCORE, 1.0),
        )
        assert trusted_names(with_real) == ['kobo']

    def test_weaker_sources_are_used_when_none_is_strong(self):
        from ebook_metamend.enrich import trusted_names

        scores = self._scores(('kobo', 'Something Close', 0.8, 0.3))
        assert trusted_names(scores) == ['kobo']

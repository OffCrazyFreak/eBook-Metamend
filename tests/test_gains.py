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
        assert merged['tags'] == ['Psychology', 'Self-Help']

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
        for flag in ('-t', '--tags', '-c', '--publisher', '--isbn'):
            assert flag in args

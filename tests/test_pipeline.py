"""The composition: classify -> trusted_names -> merge -> compute_gains -> run.

The pure functions were well covered and the wiring between them was not, which
is how a source that identified a different book kept its ability to write.
"""

import json

import pytest

from ebook_metamend import calibre, enrich
from ebook_metamend.library import Book
from ebook_metamend.matching import SourceScore
from ebook_metamend.sources import cache


def score(name, title, title_score, author_score):
    return SourceScore(name=name, title=title, title_score=title_score, author_score=author_score)


class TestOnlyTheSourcesThatAgreedMayContribute:
    def test_a_strong_source_naming_a_different_book_is_excluded(self):
        scores = [
            score('kobo', 'Sapiens: A Brief History of Humankind', 0.95, 1.0),
            score('google', 'Sapiens: A Brief History of Humankind', 0.95, 1.0),
            score('openlib', 'Something Else Entirely', 0.9, 0.9),
        ]
        assert enrich.trusted_names(scores) == ['kobo', 'google']

    def test_when_nobody_agrees_the_strong_sources_still_report(self):
        scores = [
            score('kobo', 'Some Book', 1.0, 1.0),
            score('google', 'A Different Book Entirely', 0.9, 0.9),
        ]
        assert sorted(enrich.trusted_names(scores)) == ['google', 'kobo']

    def test_an_answer_that_is_only_an_adaptation_contributes_nothing(self):
        scores = [score('google', 'On Liberty (Squashed Edition)', 0.55, 1.0)]
        assert enrich.trusted_names(scores) == []


class TestASequelCannotWinOnLength:
    """Reproduced live: Kobo and Google returned "Foundation", Open Library
    returned the sequel "Foundation and Empire" by the same author. A sequel is a
    legitimate prefix extension, so it scores 0.95 and genuinely agrees; it
    cannot be excluded by similarity. It used to supply the title, and because
    the other two had no ISBN, the sequel's ISBN too, at HIGH with no override."""

    ANSWERS = {
        'kobo': {'title': 'Foundation', 'isbn': '', 'publisher': 'Gnome Press'},
        'google': {'title': 'Foundation', 'isbn': '', 'publisher': ''},
        'openlib': {
            'title': 'Foundation and Empire',
            'isbn': '9780553293371',
            'publisher': 'Bantam',
        },
    }

    def test_the_title_the_most_sources_named_wins(self):
        assert enrich.merge(self.ANSWERS)['title'] == 'Foundation'

    def test_and_the_other_books_identifiers_come_nowhere_near(self):
        merged = enrich.merge(self.ANSWERS)
        assert merged['isbn'] == ''
        assert merged['publisher'] == 'Gnome Press'

    def test_a_real_subtitle_is_still_preferred_over_the_bare_title(self):
        """The case longest-wins existed for, and it has to keep working: one
        source describing the same book more fully, not a different book."""
        answers = {
            'kobo': {'title': 'Sapiens'},
            'google': {'title': 'Sapiens: A Brief History of Humankind'},
        }
        assert enrich.merge(answers)['title'] == 'Sapiens: A Brief History of Humankind'


class TestNothingSurvivesTheAdaptationFilter:
    def test_and_so_nothing_is_proposed_from_it(self):
        merged = enrich.merge({})
        assert enrich.compute_gains(merged, {}, 'LOW') == {}


class TestAnExistingDescriptionIsNotTradedForALongerOne:
    MERGED = {
        'title': '',
        'tags': [],
        'description': 'A much longer blurb belonging to some other edition.',
        'series': None,
        'sidx': None,
        'publisher': '',
        'isbn': '',
    }

    def test_an_empty_description_is_filled_at_any_confidence(self):
        gains = enrich.compute_gains(self.MERGED, {'description': ''}, 'LOW')
        assert gains['description'] == self.MERGED['description']

    def test_an_existing_one_is_not_replaced_below_high(self):
        """Longer is not better, and this is the only non-title path that can
        destroy content that was already there."""
        current = {'description': 'The real 1859 essay.'}
        assert enrich.compute_gains(self.MERGED, current, 'MED') == {}
        assert enrich.compute_gains(self.MERGED, current, 'LOW') == {}

    def test_and_is_replaced_at_high(self):
        current = {'description': 'The real 1859 essay.'}
        gains = enrich.compute_gains(self.MERGED, current, 'HIGH')
        assert gains['description'] == self.MERGED['description']


class TestNothingIsWrittenWithoutSomethingToScoreAgainst:
    def test_a_filename_with_no_author_separator_is_skipped(self, tmp_path):
        """ "Dune" parses as all author and no title, so every score would be 0.0
        against an empty string and any answer would look equally related."""
        book = tmp_path / 'Dune.epub'
        book.write_bytes(b'')
        assert enrich.propose(Book(stem='Dune', formats={'.epub': str(book)})) is None


class TestTheApplyGate:
    """Only HIGH is written unless the override is passed. This is the tool's
    headline promise and nothing pinned it."""

    @pytest.fixture
    def written(self, monkeypatch, tmp_path):
        calls = []
        monkeypatch.setattr(
            calibre, 'write_metadata', lambda path, args, **kw: (calls.append(args), (True, ''))[1]
        )
        return calls

    def _proposal(self, conf, tmp_path):
        book = tmp_path / 'x.epub'
        book.write_bytes(b'')
        return enrich.Proposal(
            stem='Someone - A Book',
            files={'.epub': str(book)},
            conf=conf,
            sources=['kobo', 'google'],
            gains={'publisher': 'Real Press'},
            merged={'sidx': None},
            fn_score=1.0,
            au_score=1.0,
            src_titles={},
        )

    @pytest.mark.parametrize('conf', ['MED', 'LOW'])
    def test_below_high_nothing_is_written_by_default(self, conf, written, tmp_path, monkeypatch):
        proposal = self._proposal(conf, tmp_path)
        monkeypatch.setattr(enrich, 'propose', lambda book: proposal)
        enrich.run([Book(stem='Someone - A Book')], do_apply=True)
        assert written == []

    def test_high_is_written(self, written, tmp_path, monkeypatch):
        proposal = self._proposal('HIGH', tmp_path)
        monkeypatch.setattr(enrich, 'propose', lambda book: proposal)
        enrich.run([Book(stem='Someone - A Book')], do_apply=True)
        assert written == [['--publisher', 'Real Press']]

    def test_med_is_written_only_with_the_override(self, written, tmp_path, monkeypatch):
        proposal = self._proposal('MED', tmp_path)
        monkeypatch.setattr(enrich, 'propose', lambda book: proposal)
        enrich.run([Book(stem='Someone - A Book')], do_apply=True, include_low=True)
        assert written == [['--publisher', 'Real Press']]

    def test_a_dry_run_writes_nothing_at_any_confidence(self, written, tmp_path, monkeypatch):
        proposal = self._proposal('HIGH', tmp_path)
        monkeypatch.setattr(enrich, 'propose', lambda book: proposal)
        enrich.run([Book(stem='Someone - A Book')], do_apply=False, include_low=True)
        assert written == []


class TestASourceThatKeepsFailingIsShelvedForTheRun:
    def test_it_stops_being_asked(self, monkeypatch):
        """Backing off suits a source having a bad minute. A source whose network
        path is broken charges the full timeout on every remaining book and never
        answers, which was the largest single cost in a run."""
        asked = []

        def always_fails(title, author):
            asked.append(title)
            raise enrich.SourceError('TLS handshake timed out')

        dead = enrich.SOURCES[0].__class__(name='dead', fetch=always_fails, pause=0)
        monkeypatch.setattr(enrich, 'SOURCES', (dead,))
        enrich.reset_run_state()
        for book in range(enrich.MAX_CONSECUTIVE_FAILURES + 4):
            enrich.query_sources(f'Book {book}', 'Someone', pause=False)

        assert len(asked) == enrich.MAX_CONSECUTIVE_FAILURES
        assert 'dead' in enrich.unavailable_sources
        enrich.reset_run_state()

    def test_an_answer_resets_the_count(self, monkeypatch):
        results = [None, enrich.SourceError('boom'), {'title': 'x'}, enrich.SourceError('boom')]

        def flaky(title, author):
            outcome = results.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        flapping = enrich.SOURCES[0].__class__(name='flapping', fetch=flaky, pause=0)
        monkeypatch.setattr(enrich, 'SOURCES', (flapping,))
        enrich.reset_run_state()
        for book in range(4):
            enrich.query_sources(f'Book {book}', 'Someone', pause=False)
        assert 'flapping' not in enrich.unavailable_sources
        enrich.reset_run_state()


class TestFixturesRecordWhatHappenedIncludingFailure:
    @pytest.fixture
    def fixtures(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache, 'FIXTURES', tmp_path)
        return tmp_path

    def test_an_answer_round_trips(self, fixtures, monkeypatch):
        monkeypatch.setattr(cache, 'MODE', 'record')
        wrapped = cache.wrap('kobo', lambda t, a: {'title': t})
        assert wrapped('Dune', 'Herbert') == {'title': 'Dune'}

        monkeypatch.setattr(cache, 'MODE', 'replay')
        replayed = cache.wrap('kobo', lambda t, a: pytest.fail('replay hit the network'))
        assert replayed('Dune', 'Herbert') == {'title': 'Dune'}

    def test_a_failure_replays_as_the_same_failure(self, fixtures, monkeypatch):
        """Recording only successes meant a run where a source was unreachable
        could not be replayed at all: the key was never written, so replay went
        back to the network for exactly the source that had just failed."""
        monkeypatch.setattr(cache, 'MODE', 'record')
        wrapped = cache.wrap(
            'openlib', lambda t, a: (_ for _ in ()).throw(enrich.SourceError('TLS timeout'))
        )
        with pytest.raises(enrich.SourceError):
            wrapped('Dune', 'Herbert')

        monkeypatch.setattr(cache, 'MODE', 'replay')
        replayed = cache.wrap('openlib', lambda t, a: pytest.fail('replay hit the network'))
        with pytest.raises(enrich.SourceError, match='TLS timeout'):
            replayed('Dune', 'Herbert')

    def test_an_unrecorded_key_is_loud_rather_than_silent(self, fixtures, monkeypatch):
        monkeypatch.setattr(cache, 'MODE', 'replay')
        replayed = cache.wrap('kobo', lambda t, a: {'title': t})
        with pytest.raises(cache.MissingFixture):
            replayed('Never Recorded', 'Nobody')

    def test_the_key_follows_the_query(self, fixtures):
        one = cache.fixture_path('kobo', 'Dune', 'Herbert')
        two = cache.fixture_path('kobo', 'Dune', 'Someone Else')
        assert one != two

    def test_the_record_is_readable_by_a_human(self, fixtures, monkeypatch):
        monkeypatch.setattr(cache, 'MODE', 'record')
        cache.wrap('kobo', lambda t, a: {'title': 'Dune'})('Dune', 'Herbert')
        saved = json.loads(cache.fixture_path('kobo', 'Dune', 'Herbert').read_text())
        assert saved['source'] == 'kobo'
        assert saved['title'] == 'Dune'
        assert saved['response'] == {'title': 'Dune'}


class TestAtLowNoSourceIdentifiedTheBook:
    """LOW means not one source cleared both the title and the author. Under
    --include-low it may still offer subjects, but not an identifier."""

    MERGED = {
        'title': 'Something',
        'tags': ['Fiction'],
        'description': 'A blurb.',
        'series': 'Some Saga',
        'sidx': '2',
        'publisher': 'A Publisher',
        'isbn': '9780000000001',
    }

    def test_identifiers_are_withheld(self):
        gains = enrich.compute_gains(self.MERGED, {}, 'LOW')
        assert 'isbn' not in gains
        assert 'publisher' not in gains
        assert 'series' not in gains

    def test_subjects_and_an_empty_description_still_come_through(self):
        gains = enrich.compute_gains(self.MERGED, {}, 'LOW')
        assert gains['tags'] == ['Fiction']
        assert gains['description'] == 'A blurb.'

    @pytest.mark.parametrize('conf', ['MED', 'HIGH'])
    def test_and_are_written_once_something_identified_it(self, conf):
        gains = enrich.compute_gains(self.MERGED, {}, conf)
        assert gains['isbn'] == '9780000000001'
        assert gains['publisher'] == 'A Publisher'
        assert gains['series'] == 'Some Saga'

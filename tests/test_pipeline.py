"""The composition: classify -> trusted_names -> merge -> compute_gains -> run.

The pure functions were well covered and the wiring between them was not, which
is how a source that identified a different book kept its ability to write.
"""

import json

import pytest

from ebook_metamend import enrich
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


class TestTheReportedFiguresDescribeTheTrustedSources:
    def test_an_excluded_answer_does_not_set_the_figures(self):
        scores = [
            score('kobo', 'Foundation', 0.9, 0.8),
            score('google', 'Foundation', 0.9, 0.8),
            score('openlib', 'Foundation and Empire', 0.95, 1.0),
        ]
        assert enrich.reported_scores(scores, ['kobo', 'google']) == (0.9, 0.8)

    def test_when_nothing_is_trusted_the_best_of_every_answer_is_kept(self):
        scores = [score('google', 'On Liberty (Squashed Edition)', 0.55, 1.0)]
        assert enrich.reported_scores(scores, []) == (0.55, 1.0)

    def test_a_verdict_earned_outside_the_trusted_set_keeps_its_figures(self):
        # The adaptation earns MED on its author and is barred from contributing;
        # the weak survivor alone would print MED beside an author score of 0.
        scores = [
            score('google', 'On Liberty (Squashed Edition)', 0.7, 1.0),
            score('openlib', 'Liberty', 0.6, 0.0),
        ]
        assert enrich.reported_scores(scores, ['openlib']) == (0.7, 1.0)

    def test_no_answers_at_all_read_as_zero(self):
        assert enrich.reported_scores([], []) == (0.0, 0.0)


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

    def test_the_answer_closest_to_the_filename_wins(self):
        merged = enrich.merge(self.ANSWERS, filename_title='Foundation')
        assert merged['title'] == 'Foundation'

    def test_and_the_other_books_identifiers_come_nowhere_near(self):
        merged = enrich.merge(self.ANSWERS, filename_title='Foundation')
        assert merged['isbn'] == ''
        assert merged['publisher'] == 'Gnome Press'


class TestALongerTitleIsNotABetterOne:
    """Found by replaying 50 books from the real library. Kobo answered
    "Essentialism"; Google answered with the separate companion planner. Both
    name the real author, both are strong, and the planner is a legitimate prefix
    of nothing but its own name, so the two agreed, reached HIGH, and the planner
    won on length. The filename is the ground truth everywhere else in this tool,
    so it decides here too."""

    def test_a_companion_volume_cannot_take_the_title(self):
        answers = {
            'kobo': {'title': 'Essentialism'},
            'google': {
                'title': (
                    'The Essentialism Planner: A 90-Day Guide to Accomplishing More by Doing Less'
                )
            },
        }
        merged = enrich.merge(answers, filename_title='Essentialism')
        assert merged['title'] == 'Essentialism'

    def test_nor_can_a_sequel(self):
        answers = {
            'kobo': {'title': 'Foundation'},
            'google': {'title': 'Foundation and Empire'},
        }
        assert enrich.merge(answers, filename_title='Foundation')['title'] == 'Foundation'

    @pytest.mark.parametrize(
        ('offered', 'expected'),
        [
            # A colon and a spaced dash both introduce a subtitle.
            ('Sapiens: A Brief History of Humankind', 'Sapiens: A Brief History of Humankind'),
            ('Sapiens - A Brief History of Humankind', 'Sapiens - A Brief History of Humankind'),
            # More title words are not a subtitle.
            ('Sapiens Illustrated Companion', 'Sapiens'),
            ('Sapiens and Homo Deus', 'Sapiens'),
        ],
    )
    def test_a_real_subtitle_is_still_added(self, offered, expected):
        answers = {'kobo': {'title': 'Sapiens'}, 'google': {'title': offered}}
        assert enrich.merge(answers, filename_title='Sapiens')['title'] == expected

    def test_an_article_is_not_an_improvement_worth_writing(self):
        """Google answered "The Meditations" for "Meditations". Both normalise
        the same, so the longer one used to win and propose writing "The"."""
        answers = {'kobo': {'title': 'Meditations'}, 'google': {'title': 'The Meditations'}}
        assert enrich.merge(answers, filename_title='Meditations')['title'] == 'Meditations'


class TestNothingSurvivesTheAdaptationFilter:
    def test_and_so_nothing_is_proposed_from_it(self):
        merged = enrich.merge({}, filename_title='Anything')
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
        monkeypatch.setitem(
            enrich.WRITERS,
            '.epub',
            lambda path, gains, merged: (calls.append(gains), (True, ''))[1],
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
        monkeypatch.setattr(enrich, 'propose', lambda book, **_: proposal)
        enrich.run([Book(stem='Someone - A Book')], do_apply=True)
        assert written == []

    def test_high_is_written(self, written, tmp_path, monkeypatch):
        proposal = self._proposal('HIGH', tmp_path)
        monkeypatch.setattr(enrich, 'propose', lambda book, **_: proposal)
        enrich.run([Book(stem='Someone - A Book')], do_apply=True)
        assert written == [{'publisher': 'Real Press'}]

    def test_med_is_written_only_with_the_override(self, written, tmp_path, monkeypatch):
        proposal = self._proposal('MED', tmp_path)
        monkeypatch.setattr(enrich, 'propose', lambda book, **_: proposal)
        enrich.run([Book(stem='Someone - A Book')], do_apply=True, include_low=True)
        assert written == [{'publisher': 'Real Press'}]

    def test_a_dry_run_writes_nothing_at_any_confidence(self, written, tmp_path, monkeypatch):
        proposal = self._proposal('HIGH', tmp_path)
        monkeypatch.setattr(enrich, 'propose', lambda book, **_: proposal)
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

    def test_record_mode_retries_a_stored_failure(self, fixtures, monkeypatch):
        """A failure is transient by definition, so freezing the first bad minute
        into the fixtures would make it permanent."""
        monkeypatch.setattr(cache, 'MODE', 'record')
        failing = cache.wrap(
            'openlib', lambda t, a: (_ for _ in ()).throw(enrich.SourceError('TLS timeout'))
        )
        with pytest.raises(enrich.SourceError):
            failing('Dune', 'Herbert')

        recovered = cache.wrap('openlib', lambda t, a: {'title': 'Dune'})
        assert recovered('Dune', 'Herbert') == {'title': 'Dune'}

        monkeypatch.setattr(cache, 'MODE', 'replay')
        replayed = cache.wrap('openlib', lambda t, a: pytest.fail('replay hit the network'))
        assert replayed('Dune', 'Herbert') == {'title': 'Dune'}

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

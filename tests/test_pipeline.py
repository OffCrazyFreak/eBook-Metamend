"""The composition: classify -> trusted_names -> merge -> compute_gains -> run.

The pure functions were well covered and the wiring between them was not, which
is how a source that identified a different book kept its ability to write.
"""

import json

import pytest

from ebook_metamend import calibre, enrich
from ebook_metamend.library import Book
from ebook_metamend.matching import CONTAINED_SCORE, SourceScore
from ebook_metamend.sources import cache, calibre_plugin, http


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
    def test_a_filename_with_no_title_is_skipped(self, tmp_path):
        """A bare ISBN names no title, so every score would be 0.0 against an
        empty string and any answer would look equally related."""
        book = tmp_path / '9780465050659.epub'
        book.write_bytes(b'')
        assert enrich.propose(Book(stem='9780465050659', formats={'.epub': str(book)})) is None

    def test_a_title_with_no_author_can_never_be_strong(self, tmp_path, monkeypatch):
        """ "Dune" is a title and nobody's name. A source naming the book exactly
        still has no author to be checked against, so it cannot vouch for the
        book on its own and the verdict stays LOW."""
        book = tmp_path / 'Dune.epub'
        book.write_bytes(b'')
        exact = enrich.SOURCES[0].__class__(
            name='exact',
            fetch=lambda t, a: {'title': 'Dune', 'authors': ['Frank Herbert']},
            pause=0,
        )
        monkeypatch.setattr(enrich, 'SOURCES', (exact,))
        monkeypatch.setattr(calibre, 'read_book_metadata', lambda path: {})
        enrich.reset_run_state()
        proposal = enrich.propose(Book(stem='Dune', formats={'.epub': str(book)}), pause=False)
        assert proposal is not None
        assert proposal.conf == 'LOW'
        assert proposal.au_score == 0.0
        enrich.reset_run_state()


class TestAShorterBookCannotBeWrittenOverALongerOne:
    """Two catalogues answering with the earlier volume of a series, whose title
    is the head of this one's, used to agree with each other and reach HIGH; the
    earlier volume's ISBN and series index were then proposed for this file."""

    def test_two_sources_naming_the_head_volume_stay_below_high(self, monkeypatch, tmp_path):
        head = {
            'title': 'The Quiet Orchard',
            'authors': ['Mara Voss'],
            'isbn': '9781594488849',
            'series': 'The Quiet Orchard',
            'sidx': '1',
        }
        one = enrich.SOURCES[0].__class__(name='one', fetch=lambda t, a: dict(head), pause=0)
        two = enrich.SOURCES[0].__class__(name='two', fetch=lambda t, a: dict(head), pause=0)
        monkeypatch.setattr(enrich, 'SOURCES', (one, two))
        monkeypatch.setattr(calibre, 'read_book_metadata', lambda path: {})
        enrich.reset_run_state()
        path = tmp_path / 'Mara Voss - The Quiet Orchard The Winter Pruning.epub'
        path.write_bytes(b'')
        proposal = enrich.propose(Book(stem=path.stem, formats={'.epub': str(path)}), pause=False)
        enrich.reset_run_state()
        assert proposal is not None
        # MED, not HIGH: the author still matches, so the answer keeps a say,
        # but the earlier volume's identifiers are behind the --include-low gate.
        assert proposal.conf == 'MED'
        assert proposal.fn_score == CONTAINED_SCORE

    def test_the_same_head_declared_as_the_main_title_is_the_book_itself(
        self, monkeypatch, tmp_path
    ):
        """ "Mara Voss - The Quiet Orchard - The Winter Pruning" declares "The Quiet
        Orchard" as the main title, so a catalogue answering exactly that is the
        book listed without its subtitle and HIGH is right."""
        answer = {'title': 'The Quiet Orchard', 'authors': ['Mara Voss']}
        one = enrich.SOURCES[0].__class__(name='one', fetch=lambda t, a: dict(answer), pause=0)
        two = enrich.SOURCES[0].__class__(name='two', fetch=lambda t, a: dict(answer), pause=0)
        monkeypatch.setattr(enrich, 'SOURCES', (one, two))
        monkeypatch.setattr(calibre, 'read_book_metadata', lambda path: {})
        enrich.reset_run_state()
        path = tmp_path / 'Mara Voss - The Quiet Orchard - The Winter Pruning.epub'
        path.write_bytes(b'')
        proposal = enrich.propose(Book(stem=path.stem, formats={'.epub': str(path)}), pause=False)
        enrich.reset_run_state()
        assert proposal is not None
        assert proposal.conf == 'HIGH'


class TestTheOtherReadingOfANameIsTriedWhenTheFirstFindsNothing:
    """Half the tools out there write the title first (Calibre, Anna's Archive,
    Z-Library), half the author first (this tool, Readarr, libgen). The
    catalogues settle it, not a guess."""

    @pytest.fixture
    def catalogue(self, monkeypatch, tmp_path):
        asked = []

        def fetch(title, author):
            asked.append((title, author))
            # The catalogue knows one book and answers only a query that names it.
            if title in ('The Quiet Orchard', 'Quiet Orchard') and author == 'Mara Voss':
                return {'title': title, 'authors': ['Mara Voss']}
            return None

        one = enrich.SOURCES[0].__class__(name='one', fetch=fetch, pause=0)
        two = enrich.SOURCES[0].__class__(name='two', fetch=fetch, pause=0)
        monkeypatch.setattr(enrich, 'SOURCES', (one, two))
        monkeypatch.setattr(calibre, 'read_book_metadata', lambda path: {})
        enrich.reset_run_state()
        yield asked
        enrich.reset_run_state()

    def _book(self, tmp_path, stem):
        path = tmp_path / f'{stem}.epub'
        path.write_bytes(b'')
        return Book(stem=stem, formats={'.epub': str(path)})

    def test_a_title_first_name_reaches_high_on_the_second_reading(self, catalogue, tmp_path):
        """ "Quiet Orchard - Mara Voss" reads author first by the tool's own
        convention; the catalogues know it the other way round."""
        proposal = enrich.propose(self._book(tmp_path, 'Quiet Orchard - Mara Voss'), pause=False)
        assert proposal is not None
        assert proposal.conf == 'HIGH'
        assert proposal.facts.author == 'Mara Voss'
        assert proposal.facts.title == 'Quiet Orchard'
        assert catalogue[:2] == [('Mara Voss', 'Quiet Orchard')] * 2

    def test_an_author_first_name_costs_one_round(self, catalogue, tmp_path):
        proposal = enrich.propose(
            self._book(tmp_path, 'Mara Voss - The Quiet Orchard'), pause=False
        )
        assert proposal is not None
        assert proposal.conf == 'HIGH'
        assert catalogue == [('The Quiet Orchard', 'Mara Voss')] * 2

    def test_the_second_reading_is_not_taken_when_it_finds_nothing_either(
        self, catalogue, tmp_path
    ):
        proposal = enrich.propose(self._book(tmp_path, 'Some Other Book - Ann Person'), pause=False)
        assert proposal is None
        # Both readings were tried, once per source.
        assert len(catalogue) == 4

    def test_a_half_that_cannot_be_a_person_is_never_asked_as_one(self, catalogue, tmp_path):
        """A subtitle or a product name makes no author, so the other reading is
        not worth a round of queries."""
        stem = 'Ann Person - Some Product Guide for Version 4 Cloud and Beyond'
        enrich.propose(self._book(tmp_path, stem), pause=False)
        assert len(catalogue) == 2

    def test_a_missing_recording_for_the_other_reading_is_skipped(self, monkeypatch, tmp_path):
        """A fixture set recorded before names had two readings has no key for
        the second one; the run reports it and carries on rather than aborting."""
        from ebook_metamend.sources import cache

        def strict(title, author):
            if title == 'The Quiet Orchard':
                return None
            raise cache.MissingFixture(f'{title!r} / {author!r}')

        one = enrich.SOURCES[0].__class__(name='one', fetch=strict, pause=0)
        monkeypatch.setattr(enrich, 'SOURCES', (one,))
        monkeypatch.setattr(calibre, 'read_book_metadata', lambda path: {})
        enrich.reset_run_state()
        assert (
            enrich.propose(self._book(tmp_path, 'Ann Person - The Quiet Orchard'), pause=False)
            is None
        )
        assert enrich.last_rounds == 2
        enrich.reset_run_state()

    def test_a_book_read_both_ways_reports_two_rounds(self, catalogue, tmp_path):
        """The page paces between books, not inside one, so it must know a book
        cost two rounds to keep a source under its rate."""
        enrich.propose(self._book(tmp_path, 'Some Other Book - Ann Person'), pause=False)
        assert enrich.last_rounds == 2
        enrich.propose(self._book(tmp_path, 'Mara Voss - The Quiet Orchard'), pause=False)
        assert enrich.last_rounds == 1

    def test_only_the_whole_title_is_ever_asked_for(self, catalogue, tmp_path):
        """A retry with the head of a glued title once drew a different volume out
        of the catalogues, a strict prefix that the prefix rule scores 0.95, and
        proposed its ISBN. The catalogues are asked about the whole title only."""
        enrich.propose(
            self._book(tmp_path, 'Ann Person - The Quiet Orchard The Year Of Pruning'), pause=False
        )
        assert {title for title, _ in catalogue} == {'The Quiet Orchard The Year Of Pruning'}

    def test_a_series_name_has_one_reading(self, catalogue, tmp_path):
        """ "Author - Series - 02 - Title" is this tool's own convention; the
        other way round fits nothing, so it is never asked."""
        enrich.propose(
            self._book(tmp_path, 'Ann Person - Hill Country - 02 - Some Book'), pause=False
        )
        assert catalogue == [('Some Book', 'Ann Person')] * 2


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


class TestTheRawBodyIsRecordedBesideTheParsedRecord:
    """A parsed record replays what an old parser made of the answer; the raw
    body lets the parser in the checked-out code run over what the catalogue
    actually sent."""

    @pytest.fixture
    def fixtures(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache, 'FIXTURES', tmp_path)
        return tmp_path

    def test_a_body_round_trips_through_the_transport(self, fixtures, monkeypatch):
        monkeypatch.setattr(cache, 'MODE', 'record')
        http.set_transport(lambda url, headers, timeout: b'{"docs": [1]}')
        try:
            assert http.get_json('https://example.test/search?q=dune') == {'docs': [1]}
            monkeypatch.setattr(cache, 'MODE', 'replay')
            http.set_transport(lambda *_: pytest.fail('replay hit the network'))
            assert http.get_json('https://example.test/search?q=dune') == {'docs': [1]}
        finally:
            http.set_transport(None)

    def test_a_parser_change_shows_in_replay(self, fixtures, monkeypatch):
        monkeypatch.setattr(cache, 'MODE', 'record')
        http.set_transport(lambda url, headers, timeout: b'{"title": "Dune", "year": 1965}')
        try:

            def old_parser(title, author):
                return {'title': http.get_json('https://example.test/' + title)['title']}

            def new_parser(title, author):
                answer = http.get_json('https://example.test/' + title)
                return {'title': answer['title'], 'year': answer['year']}

            assert cache.wrap('openlib', old_parser)('Dune', 'Herbert') == {'title': 'Dune'}
            monkeypatch.setattr(cache, 'MODE', 'replay')
            http.set_transport(lambda *_: pytest.fail('replay hit the network'))
            assert cache.wrap('openlib', new_parser)('Dune', 'Herbert') == {
                'title': 'Dune',
                'year': 1965,
            }
        finally:
            http.set_transport(None)

    def test_without_the_raw_body_the_parsed_record_still_serves(self, fixtures, monkeypatch):
        monkeypatch.setattr(cache, 'MODE', 'record')
        http.set_transport(lambda url, headers, timeout: b'{"title": "Dune"}')
        try:
            fetch = lambda t, a: http.get_json('https://example.test/' + t)  # noqa: E731
            cache.wrap('openlib', fetch)('Dune', 'Herbert')
            for raw_file in fixtures.glob('raw-*.json'):
                raw_file.unlink()
            monkeypatch.setattr(cache, 'MODE', 'replay')
            replayed = cache.wrap('openlib', lambda t, a: pytest.fail('replay hit the network'))
            assert replayed('Dune', 'Herbert') == {'title': 'Dune'}
        finally:
            http.set_transport(None)

    def test_a_body_that_is_not_json_is_retried_not_recorded(self, fixtures, monkeypatch):
        monkeypatch.setattr(cache, 'MODE', 'record')
        monkeypatch.setattr(http.time, 'sleep', lambda s: None)
        bodies = iter([b'<html>503</html>', b'{"docs": [1]}'])
        http.set_transport(lambda url, headers, timeout: next(bodies))
        try:
            assert http.get_json('https://example.test/search') == {'docs': [1]}
            monkeypatch.setattr(cache, 'MODE', 'replay')
            http.set_transport(lambda *_: pytest.fail('replay hit the network'))
            assert http.get_json('https://example.test/search') == {'docs': [1]}
        finally:
            http.set_transport(None)

    def test_a_parser_that_asks_a_new_url_falls_back_to_the_parsed_record(
        self, fixtures, monkeypatch
    ):
        monkeypatch.setattr(cache, 'MODE', 'record')
        http.set_transport(lambda url, headers, timeout: b'{"title": "Dune"}')
        try:
            fetch = lambda t, a: http.get_json('https://example.test/v1/' + t)  # noqa: E731
            assert cache.wrap('openlib', fetch)('Dune', 'Herbert') == {'title': 'Dune'}
            monkeypatch.setattr(cache, 'MODE', 'replay')
            http.set_transport(lambda *_: pytest.fail('replay hit the network'))
            moved = lambda t, a: http.get_json('https://example.test/v2/' + t)  # noqa: E731
            assert cache.wrap('openlib', moved)('Dune', 'Herbert') == {'title': 'Dune'}
        finally:
            http.set_transport(None)

    def test_a_stored_body_the_parser_rejects_falls_back_to_the_parsed_record(
        self, fixtures, monkeypatch
    ):
        monkeypatch.setattr(cache, 'MODE', 'record')
        http.set_transport(lambda url, headers, timeout: b'{"title": "Dune"}')
        try:
            fetch = lambda t, a: http.get_json('https://example.test/' + t)  # noqa: E731
            cache.wrap('openlib', fetch)('Dune', 'Herbert')
            raw_file = cache.raw_path('http', 'https://example.test/Dune')
            raw_file.write_text(json.dumps({'kind': 'http', 'key': 'x', 'body': '<html>'}))
            monkeypatch.setattr(cache, 'MODE', 'replay')
            http.set_transport(lambda *_: pytest.fail('replay hit the network'))
            monkeypatch.setattr(http.time, 'sleep', lambda s: pytest.fail('replay slept'))
            assert cache.wrap('openlib', fetch)('Dune', 'Herbert') == {'title': 'Dune'}
        finally:
            http.set_transport(None)

    def test_a_plugin_answer_replays_without_calibre(self, fixtures, monkeypatch):
        monkeypatch.setattr(cache, 'MODE', 'record')
        monkeypatch.setattr(calibre_plugin, 'require_plugin', lambda plugin: None)
        opf_text = (
            '<package xmlns="http://www.idpf.org/2007/opf" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<metadata><dc:title>Dune</dc:title></metadata></package>'
        )
        monkeypatch.setattr(calibre, 'fetch_metadata', lambda *a, **k: opf_text)
        first = calibre_plugin.fetch_plugin('Dune', 'Herbert', 'Kobo Metadata')
        assert first['title'] == 'Dune'

        monkeypatch.setattr(cache, 'MODE', 'replay')
        monkeypatch.setattr(calibre, 'fetch_metadata', lambda *a, **k: pytest.fail('ran calibre'))
        monkeypatch.setattr(
            calibre_plugin, 'require_plugin', lambda plugin: pytest.fail('probed calibre')
        )
        assert calibre_plugin.fetch_plugin('Dune', 'Herbert', 'Kobo Metadata') == first

    def test_a_bad_minute_does_not_overwrite_a_good_record(self, fixtures, monkeypatch):
        monkeypatch.setattr(cache, 'MODE', 'record')
        cache.wrap('openlib', lambda t, a: {'title': 'Dune'})('Dune', 'Herbert')
        failing = cache.wrap(
            'openlib', lambda t, a: (_ for _ in ()).throw(enrich.SourceError('TLS timeout'))
        )
        with pytest.raises(enrich.SourceError):
            failing('Dune', 'Herbert')

        monkeypatch.setattr(cache, 'MODE', 'replay')
        replayed = cache.wrap('openlib', lambda t, a: pytest.fail('replay hit the network'))
        assert replayed('Dune', 'Herbert') == {'title': 'Dune'}

    def test_the_record_names_the_raw_files_it_read(self, fixtures, monkeypatch):
        monkeypatch.setattr(cache, 'MODE', 'record')
        http.set_transport(lambda url, headers, timeout: b'{}')
        try:
            fetch = lambda t, a: http.get_json('https://example.test/' + t)  # noqa: E731
            cache.wrap('openlib', fetch)('Dune', 'Herbert')
        finally:
            http.set_transport(None)
        saved = json.loads(cache.fixture_path('openlib', 'Dune', 'Herbert').read_text())
        assert saved['raw'] == [cache.raw_path('http', 'https://example.test/Dune').name]


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

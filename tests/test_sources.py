"""Source availability and pacing.

A missing plugin used to be indistinguishable from "this book is not in the
catalogue". That is how the tool ran for weeks on one source while claiming
three, and it is why every decision in that period had no second opinion.
"""

import pytest

from ebook_metamend import enrich
from ebook_metamend.sources import Pacer, Source
from ebook_metamend.sources.calibre_plugin import SourceUnavailable, require_plugin


@pytest.fixture(autouse=True)
def _clear_unavailable():
    enrich.unavailable_sources.clear()
    yield
    enrich.unavailable_sources.clear()


class TestRequirePlugin:
    def test_a_missing_plugin_raises(self, monkeypatch):
        monkeypatch.setattr(
            'ebook_metamend.calibre.installed_metadata_plugins', lambda: frozenset({'Google'})
        )
        with pytest.raises(SourceUnavailable, match='Kobo'):
            require_plugin('Kobo Metadata')

    def test_an_installed_plugin_passes(self, monkeypatch):
        monkeypatch.setattr(
            'ebook_metamend.calibre.installed_metadata_plugins',
            lambda: frozenset({'Google', 'Kobo Metadata'}),
        )
        require_plugin('Kobo Metadata')

    def test_an_empty_plugin_list_does_not_block(self, monkeypatch):
        """If the listing itself failed we cannot tell, so do not invent a
        failure. Better to try and get a real error than refuse on a guess."""
        monkeypatch.setattr(
            'ebook_metamend.calibre.installed_metadata_plugins', lambda: frozenset()
        )
        require_plugin('Kobo Metadata')


class TestQuerySources:
    def test_an_unavailable_source_is_recorded_not_silently_skipped(self, monkeypatch):
        def missing(_title, _author):
            raise SourceUnavailable('the Kobo plugin is not installed')

        monkeypatch.setattr(enrich, 'SOURCES', (Source('kobo', missing, pause=0),))
        answers = enrich.query_sources('Atomic Habits', 'James Clear', pause=False)

        assert answers == {}
        assert 'kobo' in enrich.unavailable_sources

    def test_an_unavailable_source_is_not_retried_for_every_book(self, monkeypatch):
        calls = []

        def missing(_title, _author):
            calls.append(1)
            raise SourceUnavailable('nope')

        monkeypatch.setattr(enrich, 'SOURCES', (Source('kobo', missing, pause=0),))
        for _ in range(5):
            enrich.query_sources('t', 'a', pause=False)

        assert len(calls) == 1, 'a missing plugin should be discovered once, not per book'

    def test_a_source_with_no_answer_is_not_marked_unavailable(self, monkeypatch):
        """No answer is a normal outcome. Conflating it with a broken source is
        what hid the missing plugin in the first place."""
        monkeypatch.setattr(enrich, 'SOURCES', (Source('google', lambda *_: None, pause=0),))
        enrich.query_sources('t', 'a', pause=False)

        assert enrich.unavailable_sources == {}


class TestPacer:
    def test_a_answering_source_keeps_the_baseline_pause(self):
        pacer = Pacer()
        source = Source('google', lambda *_: None, pause=8)
        pacer.record('google', answered=True)
        assert pacer.delay(source) == 8

    def test_consecutive_misses_back_off(self):
        pacer = Pacer()
        source = Source('google', lambda *_: None, pause=2)
        pacer.record('google', answered=False)
        first = pacer.delay(source)
        pacer.record('google', answered=False)
        assert pacer.delay(source) > first

    def test_backing_off_is_capped(self):
        pacer = Pacer(ceiling=10)
        source = Source('google', lambda *_: None, pause=8)
        for _ in range(20):
            pacer.record('google', answered=False)
        assert pacer.delay(source) == 10

    def test_an_answer_resets_the_back_off(self):
        pacer = Pacer()
        source = Source('google', lambda *_: None, pause=3)
        for _ in range(4):
            pacer.record('google', answered=False)
        pacer.record('google', answered=True)
        assert pacer.delay(source) == 3


class TestRunStateIsolation:
    """Module state that survives between runs means a source that failed once is
    never retried, and back-off from a previous run still applies."""

    def test_reset_forgets_unavailable_sources(self):
        enrich.unavailable_sources['kobo'] = 'missing'
        enrich.reset_run_state()
        assert enrich.unavailable_sources == {}

    def test_reset_clears_accumulated_back_off(self):
        source = Source('google', lambda *_: None, pause=4)
        for _ in range(5):
            enrich._pacer.record('google', answered=False)
        assert enrich._pacer.delay(source) > 4
        enrich.reset_run_state()
        assert enrich._pacer.delay(source) == 4

    def test_run_resets_before_starting(self, monkeypatch):
        enrich.unavailable_sources['kobo'] = 'missing from a previous run'
        monkeypatch.setattr(enrich, 'SOURCES', ())
        enrich.run([])
        assert enrich.unavailable_sources == {}


class TestPacerClamping:
    def test_the_exponent_cannot_grow_without_bound(self):
        """min() clamps the result, but 2**misses is computed first, so a source
        that never answers would build an astronomically large integer."""
        pacer = Pacer(max_misses=8)
        for _ in range(10_000):
            pacer.record('dead', answered=False)
        assert pacer._misses['dead'] == 8

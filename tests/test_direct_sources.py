"""The keyless catalogues and the transport they share.

Every fetch here goes through ``sources.http``, so a fake transport is the
whole test double: no socket, no monkeypatching inside the source modules.
"""

import json
import urllib.parse

import pytest

from ebook_metamend import sources
from ebook_metamend.sources import http
from ebook_metamend.sources.apple import fetch_apple
from ebook_metamend.sources.errors import SourceError
from ebook_metamend.sources.inventaire import fetch_inventaire


@pytest.fixture(autouse=True)
def _restore_transport():
    yield
    http.set_transport(None)


def serve(pages: dict[str, object]):
    """A transport answering by URL substring, remembering what was asked."""
    asked: list[str] = []

    def transport(url, headers, timeout):
        asked.append(url)
        for key, payload in pages.items():
            if key in url:
                return json.dumps(payload).encode()
        raise AssertionError(f'unexpected URL {url}')

    http.set_transport(transport)
    return asked


class TestTransport:
    def test_the_agent_names_the_project_not_a_person(self):
        assert 'github.com/OffCrazyFreak' in http.USER_AGENT
        assert '@' not in http.USER_AGENT

    def test_a_failed_catalogue_raises_instead_of_reading_as_no_book(self, monkeypatch):
        monkeypatch.setattr(http.time, 'sleep', lambda _s: None)

        def down(url, headers, timeout):
            raise OSError('connection refused')

        http.set_transport(down)
        with pytest.raises(SourceError, match='2 attempts'):
            http.get_json('https://example.invalid/x')

    def test_a_transient_failure_is_retried_once(self, monkeypatch):
        monkeypatch.setattr(http.time, 'sleep', lambda _s: None)
        calls = []

        def flaky(url, headers, timeout):
            calls.append(url)
            if len(calls) == 1:
                raise OSError('reset')
            return b'{"ok": true}'

        http.set_transport(flaky)
        assert http.get_json('https://example.invalid/x') == {'ok': True}
        assert len(calls) == 2

    def test_none_restores_urllib(self):
        http.set_transport(lambda *_: b'{}')
        http.set_transport(None)
        assert http._transport is http._urllib


APPLE_HITS = {
    'results': [
        {
            'kind': 'ebook',
            'trackName': 'The Quiet Orchard',
            'artistName': 'Mara Voss',
            'genres': ['Books', 'Fiction & Literature', 'Literary'],
            'description': '<p>A house, a hill &amp; a harvest.</p>',
        },
        {
            'kind': 'ebook',
            'trackName': 'The Quiet Orchard Companion',
            'artistName': 'Someone Else',
            'genres': ['Books', 'Reference'],
            'description': 'Not the book.',
        },
        {'kind': 'audiobook', 'trackName': 'The Quiet Orchard', 'artistName': 'Mara Voss'},
    ]
}


class TestApple:
    def test_the_hit_closest_to_the_filename_wins(self):
        asked = serve({'itunes.apple.com': APPLE_HITS})
        record = fetch_apple('The Quiet Orchard', 'Mara Voss')

        assert record is not None
        assert record['title'] == 'The Quiet Orchard'
        assert record['authors'] == ['Mara Voss']
        assert 'media=ebook' in asked[0] and 'entity=ebook' in asked[0]

    def test_html_is_stripped_and_the_storefront_genre_dropped(self):
        serve({'itunes.apple.com': APPLE_HITS})
        record = fetch_apple('The Quiet Orchard', 'Mara Voss')

        assert record['description'] == 'A house, a hill & a harvest.'
        assert record['tags'] == ['Fiction & Literature', 'Literary']

    def test_it_never_claims_a_publisher_or_isbn(self):
        """Apple has neither, and a blank must not look like a find."""
        serve({'itunes.apple.com': APPLE_HITS})
        record = fetch_apple('The Quiet Orchard', 'Mara Voss')

        assert record['publisher'] == '' and record['isbn'] == ''
        assert record['series'] is None and record['sidx'] is None

    def test_no_ebook_results_means_no_answer(self):
        serve({'itunes.apple.com': {'results': [APPLE_HITS['results'][2]]}})
        assert fetch_apple('The Quiet Orchard', 'Mara Voss') is None


INVENTAIRE_SEARCH = {
    'results': [
        {'uri': 'wd:Q1', 'label': 'The Quiet Orchard', 'description': 'novel'},
        {'uri': 'wd:Q2', 'label': 'The Quiet Orchard Companion', 'description': 'guide'},
        {'uri': 'wd:Q3', 'label': 'Something Unrelated Entirely', 'description': ''},
    ]
}
INVENTAIRE_WORKS = {
    'entities': {
        'wd:Q1': {
            'labels': {'en': 'The Quiet Orchard'},
            'claims': {
                'wdt:P50': ['wd:Q10'],
                'wdt:P136': ['wd:Q20'],
                'wdt:P921': ['wd:Q21'],
                'wdt:P179': ['wd:Q30'],
                'wdt:P1545': ['2'],
            },
        },
        'wd:Q2': {
            'labels': {'en': 'The Quiet Orchard Companion'},
            'claims': {'wdt:P50': ['wd:Q11']},
        },
    }
}
INVENTAIRE_LABELS = {
    'entities': {
        'wd:Q10': {'labels': {'en': 'Mara Voss'}},
        'wd:Q11': {'labels': {'fr': 'Quelqu\'un'}},
        'wd:Q20': {'labels': {'en': 'literary fiction'}},
        'wd:Q21': {'labels': {'en': 'orchards'}},
        'wd:Q30': {'labels': {'en': 'Hill Country'}},
    }
}


def serve_inventaire():
    """Works and labels share one endpoint; the batch tells them apart."""
    asked: list[str] = []

    def transport(url, headers, timeout):
        asked.append(url)
        if 'api/search' in url:
            return json.dumps(INVENTAIRE_SEARCH).encode()
        uris = set(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['uris'][0].split('|'))
        if uris <= set(INVENTAIRE_WORKS['entities']):
            return json.dumps(INVENTAIRE_WORKS).encode()
        return json.dumps(INVENTAIRE_LABELS).encode()

    http.set_transport(transport)
    return asked


class TestInventaire:
    def test_a_work_gets_its_author_from_the_entity_lookup(self):
        asked = serve_inventaire()
        record = fetch_inventaire('The Quiet Orchard', 'Mara Voss')

        assert record is not None
        assert record['title'] == 'The Quiet Orchard'
        assert record['authors'] == ['Mara Voss']
        assert record['tags'] == ['literary fiction', 'orchards']
        assert record['series'] == 'Hill Country' and record['sidx'] == '2'
        assert record['publisher'] == '' and record['isbn'] == ''
        # Search, works, labels: the whole cost of one book.
        assert len(asked) == 3

    def test_only_titles_worth_a_round_trip_are_looked_up(self):
        """The unrelated third hit must not reach the entity call."""
        asked = serve_inventaire()
        fetch_inventaire('The Quiet Orchard', 'Mara Voss')

        assert 'wd%3AQ3' not in asked[1]

    def test_nothing_close_means_no_answer_and_no_second_call(self):
        asked = serve({'api/search': INVENTAIRE_SEARCH})
        assert fetch_inventaire('Completely Different Name', 'Nobody') is None
        assert len(asked) == 1

    def test_a_label_in_another_language_still_counts(self):
        serve_inventaire()
        record = fetch_inventaire('The Quiet Orchard Companion', 'Quelqu\'un')
        assert record['authors'] == ["Quelqu'un"]


class TestSelect:
    def test_order_follows_the_registry_not_the_request(self):
        chosen = sources.select(['inventaire', 'kobo', 'apple'])
        assert [s.name for s in chosen] == ['kobo', 'apple', 'inventaire']

    def test_an_unknown_name_is_an_error_not_a_silent_drop(self):
        with pytest.raises(ValueError, match='unknown source'):
            sources.select(['kobo', 'goodreads'])

    def test_the_web_set_is_keyless_only(self):
        assert set(sources.WEB_SOURCE_NAMES) == {'apple', 'openlib', 'inventaire'}
        assert 'kobo' not in sources.WEB_SOURCE_NAMES

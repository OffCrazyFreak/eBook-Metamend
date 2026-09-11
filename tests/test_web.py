"""The worker-facing entry points, run without Pyodide.

A visitor's files arrive as bytes and leave as bytes; in between the same
pipeline runs as on the desktop, with the three keyless sources only.
"""

import json
import urllib.parse

import pytest

from ebook_metamend import enrich, web
from ebook_metamend.sources import http
from ebook_metamend.sources.errors import SourceError
from test_writers import make_epub

# One answer per keyless catalogue, all naming the filename's book.
APPLE = {
    'results': [
        {
            'kind': 'ebook',
            'trackName': 'The Quiet Orchard',
            'artistName': 'Mara Voss',
            'genres': ['Books', 'Fiction'],
            'description': 'A house on a hill.',
        }
    ]
}
OPENLIB = {
    'docs': [
        {
            'title': 'The Quiet Orchard',
            'author_name': ['Mara Voss'],
            'publisher': ['Hollow Beech Press'],
            'subject': ['Orchards'],
            'isbn': ['9781940000012'],
        }
    ]
}
INVENTAIRE_SEARCH = {'results': [{'uri': 'wd:Q1', 'label': 'The Quiet Orchard'}]}
INVENTAIRE_WORKS = {'entities': {'wd:Q1': {'claims': {'wdt:P50': ['wd:Q10']}}}}
INVENTAIRE_LABELS = {'entities': {'wd:Q10': {'labels': {'en': 'Mara Voss'}}}}


@pytest.fixture(autouse=True)
def _fake_catalogues():
    asked: list[str] = []

    def transport(url, headers, timeout):
        asked.append(url)
        if 'itunes.apple.com' in url:
            return json.dumps(APPLE).encode()
        if 'openlibrary.org' in url:
            return json.dumps(OPENLIB).encode()
        if 'api/search' in url:
            return json.dumps(INVENTAIRE_SEARCH).encode()
        uris = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['uris'][0]
        return json.dumps(INVENTAIRE_WORKS if uris == 'wd:Q1' else INVENTAIRE_LABELS).encode()

    http.set_transport(transport)
    enrich.reset_run_state()
    yield asked
    http.set_transport(None)


def epub_bytes(tmp_path) -> bytes:
    path = tmp_path / 'source.epub'
    make_epub(path)
    return path.read_bytes()


class TestPropose:
    def test_bytes_in_proposal_out_and_nothing_left_behind(self, tmp_path):
        root = tmp_path / 'library'
        stem = 'Mara Voss - The Quiet Orchard'
        heard = []
        result = web.propose(
            stem,
            {'.epub': epub_bytes(tmp_path)},
            str(root),
            on_answer=lambda n, ok: heard.append(n),
        )

        assert result is not None
        assert result['conf'] == 'HIGH'
        assert set(result['sources']) == {'apple', 'openlib', 'inventaire'}
        assert result['gains']['description'] == 'A house on a hill.'
        assert result['files'] == {'.epub': f'{stem}.epub'}
        assert result['current']['title'] == 'Example Title'
        assert result['unreadable'] is False
        assert {s['name'] for s in result['scores']} == {'apple', 'openlib', 'inventaire'}
        assert heard == ['openlib', 'apple', 'inventaire']
        assert web.unavailable() == []
        assert not any(root.rglob('*'))

    def test_a_folder_in_the_stem_is_kept_apart(self, tmp_path):
        """Two books with one filename in different folders are different books."""
        root = tmp_path / 'library'
        result = web.propose(
            'Fiction/Mara Voss - The Quiet Orchard', {'.epub': epub_bytes(tmp_path)}, str(root)
        )
        assert result['stem'] == 'Fiction/Mara Voss - The Quiet Orchard'
        assert result['files'] == {'.epub': 'Mara Voss - The Quiet Orchard.epub'}
        # The folder made for the book goes with it.
        assert not (root / 'Fiction').exists()
        # The folder is not part of the author's name.
        assert result['conf'] == 'HIGH'
        assert web.facts('Fiction/Mara Voss - The Quiet Orchard')['author'] == 'Mara Voss'

    def test_a_stem_without_a_title_asks_nobody(self, tmp_path, _fake_catalogues):
        assert (
            web.propose('Just A Name', {'.epub': epub_bytes(tmp_path)}, str(tmp_path / 'l')) is None
        )
        assert _fake_catalogues == []

    def test_facts_follow_the_filename_parser(self):
        assert web.facts('Mara Voss - Hill Country - 02 - The Quiet Orchard') == {
            'author': 'Mara Voss',
            'title': 'The Quiet Orchard',
            'series': 'Hill Country',
            'series_index': '02',
        }


class TestApply:
    def test_the_gains_come_back_written_into_the_bytes(self, tmp_path):
        root = tmp_path / 'library'
        stem = 'Mara Voss - The Quiet Orchard'
        data = epub_bytes(tmp_path)
        proposal = web.propose(stem, {'.epub': data}, str(root))

        out = web.apply(stem, {'.epub': data}, str(root), proposal)

        assert out['writes'] == [{'ext': '.epub', 'ok': True, 'reason': ''}]
        assert out['files']['.epub'] != data
        written = tmp_path / 'written.epub'
        written.write_bytes(out['files']['.epub'])
        from ebook_metamend import calibre

        assert calibre.read_book_metadata(str(written))['description'] == 'A house on a hill.'
        assert not any(root.rglob('*'))

    def test_no_gains_returns_the_bytes_untouched(self, tmp_path):
        data = epub_bytes(tmp_path)
        proposal = {
            'stem': 's',
            'conf': 'HIGH',
            'sources': [],
            'gains': {},
            'merged': {},
            'fn_score': 0,
            'au_score': 0,
            'src_titles': {},
            'files': {},
        }
        out = web.apply('s', {'.epub': data}, str(tmp_path / 'l'), proposal)
        assert out['files']['.epub'] == data and out['writes'] == []


class TestPacing:
    def test_the_pause_is_the_slowest_web_source(self):
        # Apple's 3 s is the ceiling of the three at their baseline.
        assert web.pause_after() == 3


class TestBundle:
    def test_every_file_lands_under_its_own_path(self, tmp_path):
        import io
        import zipfile

        data = web.bundle({'a/x.epub': b'one', 'y.pdf': b'two'})
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            assert sorted(archive.namelist()) == ['a/x.epub', 'y.pdf']
            assert archive.read('a/x.epub') == b'one'


class TestTransport:
    def test_the_worker_function_is_wrapped_and_the_agent_dropped(self):
        seen = {}

        def fetch(url, headers_json, timeout):
            seen['headers'] = json.loads(headers_json)
            seen['timeout'] = timeout
            return b'{"ok": true}'

        web.install_transport(fetch)
        assert http.get_json('https://example.invalid/x', timeout=7) == {'ok': True}
        assert 'User-Agent' not in seen['headers'] and seen['headers']['Accept']
        assert seen['timeout'] == 7

    def test_a_browser_error_reads_as_a_source_error(self, monkeypatch):
        monkeypatch.setattr(http.time, 'sleep', lambda _s: None)

        class JsException(Exception):
            pass

        def fetch(url, headers_json, timeout):
            raise JsException('NetworkError: timeout')

        web.install_transport(fetch)
        with pytest.raises(SourceError, match='OSError'):
            http.get_json('https://example.invalid/x')

    def test_begin_run_forgets_a_shelved_source(self):
        enrich.unavailable_sources['openlib'] = 'down'
        web.begin_run()
        assert enrich.unavailable_sources == {}

"""Filename parsing, library walking, OPF parsing and junk-title detection."""

import textwrap

import pytest

from ebook_metamend.library import books, pairs, parse_filename, walk
from ebook_metamend.matching import junky
from ebook_metamend.opf import parse


class TestParseFilename:
    def test_splits_author_from_title(self):
        facts = parse_filename('James Clear - Atomic Habits')
        assert facts.author == 'James Clear'
        assert facts.title == 'Atomic Habits'

    def test_strips_an_embedded_series_number(self):
        facts = parse_filename('Some Author - Example Saga - 02.5 - Second Volume')
        assert facts.title == 'Second Volume'
        assert facts.series == 'Example Saga'
        assert facts.series_index == '02.5'

    def test_the_series_name_is_not_glued_onto_the_title(self):
        """Glued together it reads "The Ravenhood Flock", which no catalogue has
        ever returned, so every book named this way scored 0.69 on its title and
        could never reach HIGH however exactly the sources agreed."""
        facts = parse_filename('Kate Stewart - The Ravenhood - 01 - Flock')
        assert facts.title == 'Flock'
        assert facts.query == 'Flock'

    def test_a_subtitle_is_not_mistaken_for_a_series(self):
        facts = parse_filename('John Carreyrou - Bad Blood - Secrets And Lies')
        assert facts.series is None
        assert facts.title == 'Bad Blood - Secrets And Lies'

    def test_query_stops_at_a_subtitle(self):
        facts = parse_filename('John Carreyrou - Bad Blood - Secrets And Lies')
        assert facts.query == 'Bad Blood'

    def test_query_stops_at_a_colon_or_parenthesis(self):
        assert parse_filename('A - Title: Subtitle').query == 'Title'
        assert parse_filename('A - Title (3rd Edition)').query == 'Title'

    def test_query_never_ends_up_empty(self):
        """A title that is only a separator must fall back to the full title,
        otherwise the tool queries the sources for an empty string."""
        facts = parse_filename('Author - : odd')
        assert facts.query


class TestWalk:
    @pytest.fixture
    def library(self, tmp_path):
        (tmp_path / 'Fiction').mkdir()
        (tmp_path / 'Fiction' / 'A - Both.epub').write_bytes(b'x')
        (tmp_path / 'Fiction' / 'A - Both.pdf').write_bytes(b'x')
        (tmp_path / 'Fiction' / 'A - EpubOnly.epub').write_bytes(b'x')
        nested = tmp_path / 'Parenting' / '01 - Foundations'
        nested.mkdir(parents=True)
        (nested / 'B - Nested.epub').write_bytes(b'x')
        (nested / 'B - Nested.pdf').write_bytes(b'x')
        (tmp_path / 'Fiction' / 'cover.jpg').write_bytes(b'x')
        # Same filename, different category. These are two different books.
        (tmp_path / 'Poetry').mkdir()
        (tmp_path / 'Poetry' / 'A - Both.epub').write_bytes(b'x')
        return tmp_path

    def test_finds_books_in_nested_folders(self, library):
        stems = [b.stem for b in books(str(library))]
        assert 'B - Nested' in stems

    def test_ignores_files_that_are_not_books(self, library):
        assert not any(b.stem == 'cover' for b in books(str(library)))

    def test_same_filename_in_two_folders_stays_two_books(self, library):
        """Keying on the basename merged these, which could pair one book's EPUB
        with another book's PDF and write metadata to the wrong file."""
        found = walk(str(library))
        assert len(found) == 4, sorted(found)
        both = [b for b in books(str(library)) if b.stem == 'A - Both']
        assert len(both) == 2
        assert {tuple(sorted(b.formats)) for b in both} == {('.epub', '.pdf'), ('.epub',)}

    def test_ordering_is_by_filename_not_by_folder(self, library):
        stems = [b.stem for b in books(str(library))]
        assert stems == sorted(stems)

    def test_books_includes_single_format_stems(self, library):
        stems = [b.stem for b in books(str(library))]
        assert 'A - EpubOnly' in stems

    def test_pairs_excludes_single_format_stems(self, library):
        stems = [b.stem for b in pairs(str(library))]
        assert 'A - EpubOnly' not in stems
        assert {'A - Both', 'B - Nested'} <= set(stems)

    def test_a_single_format_book_still_has_a_readable_path(self, library):
        """``any_path`` must never be None for a book the walker returned, or it
        ends up in a subprocess argument list."""
        for book in books(str(library)):
            assert book.any_path is not None


OPF_TEMPLATE = textwrap.dedent("""\
    noise before
    <package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="i">
      <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"
                xmlns:opf="http://www.idpf.org/2007/opf">
        <dc:title>Atomic Habits</dc:title>
        <dc:creator>James Clear</dc:creator>
        <dc:publisher>Avery</dc:publisher>
        <dc:description>A book.</dc:description>
        <dc:subject>Self-Help</dc:subject>
        <dc:subject>Psychology</dc:subject>
        <dc:identifier id="i">{identifier}</dc:identifier>
        <meta name="calibre:series" content="Habits"/>
        <meta name="calibre:series_index" content="1"/>
      </metadata>
    </package>
    noise after
    """)


class TestParseOpf:
    def test_extracts_every_field(self):
        record = parse(OPF_TEMPLATE.format(identifier='isbn:9780735211292'))
        assert record['title'] == 'Atomic Habits'
        assert record['authors'] == ['James Clear']
        assert record['publisher'] == 'Avery'
        assert record['tags'] == ['Self-Help', 'Psychology']
        assert record['series'] == 'Habits'
        assert record['sidx'] == '1'
        assert record['isbn'] == '9780735211292'

    def test_tolerates_log_noise_around_the_package(self):
        assert parse(OPF_TEMPLATE.format(identifier='isbn:1')) is not None

    def test_returns_none_when_there_is_no_package(self):
        assert parse('not xml at all') is None

    def test_returns_none_on_malformed_xml(self):
        assert parse('<package><unclosed></package>') is None

    def test_bare_isbn_is_ignored_by_default(self):
        record = parse(OPF_TEMPLATE.format(identifier='9780735211292'))
        assert record['isbn'] == ''

    def test_bare_isbn_is_read_when_the_fallback_is_enabled(self):
        """The two original scripts disagreed here. The difference is preserved
        rather than silently resolved, because enabling it changes which books
        gain an ISBN."""
        record = parse(OPF_TEMPLATE.format(identifier='9780735211292'), bare_isbn_fallback=True)
        assert record['isbn'] == '9780735211292'


class TestJunky:
    @pytest.mark.parametrize(
        'title',
        ['', '   ', None, 'manuscript.indd', 'Final.doc', 'untitled', 'Microsoft Word', 'NBRT_A01'],
    )
    def test_junk_titles_are_rejected(self, title):
        assert junky(title) is True

    @pytest.mark.parametrize('title', ['Atomic Habits', 'Artemis', 'On Liberty', 'It'])
    def test_real_titles_are_kept(self, title):
        assert junky(title) is False

    def test_empty_is_junk_even_though_no_regex_matches_it(self):
        """The regex constants the original carried alongside this function did
        not match an empty string, so replacing the function with them would have
        silently broken the PDF-with-no-title case."""
        assert junky('') is True

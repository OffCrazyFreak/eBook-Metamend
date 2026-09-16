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


class TestNamesFromTheWild:
    """How download sites and library managers actually name files, measured
    (docs/filenames.md). Each shape is read the way its own tool wrote it, and
    the invented book behind every example is Mara Voss's "The Quiet Orchard".
    """

    @pytest.mark.parametrize(
        'stem, scheme, author, title',
        [
            # OceanofPDF: underscores for spaces, title first, "_-_" between them.
            (
                '_OceanofPDF.com_The_Quiet_Orchard_-_Mara_Voss',
                'oceanofpdf',
                'Mara Voss',
                'The Quiet Orchard',
            ),
            (
                'OceanofPDF.com_Slow-Grown_Fruit_-_Mara_Voss',
                'oceanofpdf',
                'Mara Voss',
                'Slow-Grown Fruit',
            ),
            # Anna's Archive: " -- " between fields, every "." turned into "_".
            (
                'The Quiet Orchard -- Mara T_ Voss -- Hill Press, 2011 -- Hill Press -- 9781594488849 -- '
                '0123456789abcdef0123456789abcdef -- Anna’s Archive',
                'annas-archive',
                'Mara T. Voss',
                'The Quiet Orchard',
            ),
            # Z-Library over the years, the dropped colon leaving two spaces behind.
            (
                'The Quiet Orchard  a year of pruning (Voss, Mara) (z-lib.org)',
                'z-library',
                'Mara Voss',
                'The Quiet Orchard: a year of pruning',
            ),
            (
                'The Quiet Orchard (Mara Voss) (Z-Library)',
                'z-library',
                'Mara Voss',
                'The Quiet Orchard',
            ),
            (
                'The Quiet Orchard (Voss, Mara etc.) (z-library.sk, 1lib.sk, z-lib.sk)',
                'z-library',
                'Mara Voss',
                'The Quiet Orchard',
            ),
            (
                'The Quiet Orchard by Mara Voss (z-lib.org)',
                'z-library',
                'Mara Voss',
                'The Quiet Orchard',
            ),
            (
                'The Quiet Orchard (Mara Voss)\u2014_Hill Press_English_9781594488849 (Z-Library)',
                'z-library',
                'Mara Voss',
                'The Quiet Orchard',
            ),
            # PDFDrive: title only, "_ " where a colon was.
            ('The Quiet Orchard ( PDFDrive )', 'pdfdrive', '', 'The Quiet Orchard'),
            (
                'Orchards_ The Quiet Ones ( PDFDrive.com )',
                'pdfdrive',
                '',
                'Orchards: The Quiet Ones',
            ),
            # Library Genesis, spaced and dotted.
            (
                'Mara Voss - The Quiet Orchard (2011, Hill Press) - libgen.li',
                'libgen',
                'Mara Voss',
                'The Quiet Orchard',
            ),
            (
                'Mara.Voss.-.The.Quiet.Orchard.2011.Hill.Press.-.libgen.lc.1',
                'libgen',
                'Mara Voss',
                'The Quiet Orchard',
            ),
            ('Mara Voss - The Quiet Orch - libgen.li', 'libgen', 'Mara Voss', 'The Quiet Orch'),
            # Scene release folders.
            (
                'Mara.Voss.-.The.Quiet.Orchard.2011.RETAIL.EPUB.eBook-GRP',
                'dotted',
                'Mara Voss',
                'The Quiet Orchard',
            ),
            # Sharing channels and ebook-tools output.
            (
                'Mara Voss - The Quiet Orchard [RSC] (retail)',
                '',
                'Mara Voss',
                'The Quiet Orchard [RSC]',
            ),
            (
                'Mara Voss - The Quiet Orchard (2011) [9781594488849]',
                '',
                'Mara Voss',
                'The Quiet Orchard',
            ),
            # Slugs: Standard Ebooks, dokumen.pub, vdoc.pub, epdf.pub.
            ('mara-voss_the-quiet-orchard', 'slug', 'Mara Voss', 'The Quiet Orchard'),
            ('mara-voss_the-quiet-orchard_advanced', 'slug', 'Mara Voss', 'The Quiet Orchard'),
            (
                'the-quiet-orchard-9781594488849-9781594488856-2011024417',
                'slug',
                '',
                'The Quiet Orchard',
            ),
            ('the-quiet-orchard-1nbsped-9781594488849', 'slug', '', 'The Quiet Orchard'),
            ('the-quiet-orchard-4u9bqm2ndpq0', 'slug', '', 'The Quiet Orchard'),
            ('epdf-pub-the-quiet-orchard-pdf', 'slug', '', 'The Quiet Orchard'),
            # Springer: CamelCase after the year, cut short by the site.
            (
                '2011_Book_TheQuietOrchardAYearOfPrun',
                'springer',
                '',
                'The Quiet Orchard A Year Of Prun',
            ),
            # Underscores for spaces and nothing else (Humble Bundle, publishers).
            ('The_Quiet_Orchard_2nd_Edition', '', '', 'The Quiet Orchard 2nd Edition'),
            # "Title by Author" (Z-Library once, renaming tools still).
            ('The Quiet Orchard by Mara Voss', 'title-by-author', 'Mara Voss', 'The Quiet Orchard'),
            # Other separators between the same two halves.
            ('Mara Voss \u2013 The Quiet Orchard', '', 'Mara Voss', 'The Quiet Orchard'),
            ('Mara Voss \u2014 The Quiet Orchard', '', 'Mara Voss', 'The Quiet Orchard'),
            ('Mara Voss _ The Quiet Orchard', '', 'Mara Voss', 'The Quiet Orchard'),
            # Kobo's double extension, a browser's duplicate counter, Scribd's title bar.
            ('Mara Voss - The Quiet Orchard.kepub', '', 'Mara Voss', 'The Quiet Orchard'),
            ('Mara Voss - The Quiet Orchard (1)', '', 'Mara Voss', 'The Quiet Orchard'),
            ('The Quiet Orchard | PDF | Gardening', '', '', 'The Quiet Orchard'),
            # A title and nobody's name.
            ('The Quiet Orchard', '', '', 'The Quiet Orchard'),
        ],
    )
    def test_is_read_the_way_its_tool_wrote_it(self, stem, scheme, author, title):
        facts = parse_filename(stem)
        assert (facts.scheme, facts.author, facts.title) == (scheme, author, title)

    @pytest.mark.parametrize(
        'stem, scheme',
        [
            ('pg1342-images-3', 'gutenberg'),
            ('quietorchardyea0000voss_lcp', 'internet-archive'),
            ('978-1-59448-884-9', 'isbn'),
            ('9781594488849', 'isbn'),
            ('B00KYB2XAA_EBOK', 'kindle'),
        ],
    )
    def test_a_name_that_carries_no_title_says_so(self, stem, scheme):
        facts = parse_filename(stem)
        assert facts.title == ''
        assert facts.query == ''
        assert facts.scheme == scheme
        assert facts.alternate is None

    def test_a_plain_name_is_read_author_first_with_the_other_way_kept(self):
        facts = parse_filename('Mara Voss - Quiet Orchard')
        assert (facts.author, facts.title) == ('Mara Voss', 'Quiet Orchard')
        assert facts.alternate is not None
        assert (facts.alternate.author, facts.alternate.title) == ('Quiet Orchard', 'Mara Voss')
        assert facts.alternate.alternate is None

    @pytest.mark.parametrize(
        'stem',
        [
            'Mara Voss - The Quiet Orchard: A Year of Pruning',
            'Mara Voss - Some Product Guide for Version 4 Cloud and Beyond',
            'The Quiet Orchard: A Year of Pruning - Mara Voss',
        ],
    )
    def test_a_half_that_cannot_be_a_person_leaves_no_other_reading(self, stem):
        facts = parse_filename(stem)
        assert facts.author == 'Mara Voss'
        assert facts.alternate is None

    @pytest.mark.parametrize(
        'stem',
        [
            # A subtitle, an article or a long run of words reads as a title.
            'The Quiet Orchard: A Year of Pruning - Mara T. Voss',
            'The Quiet Orchard - Mara T. Voss',
            'Quiet Orchards of the North - Mara Voss',
            'Orchard - Mara Voss',
        ],
    )
    def test_a_name_whose_last_half_reads_as_a_person_is_read_title_first(self, stem):
        facts = parse_filename(stem)
        assert facts.author == facts.stem.split(' - ')[-1]
        assert facts.scheme == 'title-first'

    def test_two_names_joined_by_and_are_one_author(self):
        facts = parse_filename('Colin Bryar and Bill Carr - Working Backwards')
        assert facts.author == 'Colin Bryar and Bill Carr'

    def test_a_series_name_has_no_other_reading(self):
        assert parse_filename('Mara Voss - Hill Country - 02 - The Quiet Orchard').alternate is None

    def test_series_shapes_from_other_tools(self):
        facts = parse_filename(
            'Mara Voss - [Hill Country #2] - The Quiet Orchard (2011) [9781594488849]'
        )
        assert (facts.series, facts.series_index, facts.title) == (
            'Hill Country',
            '2',
            'The Quiet Orchard',
        )
        facts = parse_filename('Mara Voss - The Quiet Orchard (Hill Country Book 2)')
        assert (facts.series, facts.series_index, facts.title) == (
            'Hill Country',
            '2',
            'The Quiet Orchard',
        )

    def test_a_title_containing_by_keeps_the_whole_as_a_second_reading(self):
        facts = parse_filename('Death by Black Hole')
        assert facts.alternate is not None
        assert (facts.alternate.author, facts.alternate.title) == ('', 'Death by Black Hole')

    def test_last_comma_first_is_turned_round_but_a_suffix_is_not(self):
        assert parse_filename('Voss, Mara - The Quiet Orchard').author == 'Mara Voss'
        assert parse_filename('Smith, Jr. - The Quiet Orchard').author == 'Smith, Jr.'


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

    def test_epub3_urn_isbn_is_read(self):
        record = parse(OPF_TEMPLATE.format(identifier='urn:isbn:9780735211292'))
        assert record['isbn'] == '9780735211292'

    def test_an_empty_urn_does_not_blank_an_earlier_isbn(self):
        xml = OPF_TEMPLATE.format(
            identifier='urn:isbn:9780735211292</dc:identifier><dc:identifier>urn:isbn:'
        )
        assert parse(xml)['isbn'] == '9780735211292'

    def test_epub2_scheme_attribute_is_read(self):
        xml = OPF_TEMPLATE.replace(
            '<dc:identifier id="i">{identifier}</dc:identifier>',
            '<dc:identifier id="i" opf:scheme="ISBN">9780735211292</dc:identifier>',
        )
        assert parse(xml)['isbn'] == '9780735211292'

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
        [
            '',
            '   ',
            None,
            'manuscript.indd',
            'Final.doc',
            'untitled',
            'Microsoft Word',
            'NBRT_A01',
            'NBRT-A01',
            'A0123',
        ],
    )
    def test_junk_titles_are_rejected(self, title):
        assert junky(title) is True

    @pytest.mark.parametrize(
        'title',
        [
            'Atomic Habits',
            'Artemis',
            'On Liberty',
            'It',
            # All-caps books. Matching bare capitals was survivable while this
            # only meant "do not copy this onto the PDF twin"; it stopped being
            # survivable when the same question began deciding whether to
            # overwrite a title.
            'DUNE',
            'IT',
            'THE ILLUSTRATED MAN',
            '1984',  # all digits is a year, not a production code
            'V2',  # too short to be one
        ],
    )
    def test_real_titles_are_kept(self, title):
        assert junky(title) is False

    def test_empty_is_junk_even_though_no_regex_matches_it(self):
        """The regex constants the original carried alongside this function did
        not match an empty string, so replacing the function with them would have
        silently broken the PDF-with-no-title case."""
        assert junky('') is True

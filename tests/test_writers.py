"""The native writers, on files built in the test so nothing real is committed.

What matters: an EPUB keeps every other member byte for byte with mimetype first
and stored, a PDF gains an incremental section rather than a rewrite, and both
read back through the tool's own readers with exactly the gains added.
"""

import os
import zipfile

import pytest
from pypdf import PdfReader, PdfWriter

from ebook_metamend import calibre
from ebook_metamend.writers import epub, pdf

OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="{version}" unique-identifier="i">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>Example Title</dc:title>
    <dc:creator opf:role="aut">Example Author</dc:creator>
    <dc:identifier id="i">urn:uuid:0000</dc:identifier>
    <dc:language>en</dc:language>
  </metadata>
  <manifest><item id="t" href="text.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="t"/></spine>
</package>
"""

GAINS = {
    'tags': ['Woodworking', 'Angelou, Maya, 1928-2014'],
    'description': 'A year at the bench.',
    'publisher': 'Hollow Beech Press',
    'isbn': '9781940000012',
    'series': 'The Emberwake Cycle',
}


def make_epub(path, version='2.0'):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip', zipfile.ZIP_STORED)
        z.writestr(
            'META-INF/container.xml',
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>',
        )
        z.writestr('OEBPS/content.opf', OPF.format(version=version))
        z.writestr('OEBPS/text.xhtml', '<html><body>x</body></html>' * 50, zipfile.ZIP_DEFLATED)


def make_pdf(path):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_metadata({'/Title': 'Example Title', '/Author': 'Example Author'})
    with open(path, 'wb') as fh:
        writer.write(fh)


class TestEpubWriter:
    @pytest.mark.parametrize('version', ['2.0', '3.0'])
    def test_gains_read_back_and_nothing_else_moves(self, tmp_path, version):
        path = tmp_path / 'book.epub'
        make_epub(path, version)
        with zipfile.ZipFile(path) as z:
            before = [(i.filename, i.compress_type, i.CRC) for i in z.infolist()]

        ok, reason = epub.write(str(path), GAINS, {'sidx': '2'})
        assert (ok, reason) == (True, '')

        with zipfile.ZipFile(path) as z:
            after = [(i.filename, i.compress_type, i.CRC) for i in z.infolist()]
            assert z.testzip() is None
            opf_text = z.read('OEBPS/content.opf').decode()
        assert after[0][:2] == ('mimetype', zipfile.ZIP_STORED)
        assert [m for m in before if m[0] != 'OEBPS/content.opf'] == [
            m for m in after if m[0] != 'OEBPS/content.opf'
        ]
        # Prefixes survive: dc: stays dc:, not ns0:.
        assert '<dc:subject>' in opf_text and 'ns0:' not in opf_text

        record = calibre.read_epub_metadata(str(path))
        assert record['title'] == 'Example Title'
        assert record['authors'] == ['Example Author']
        assert record['tags'] == GAINS['tags']
        assert record['description'] == GAINS['description']
        assert record['publisher'] == GAINS['publisher']
        assert record['isbn'] == GAINS['isbn']
        assert (record['series'], record['sidx']) == (GAINS['series'], '2')

    def test_isbn_takes_the_form_of_the_epub_version(self, tmp_path):
        two = epub.edit(OPF.format(version='2.0'), {'isbn': '1'}, {})
        three = epub.edit(OPF.format(version='3.0'), {'isbn': '1'}, {})
        assert 'opf:scheme="ISBN">1<' in two
        assert '>urn:isbn:1<' in three

    def test_a_comma_in_a_tag_survives(self, tmp_path):
        """The reason Calibre could not be used for this: it split every tag on
        commas, so a Library of Congress heading came apart."""
        path = tmp_path / 'book.epub'
        make_epub(path)
        epub.write(str(path), {'tags': ['Angelou, Maya, 1928-2014']}, {})
        assert calibre.read_epub_metadata(str(path))['tags'] == ['Angelou, Maya, 1928-2014']

    def test_no_gains_touches_nothing(self, tmp_path):
        path = tmp_path / 'book.epub'
        make_epub(path)
        before = path.read_bytes()
        assert epub.write(str(path), {}, {}) == (True, '')
        assert path.read_bytes() == before

    def test_the_file_keeps_its_permissions(self, tmp_path):
        path = tmp_path / 'book.epub'
        make_epub(path)
        os.chmod(path, 0o664)
        assert epub.write(str(path), {'publisher': 'P'}, {}) == (True, '')
        assert oct(path.stat().st_mode & 0o777) == oct(0o664)

    def test_a_broken_archive_is_reported_not_replaced(self, tmp_path):
        path = tmp_path / 'book.epub'
        path.write_bytes(b'not a zip')
        ok, reason = epub.write(str(path), GAINS, {})
        assert not ok and reason
        assert path.read_bytes() == b'not a zip'
        assert list(tmp_path.iterdir()) == [path]


class TestPdfWriter:
    def test_gains_are_appended_and_read_back(self, tmp_path):
        path = tmp_path / 'book.pdf'
        make_pdf(path)
        original = path.read_bytes()

        ok, reason = pdf.write(str(path), GAINS, {'sidx': '2'})
        assert (ok, reason) == (True, '')
        # Incremental: the original bytes are a prefix of the new file.
        assert path.read_bytes().startswith(original)
        assert len(PdfReader(str(path)).pages) == 1

        record = pdf.read(str(path))
        assert record['title'] == 'Example Title'
        assert record['authors'] == ['Example Author']
        assert record['tags'] == GAINS['tags']
        assert record['description'] == GAINS['description']
        assert record['publisher'] == GAINS['publisher']
        assert record['isbn'] == GAINS['isbn']
        assert (record['series'], record['sidx']) == (GAINS['series'], '2')

    def test_title_and_tags_also_land_in_the_info_dictionary(self, tmp_path):
        """Plain PDF readers never look at XMP."""
        path = tmp_path / 'book.pdf'
        make_pdf(path)
        pdf.write(str(path), {'title': 'Better Title', 'tags': ['a', 'b']}, {})
        info = PdfReader(str(path)).metadata
        assert info['/Title'] == 'Better Title'
        assert info['/Keywords'] == 'a, b'

    def test_a_comma_in_a_tag_survives_through_xmp(self, tmp_path):
        """/Keywords is one comma-joined string by convention, so the list
        form in XMP is what keeps a Library of Congress heading whole."""
        path = tmp_path / 'book.pdf'
        make_pdf(path)
        pdf.write(str(path), {'tags': ['Angelou, Maya, 1928-2014', 'Poets']}, {})
        assert pdf.read(str(path))['tags'] == ['Angelou, Maya, 1928-2014', 'Poets']

    def test_reads_the_info_dictionary_when_there_is_no_xmp(self, tmp_path):
        path = tmp_path / 'book.pdf'
        make_pdf(path)
        record = pdf.read(str(path))
        assert record['title'] == 'Example Title'
        assert record['authors'] == ['Example Author']
        assert record['isbn'] == '' and record['series'] is None

    def test_a_file_pypdf_cannot_append_to_gets_a_full_rewrite(self, tmp_path, monkeypatch):
        """One corpus file has a cross-reference chain pypdf refuses to extend;
        that file is 52 MB and real, so the refusal is staged here instead."""
        path = tmp_path / 'book.pdf'
        make_pdf(path)
        real = pdf.PdfWriter

        def refuse_incremental(*args, **kwargs):
            if kwargs.get('incremental'):
                raise pdf.PdfReadError('staged: cannot follow the xref chain')
            return real(*args, **kwargs)

        monkeypatch.setattr(pdf, 'PdfWriter', refuse_incremental)
        ok, reason = pdf.write(str(path), {'publisher': 'P'}, {})
        assert (ok, reason) == (True, 'rewritten')
        assert pdf.read(str(path))['publisher'] == 'P'
        assert len(PdfReader(str(path)).pages) == 1

    def test_a_file_pypdf_cannot_open_at_all_is_reported_not_raised(self, tmp_path, monkeypatch):
        """One bad book must not abort the run for the rest."""
        path = tmp_path / 'book.pdf'
        make_pdf(path)
        before = path.read_bytes()

        def refuse(*args, **kwargs):
            raise pdf.PdfReadError('staged: unreadable either way')

        monkeypatch.setattr(pdf, 'PdfWriter', refuse)
        ok, reason = pdf.write(str(path), {'publisher': 'P'}, {})
        assert ok is False and 'PdfReadError' in reason
        assert path.read_bytes() == before
        assert list(tmp_path.iterdir()) == [path]

    def test_a_second_isbn_replaces_the_first(self, tmp_path):
        """read() takes the first isbn entry; a stale one in front would make
        the write report success while the book still says the old number."""
        path = tmp_path / 'book.pdf'
        make_pdf(path)
        pdf.write(str(path), {'isbn': '9781940000012'}, {})
        pdf.write(str(path), {'isbn': '9781940000029'}, {})
        assert pdf.read(str(path))['isbn'] == '9781940000029'

    def test_the_file_keeps_its_permissions(self, tmp_path):
        """mkstemp creates 0600, which would lock other users out of a shared book."""
        path = tmp_path / 'book.pdf'
        make_pdf(path)
        os.chmod(path, 0o664)
        assert pdf.write(str(path), {'publisher': 'P'}, {}) == (True, '')
        assert oct(path.stat().st_mode & 0o777) == oct(0o664)

    def test_an_unreadable_file_is_none_not_empty(self, tmp_path):
        path = tmp_path / 'book.pdf'
        path.write_bytes(b'%PDF-1.4 garbage')
        assert pdf.read(str(path)) is None

    def test_no_gains_touches_nothing(self, tmp_path):
        path = tmp_path / 'book.pdf'
        make_pdf(path)
        before = path.read_bytes()
        assert pdf.write(str(path), {}, {}) == (True, '')
        assert path.read_bytes() == before


class TestReadRouting:
    def test_pdfs_are_read_without_calibre(self, tmp_path, monkeypatch):
        path = tmp_path / 'book.pdf'
        make_pdf(path)
        monkeypatch.setattr(calibre, 'FETCH_METADATA', '/nonexistent')
        assert calibre.read_book_metadata(str(path))['title'] == 'Example Title'

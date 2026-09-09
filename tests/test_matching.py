"""The safety model: title similarity and the confidence decision.

If ``sim`` starts scoring a wrong book above the threshold, a bulk ``--apply``
run silently rewrites a library. These functions are pure, so this suite needs no
network, no Calibre and no ebook files.
"""

import pytest

from ebook_metamend.matching import (
    ADAPTATION_SCORE,
    AUTHOR_STRONG,
    CONTAINED_SCORE,
    PREFIX_SCORE,
    TITLE_STRONG,
    TITLE_WEAK,
    SourceScore,
    best_author_score,
    classify,
    looks_derived,
    norm,
    sim,
)


def source(name, title, title_score, author_score):
    return SourceScore(name=name, title=title, title_score=title_score, author_score=author_score)


class TestNorm:
    @pytest.mark.parametrize(
        ('raw', 'expected'),
        [
            ('The Alchemist', 'alchemist'),
            ('A Game of Thrones', 'game of thrones'),
            ('Black & White', 'black and white'),
            ('10% Happier', '10 percent happier'),
            (
                # Only the *leading* article goes. Stripping them everywhere made
                # "Vitamin A Deficiency" and "Vitamin Deficiency" identical.
                'Digital Minimalism: Choosing a Focused Life',
                'digital minimalism choosing a focused life',
            ),
            ('Vitamin A Deficiency', 'vitamin a deficiency'),
            ('  Messy   Spacing  ', 'messy spacing'),
            ('', ''),
            (None, ''),
        ],
    )
    def test_normalises(self, raw, expected):
        assert norm(raw) == expected


class TestSim:
    def test_identical_titles_score_one(self):
        assert sim('Atomic Habits', 'Atomic Habits') == 1.0

    def test_ignores_case_and_punctuation(self):
        assert sim('The Alchemist', 'the alchemist!') == 1.0

    def test_percent_and_ampersand_are_spelled_out(self):
        assert sim('10% Happier', '10 Percent Happier') == 1.0

    def test_empty_input_scores_zero(self):
        assert sim('', 'Atomic Habits') == 0.0
        assert sim('Atomic Habits', '') == 0.0

    def test_unrelated_titles_score_below_the_weak_threshold(self):
        assert sim('Atomic Habits', 'War and Peace') < TITLE_WEAK

    @pytest.mark.parametrize(
        ('short', 'full'),
        [
            ('Digital Minimalism', 'Digital Minimalism: Choosing a Focused Life in a Noisy World'),
            ('Bad Blood', 'Bad Blood: Secrets and Lies in a Silicon Valley Startup'),
        ],
    )
    def test_subtitle_is_the_same_book(self, short, full):
        assert sim(short, full) == PREFIX_SCORE
        assert sim(full, short) == PREFIX_SCORE, 'scoring must not depend on argument order'

    def test_omnibus_does_not_match_the_volume_it_merely_contains(self):
        """The case the cap exists for.

        An omnibus contains the title of a book it is not. Plain containment would
        score it high enough to overwrite the single volume's metadata.
        """
        volume = 'The Happiest Toddler on the Block'
        omnibus = 'The Happiest Baby on the Block and The Happiest Toddler on the Block'

        assert sim(volume, omnibus) == CONTAINED_SCORE
        assert sim(volume, omnibus) < TITLE_STRONG, 'must stay below the writing threshold'

    def test_prefix_outranks_mere_containment(self):
        subtitle = sim('Digital Minimalism', 'Digital Minimalism: Choosing a Focused Life')
        omnibus = sim(
            'The Happiest Toddler on the Block',
            'The Happiest Baby on the Block and The Happiest Toddler on the Block',
        )
        assert subtitle > omnibus


class TestBestScores:
    def test_the_best_of_one_source_s_authors_wins(self):
        assert best_author_score(['Nobody', 'James Clear'], 'James Clear') == 1.0

    def test_no_authors_scores_zero(self):
        assert best_author_score([], 'James Clear') == 0.0

    def test_a_bare_surname_is_not_a_full_author_match(self):
        """sim() scores authors too, so containment must stay strictly below the
        author threshold or "Smith" would vouch for "Zadie Smith"."""
        from ebook_metamend.matching import AUTHOR_STRONG

        assert best_author_score(['Smith'], 'Zadie Smith') < AUTHOR_STRONG


class TestDerivedWorks:
    """Adaptations are real books that share a title. Writing their title over
    the original is a failure this library has already suffered."""

    @pytest.mark.parametrize(
        'title',
        [
            'On Liberty (Squashed Edition)',
            'Atomic Habits (Tamil)',
            'The Alchemist Graphic Novel',
            "Man's Search for Meaning adapted for Young Adults",
            'Summary of Atomic Habits',
            'Atomic Habits Workbook',
            'The Expanse Boxed Set',
            'Abridged Edition',
        ],
    )
    def test_derived_titles_are_recognised(self, title):
        assert looks_derived(title) is True

    @pytest.mark.parametrize(
        'title',
        ['On Liberty', 'Atomic Habits', 'The Alchemist', 'Bad Blood', 'A Study in Scarlet'],
    )
    def test_real_titles_are_not(self, title):
        assert looks_derived(title) is False

    @pytest.mark.parametrize(
        ('filename', 'returned'),
        [
            ('On Liberty', 'On Liberty (Squashed Edition)'),
            ('Atomic Habits', 'Atomic Habits (Tamil)'),
            ("Man's Search for Meaning", "Man's Search for Meaning adapted for Young Adults"),
        ],
    )
    def test_an_adaptation_cannot_score_high_enough_to_be_written(self, filename, returned):
        """Every one of these was returned by a live source for this exact
        filename, and each would have overwritten the correct title."""
        assert sim(filename, returned) == ADAPTATION_SCORE
        assert sim(filename, returned) < TITLE_STRONG

    def test_two_adaptations_of_the_same_kind_still_compare_normally(self):
        assert sim('Atomic Habits (Tamil)', 'Atomic Habits (Tamil)') == 1.0


class TestClassify:
    def test_two_agreeing_strong_sources_are_high(self):
        scores = [
            source('kobo', 'Atomic Habits', 1.0, 1.0),
            source('google', 'Atomic Habits', 1.0, 1.0),
        ]
        assert classify(scores) == 'HIGH'

    def test_one_strong_source_is_only_med(self):
        """The rule that matters. A lone source returned an abridgement, a
        translation and a different book on a real run; each would have been
        written under the old rule."""
        assert classify([source('google', 'Atomic Habits', 1.0, 1.0)]) == 'MED'

    def test_title_and_author_from_different_sources_do_not_combine(self):
        """Neither source identified the book, but the old best-of maxima made it
        look like one had."""
        scores = [
            source('kobo', 'Atomic Habits', 1.0, 0.0),
            source('google', 'Something Else', 0.0, 1.0),
        ]
        assert classify(scores) == 'LOW'

    def test_two_strong_sources_that_disagree_are_not_high(self):
        scores = [
            source('kobo', 'Atomic Habits', 1.0, 1.0),
            source('google', 'War and Peace', 0.9, 0.9),
        ]
        assert classify(scores) == 'MED'

    def test_weak_title_with_strong_author_is_med(self):
        assert classify([source('a', 'x', TITLE_WEAK, AUTHOR_STRONG)]) == 'MED'

    def test_nothing_matching_is_low(self):
        assert classify([source('a', 'x', 0.1, 0.1)]) == 'LOW'

    def test_no_sources_at_all_is_low(self):
        assert classify([]) == 'LOW'

    def test_an_omnibus_cannot_reach_high_even_with_two_sources(self):
        scores = [
            source('kobo', 'Baby and Toddler Omnibus', CONTAINED_SCORE, 1.0),
            source('google', 'Baby and Toddler Omnibus', CONTAINED_SCORE, 1.0),
        ]
        assert classify(scores) != 'HIGH'

    def test_an_adaptation_cannot_reach_high_even_with_two_sources(self):
        scores = [
            source('kobo', 'On Liberty (Squashed Edition)', ADAPTATION_SCORE, 1.0),
            source('google', 'On Liberty (Squashed Edition)', ADAPTATION_SCORE, 1.0),
        ]
        assert classify(scores) != 'HIGH'

    def test_prefix_matches_still_reach_high(self):
        """A subtitle is not an adaptation, and must not be penalised."""
        scores = [
            source('kobo', 'Bad Blood: Secrets and Lies', PREFIX_SCORE, 1.0),
            source('google', 'Bad Blood: Secrets and Lies', PREFIX_SCORE, 1.0),
        ]
        assert classify(scores) == 'HIGH'


class TestEditionMarkersInEveryFormPublishersUse:
    """The bracketed form was the only one recognised, so the two commonest
    forms scored a clean 0.95 prefix match and would have been written."""

    @pytest.mark.parametrize(
        'title',
        [
            'Atomic Habits (Tamil Edition)',
            'Atomic Habits [Tamil Edition]',
            'Atomic Habits, Tamil Edition',
            'Atomic Habits: Tamil Edition',
            'Atomic Habits - Tamil Edition',
            "Harry Potter and the Sorcerer's Stone: Illustrated Edition",
            'Sapiens: A Graphic History',
            'The Hobbit (Illustrated)',
        ],
    )
    def test_a_derived_title_is_recognised(self, title):
        assert looks_derived(title)

    @pytest.mark.parametrize(
        'title',
        [
            'The Second Edition',
            'Atomic Habits',
            'Bad Blood: Secrets and Lies in a Silicon Valley Startup',
            'The Editions of Shakespeare',
            # A real Bradbury novel. An unanchored 'illustrated' marked it as a
            # derived work, which would have made the book unenrichable.
            'The Illustrated Man',
            'The Illustrated History of Rome',
        ],
    )
    def test_an_ordinary_title_is_not(self, title):
        assert not looks_derived(title)

    def test_the_same_marker_in_different_brackets_compares_equal(self):
        """The brackets are part of the regex match. Keeping them meant one
        source's "(Tamil Edition)" and another's "[Tamil Edition]" read as two
        different markers, so two sources naming the same translation were
        capped against each other and could never agree."""
        assert sim('Atomic Habits (Tamil Edition)', 'Atomic Habits [Tamil Edition]') == 1.0

    def test_the_colon_form_is_capped_below_the_reporting_floor(self):
        assert sim('Atomic Habits', 'Atomic Habits: Tamil Edition') <= ADAPTATION_SCORE


class TestTwoDerivedTitlesAreNotAutomaticallyTheSameBook:
    def test_derived_the_same_way_compares_normally(self):
        assert sim('Dune (Deluxe Edition)', 'Dune (Deluxe Edition)') == 1.0

    def test_derived_differently_is_still_capped(self):
        """An XOR on two booleans saw both-derived as a matched pair and applied
        no penalty, so an abridgement of an annotated edition scored 0.95."""
        got = sim('Ulysses (Annotated Edition)', 'Ulysses (Annotated Edition, Abridged)')
        assert got <= ADAPTATION_SCORE


class TestContainmentIsWholeWords:
    def test_a_word_prefix_is_not_a_title_prefix(self):
        """'It' sits inside 'Italian Cooking' as characters, not as a word."""
        assert sim('It', 'Italian Cooking') < TITLE_WEAK

    def test_a_real_subtitle_still_scores_as_a_prefix(self):
        assert sim('Digital Minimalism', 'Digital Minimalism: Choosing a Focused Life') == (
            PREFIX_SCORE
        )


class TestForANameTheDirectionCarriesTheMeaning:
    """A source name that extends the filename's is the same person written more
    fully. One that shortens it is under-specified and could be anyone, and it
    used to score 0.95 and clear AUTHOR_STRONG on its own."""

    @pytest.mark.parametrize(
        'source_author',
        [
            'Zadie',  # a bare given name
            'Ann Rice',  # a name the filename hyphenates further
            'Harari',  # a bare surname
        ],
    )
    def test_a_shortened_author_cannot_vouch_for_the_full_one(self, source_author):
        assert best_author_score([source_author], 'Zadie Smith') < AUTHOR_STRONG or True
        assert (
            best_author_score(
                [source_author],
                {
                    'Zadie': 'Zadie Smith',
                    'Ann Rice': 'Ann Rice-Smith',
                    'Harari': 'Yuval Noah Harari',
                }[source_author],
            )
            < AUTHOR_STRONG
        )

    @pytest.mark.parametrize(
        ('source_author', 'filename_author'),
        [
            # Both were returned verbatim by live sources for this library.
            ('Harvey Karp, M. D.', 'Harvey Karp'),
            ('Harvey Karp M. D.', 'Harvey Karp'),
            ('Malcolm T. Gladwell', 'Malcolm Gladwell'),
            ('Viktor E. Frankl', 'Viktor Frankl'),
        ],
    )
    def test_a_fuller_form_of_the_same_person_still_matches(self, source_author, filename_author):
        assert best_author_score([source_author], filename_author) >= AUTHOR_STRONG

    def test_an_initial_is_not_a_surname(self):
        """Google answered "John C." for Bad Blood. The title was exact, so this
        was the only thing standing between a guess and a HIGH write."""
        assert best_author_score(['John C.'], 'John Carreyrou') < AUTHOR_STRONG

    def test_an_exact_author_is_unaffected(self):
        assert best_author_score(['James Clear'], 'James Clear') == 1.0

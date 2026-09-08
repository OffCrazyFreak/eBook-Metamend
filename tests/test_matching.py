"""The safety model: title similarity and the confidence decision.

If ``sim`` starts scoring a wrong book above the threshold, a bulk ``--apply``
run silently rewrites a library. These functions are pure, so this suite needs no
network, no Calibre and no ebook files.
"""

import pytest

from ebook_metamend.matching import (
    AUTHOR_STRONG,
    CONTAINED_SCORE,
    PREFIX_SCORE,
    TITLE_STRONG,
    TITLE_WEAK,
    best_author_score,
    best_title_score,
    classify,
    count_agreements,
    norm,
    sim,
)


class TestNorm:
    @pytest.mark.parametrize(
        ('raw', 'expected'),
        [
            ('The Alchemist', 'alchemist'),
            ('A Game of Thrones', 'game of thrones'),
            ('Black & White', 'black and white'),
            ('10% Happier', '10 percent happier'),
            (
                'Digital Minimalism: Choosing a Focused Life',
                'digital minimalism choosing focused life',
            ),
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
    def test_best_title_takes_the_strongest_source(self):
        assert best_title_score(['Wrong Book', 'Atomic Habits'], 'Atomic Habits') == 1.0

    def test_no_sources_scores_zero(self):
        assert best_title_score([], 'Atomic Habits') == 0.0
        assert best_author_score([], 'James Clear') == 0.0

    def test_best_author_searches_within_each_source(self):
        assert best_author_score([['Nobody', 'James Clear']], 'James Clear') == 1.0

    def test_empty_author_list_is_not_a_match(self):
        assert best_author_score([[]], 'James Clear') == 0.0


class TestAgreements:
    def test_counts_pairs_not_sources(self):
        assert count_agreements(['Atomic Habits', 'Atomic Habits', 'Atomic Habits']) == 3

    def test_disagreeing_sources_do_not_count(self):
        assert count_agreements(['Atomic Habits', 'War and Peace']) == 0

    def test_single_source_cannot_agree_with_itself(self):
        assert count_agreements(['Atomic Habits']) == 0


class TestClassify:
    def test_title_and_author_both_strong_is_high(self):
        assert classify(1.0, 1.0, 0) == 'HIGH'

    def test_high_needs_both_signals(self):
        assert classify(1.0, 0.0, 0) == 'MED', 'a perfect title with a wrong author is not enough'
        assert classify(0.0, 1.0, 0) == 'LOW'

    def test_cross_source_agreement_alone_never_reaches_high(self):
        """Two sources can be wrong together, so agreement with the filename is
        the stronger signal. This is the rule the old docstring got backwards."""
        assert classify(0.0, AUTHOR_STRONG, 5) == 'MED'

    def test_weak_title_with_strong_author_is_med(self):
        assert classify(TITLE_WEAK, AUTHOR_STRONG, 0) == 'MED'

    def test_nothing_matching_is_low(self):
        assert classify(0.1, 0.1, 0) == 'LOW'

    def test_thresholds_are_inclusive(self):
        assert classify(TITLE_STRONG, AUTHOR_STRONG, 0) == 'HIGH'
        assert classify(TITLE_STRONG - 0.01, AUTHOR_STRONG, 0) == 'MED'

    def test_the_omnibus_score_cannot_be_written(self):
        """End to end: the containment cap keeps an omnibus out of HIGH even when
        the author matches perfectly, which is the realistic failure."""
        assert classify(CONTAINED_SCORE, 1.0, 0) != 'HIGH'

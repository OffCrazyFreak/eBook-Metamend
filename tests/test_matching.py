"""Tests for the title matching that decides whether metadata is safe to write.

These two functions are the whole safety model. If `sim` starts scoring a wrong
book above the threshold, a bulk `--apply` run silently rewrites a library. They
are pure, so this suite needs no network, no Calibre and no ebook files.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

# The module is named `2_online_enrich.py`, and a name starting with a digit
# cannot be used with `import`. Load it by path instead.
_spec = importlib.util.spec_from_file_location(
    'online_enrich', Path(__file__).resolve().parent.parent / '2_online_enrich.py'
)
online_enrich = importlib.util.module_from_spec(_spec)
_argv, sys.argv = sys.argv, ['test']
_spec.loader.exec_module(online_enrich)
sys.argv = _argv

norm = online_enrich.norm
sim = online_enrich.sim


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

    def test_unrelated_titles_score_below_the_apply_threshold(self):
        assert sim('Atomic Habits', 'War and Peace') < 0.60

    @pytest.mark.parametrize(
        ('short', 'full'),
        [
            ('Digital Minimalism', 'Digital Minimalism: Choosing a Focused Life in a Noisy World'),
            ('Bad Blood', 'Bad Blood: Secrets and Lies in a Silicon Valley Startup'),
        ],
    )
    def test_subtitle_is_the_same_book(self, short, full):
        """A filename holding only the main title must still match the full title."""
        assert sim(short, full) == 0.95
        assert sim(full, short) == 0.95, 'scoring must not depend on argument order'

    def test_omnibus_does_not_match_the_volume_it_merely_contains(self):
        """The case this cap exists for.

        An omnibus contains the title of a book it is not. Plain containment
        would score it high enough to overwrite the single volume's metadata, so
        non-prefix containment is capped below the threshold that would apply it.
        """
        volume = 'The Happiest Toddler on the Block'
        omnibus = 'The Happiest Baby on the Block and The Happiest Toddler on the Block'

        assert sim(volume, omnibus) == 0.70
        assert sim(volume, omnibus) < 0.85, 'must stay below the HIGH-confidence threshold'

    def test_prefix_outranks_mere_containment(self):
        """A real subtitle must always score above a suspicious omnibus."""
        subtitle = sim('Digital Minimalism', 'Digital Minimalism: Choosing a Focused Life')
        omnibus = sim(
            'The Happiest Toddler on the Block',
            'The Happiest Baby on the Block and The Happiest Toddler on the Block',
        )
        assert subtitle > omnibus

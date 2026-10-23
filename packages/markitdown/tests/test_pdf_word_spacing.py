"""Guarded pdfplumber ``x_tolerance_ratio`` word spacing (GIA fork)."""

import os

import pdfplumber
import pytest

from markitdown import MarkItDown
from markitdown.converters._pdf_converter import (
    X_TOLERANCE_RATIO,
    _SpacedPage,
    _single_letter_share,
)

TEST_FILES = os.path.join(os.path.dirname(__file__), "test_files")


def _first_page(name: str, number: int = 0):
    pdf = pdfplumber.open(os.path.join(TEST_FILES, name))
    return pdf, pdf.pages[number]


# --- _single_letter_share ----------------------------------------------------


def test_single_letter_share_values():
    assert _single_letter_share("") == 0.0
    assert _single_letter_share("  \n ... ") == 0.0
    assert _single_letter_share("hello world") == 0.0
    assert _single_letter_share("a b cd ef") == 0.5
    assert _single_letter_share("L a g e s t i o n") == 1.0


def test_single_letter_share_counts_accents_and_digits():
    assert _single_letter_share("é à 7 mot") == 0.75


# --- the three page cases: glued, clean, spread ------------------------------


def test_glued_page_uses_ratio_and_restores_spaces():
    # test.pdf: small font, pdfplumber's default 3pt tolerance glues the words.
    pdf, page = _first_page("test.pdf")
    with pdf:
        default = page.extract_text()
        spaced = _SpacedPage(page)
        assert spaced.use_ratio and not spaced.fallback
        text = spaced.extract_text()
    assert "Large language models" in text
    assert "Largelanguagemodels" not in text
    assert len(text.split()) > 1.5 * len(default.split())


def test_clean_page_is_not_degraded():
    pdf, page = _first_page("RECEIPT-2024-TXN-98765_retail_purchase.pdf")
    with pdf:
        default = page.extract_text()
        spaced = _SpacedPage(page)
        assert not spaced.fallback
        # Same words: the ratio must not split or glue a page that was fine.
        assert spaced.extract_text().split() == default.split()


def test_spread_page_falls_back_to_default_spacing():
    # Letter-spaced / expanded font: the ratio splits words into single letters.
    pdf, page = _first_page("expanded_font_spacing.pdf")
    with pdf:
        default = page.extract_text()
        ratio = page.extract_text(x_tolerance_ratio=X_TOLERANCE_RATIO)
        assert _single_letter_share(ratio) > 0.35
        assert _single_letter_share(default) < 0.20
        spaced = _SpacedPage(page)
        assert spaced.fallback and not spaced.use_ratio
        assert spaced.extract_text() == default
        assert "La gestion des heures" in spaced.extract_text()


def test_spread_page_extract_words_keeps_default_tolerance():
    pdf, page = _first_page("expanded_font_spacing.pdf")
    with pdf:
        spaced = _SpacedPage(page)
        assert spaced.fallback
        assert spaced.extract_words(x_tolerance=3) == page.extract_words(
            x_tolerance=3
        )


def test_glued_page_extract_words_uses_ratio():
    pdf, page = _first_page("test.pdf")
    with pdf:
        default_words = page.extract_words(x_tolerance=3)
        words = _SpacedPage(page).extract_words(x_tolerance=3)
        assert len(words) > 1.5 * len(default_words)
        # Callers without x_tolerance are left untouched.
        assert _SpacedPage(page).extract_words() == page.extract_words()


def test_spaced_page_delegates_other_attributes():
    pdf, page = _first_page("test.pdf")
    with pdf:
        spaced = _SpacedPage(page)
        assert spaced.width == page.width
        assert spaced.page_number == page.page_number


# --- robustness ---------------------------------------------------------------


class _FakePage:
    def __init__(self, text, ratio_text=None, supports_ratio=True):
        self._text = text
        self._ratio_text = ratio_text
        self._supports_ratio = supports_ratio

    def extract_text(self, **kwargs):
        if "x_tolerance_ratio" in kwargs:
            if not self._supports_ratio:
                raise TypeError("unexpected keyword argument")
            return self._ratio_text
        return self._text


def test_blank_page_keeps_default_without_second_extraction():
    page = _FakePage("   ", ratio_text="should not be used")
    spaced = _SpacedPage(page)
    assert not spaced.use_ratio and not spaced.fallback
    assert spaced.extract_text() == "   "


def test_pdfplumber_without_ratio_support_keeps_default():
    page = _FakePage("hello world", supports_ratio=False)
    spaced = _SpacedPage(page)
    assert not spaced.use_ratio
    assert spaced.extract_text() == "hello world"


def test_guard_thresholds():
    letters = "a b c d e f g h"
    words = "alpha beta gamma delta"
    # ratio splits, default fine -> fallback
    assert _SpacedPage(_FakePage(words, letters)).fallback
    # both already spread (genuine one-letter text) -> keep ratio
    both = _SpacedPage(_FakePage(letters, letters))
    assert both.use_ratio and not both.fallback
    # ratio fine -> keep ratio
    ok = _SpacedPage(_FakePage("alphabeta gamma", "alpha beta gamma"))
    assert ok.use_ratio and ok.extract_text() == "alpha beta gamma"


# --- converter level -----------------------------------------------------------


def test_converter_plain_pages_of_mixed_pdf_are_not_glued():
    """Pages next to form pages go through pdfplumber: words must keep spaces."""
    markdown = MarkItDown().convert(
        os.path.join(TEST_FILES, "pdf_cleanup_mixed.pdf")
    ).markdown
    assert "Large language models (LLMs) are becoming" in markdown
    assert "Largelanguagemodels" not in markdown

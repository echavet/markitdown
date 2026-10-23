"""Regression tests for the GIA fork patches (progress_callback, PDF vision)."""

import io
import os
from types import SimpleNamespace

import pytest

from markitdown import ConversionProgress, MarkItDown

TEST_FILES = os.path.join(os.path.dirname(__file__), "test_files")


def _collect(path: str, **kwargs):
    events: list[ConversionProgress] = []
    MarkItDown().convert(
        os.path.join(TEST_FILES, path), progress_callback=events.append, **kwargs
    )
    return events


@pytest.mark.parametrize(
    "filename,unit,source",
    [
        ("test.pptx", "slide", "PptxConverter"),
        ("test.xlsx", "sheet", "XlsxConverter"),
        ("test.epub", "chapter", "EpubConverter"),
        ("test.pdf", "page", "PdfConverter"),
    ],
)
def test_progress_callback_reports_units(filename, unit, source):
    events = _collect(filename)
    assert events, f"no progress event for {filename}"
    assert all(e.unit == unit and e.source == source for e in events)
    assert events[-1].current == events[-1].total
    assert [e.current for e in events] == list(range(1, len(events) + 1))


def _image_only_pdf() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (300, 300), "white").save(buf, format="PDF")
    return buf.getvalue()


class _FakeLLM:
    def __init__(self, text="Page description"):
        self.calls = 0
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )
        self._text = text

    def _create(self, **_kwargs):
        self.calls += 1
        message = SimpleNamespace(content=self._text)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_image_only_pdf_page_is_described_by_vision_llm():
    llm = _FakeLLM("VISION-DESCRIPTION")
    result = MarkItDown(llm_client=llm, llm_model="fake").convert_stream(
        io.BytesIO(_image_only_pdf()), file_extension=".pdf"
    )
    assert llm.calls == 1
    assert "VISION-DESCRIPTION" in result.markdown


def test_image_only_pdf_without_llm_is_not_described():
    result = MarkItDown().convert_stream(
        io.BytesIO(_image_only_pdf()), file_extension=".pdf"
    )
    assert "VISION-DESCRIPTION" not in result.markdown


def test_text_pdf_with_llm_keeps_pdfminer_spacing():
    """A text PDF must not be sent to the LLM nor lose pdfminer word spacing."""
    llm = _FakeLLM()
    path = os.path.join(TEST_FILES, "test.pdf")
    plain = MarkItDown().convert(path).markdown
    with_llm = MarkItDown(llm_client=llm, llm_model="fake").convert(path).markdown
    assert llm.calls == 0
    assert with_llm == plain
    assert "Large language models" in plain  # pdfminer spacing, not glued words


def test_notebook_with_non_ascii_bytes_does_not_crash_accepts():
    data = ("é" * 20).encode("latin-1")
    # Must not raise UnicodeDecodeError while sniffing the stream
    try:
        MarkItDown().convert_stream(io.BytesIO(data), file_extension=".bin")
    except Exception as exc:  # unsupported format is fine, a decode crash is not
        assert not isinstance(exc, UnicodeDecodeError)

from ptp.config import Config
from ptp.devices import DeviceSelection
from ptp.translate import (
    TranslationService,
    _clean_translation,
    _protect,
    _restore,
    _segment_is_translatable,
    _split_protected,
    estimate_tokens,
    sanitize_text,
)


def _service_with_fake_translation() -> TranslationService:
    service = TranslationService(Config(), selection=DeviceSelection(mode="cpu"))

    def fake_complete(prompt: str, **kwargs) -> str:
        return "译文：" + prompt.split("\n---\n", 1)[-1]

    service.complete = fake_complete  # type: ignore[method-assign]
    return service


def _service_that_drops_placeholders() -> TranslationService:
    service = TranslationService(Config(), selection=DeviceSelection(mode="cpu"))

    def fake_complete(prompt: str, **kwargs) -> str:
        payload = prompt.split("\n---\n", 1)[-1]
        if "@@P" in payload:
            return "译文：占位符被丢弃"
        return "译文：" + payload

    service.complete = fake_complete  # type: ignore[method-assign]
    return service


def _service_that_echoes() -> TranslationService:
    service = TranslationService(Config(), selection=DeviceSelection(mode="cpu"))

    def fake_complete(prompt: str, **kwargs) -> str:
        return prompt.split("\n---\n", 1)[-1]

    service.complete = fake_complete  # type: ignore[method-assign]
    return service


def test_protect_restores_markdown_and_math():
    text = "See ![fig](images/a.jpg), $E=mc^2$, and [1]."
    protected, values = _protect(text)
    assert "images/a.jpg" not in protected
    assert "$E=mc^2$" not in protected
    assert "@@P0@@" in protected
    assert "⟦" not in protected
    restored = _restore("译文：" + protected, values)
    assert "![fig](images/a.jpg)" in restored
    assert "$E=mc^2$" in restored
    assert "[1]" in restored


def test_split_protected_keeps_original_spans():
    pieces = _split_protected("A $x$ B [2] C")
    assert [(piece, protected) for piece, protected in pieces] == [
        ("A ", False),
        ("$x$", True),
        (" B ", False),
        ("[2]", True),
        (" C", False),
    ]


def test_segment_filter_skips_units_and_identifiers():
    assert not _segment_is_translatable("cm")
    assert not _segment_is_translatable("K")
    assert not _segment_is_translatable("Ag-ETS-10")
    assert _segment_is_translatable("temperature")
    assert _segment_is_translatable("and see")


def test_placeholder_failure_falls_back_to_segments():
    service = _service_that_drops_placeholders()
    translated = service.translate_text("The energy is $E=mc^2$ and see [1].")
    assert "译文：The energy is" in translated
    assert "译文：and see" in translated
    assert "$E=mc^2$" in translated
    assert "[1]" in translated
    assert "@@P" not in translated
    assert service.fallback_counts["placeholder_retries"] == 1
    assert service.fallback_counts["segment_fallbacks"] == 1
    assert service.fallback_counts["segment_untranslated"] == 0


def test_short_label_without_chinese_is_kept_without_segment_fallback():
    service = _service_that_echoes()
    translated = service.translate_text("CrossMark")
    assert translated == "CrossMark"
    assert service.fallback_counts["no_cjk_kept"] == 1
    assert service.fallback_counts["segment_fallbacks"] == 0


def test_prose_without_chinese_uses_segment_fallback():
    service = _service_that_echoes()
    text = "The measured breakthrough curves of radon on the investigated zeolites."
    translated = service.translate_text(text)
    assert translated == text
    assert service.fallback_counts["no_cjk_fallbacks"] == 1
    assert service.fallback_counts["segment_fallbacks"] == 1
    assert service.fallback_counts["segment_untranslated"] == 1


def test_code_is_skipped_and_markdown_table_is_translated():
    service = _service_with_fake_translation()
    markdown = (
        "# Title\n\n```python\nprint('hello')\n```\n\n"
        "| Material | Density |\n|---|---|\n| 1 | 2 |\n"
    )
    translated = service.translate_markdown(markdown)
    assert "译文：# Title" in translated
    assert "print('hello')" in translated
    assert "| 译文：Material | 译文：Density |" in translated
    assert "|---|---|" in translated
    assert "| 1 | 2 |" in translated


def test_html_table_is_translated_without_breaking_tags():
    service = _service_with_fake_translation()
    markdown = (
        "<table><tr><th>Header</th><th>Value</th></tr>"
        "<tr><td>1.5</td><td>Measured</td></tr></table>"
    )
    translated = service.translate_markdown(markdown)
    assert "<table>" in translated
    assert "译文：Header" in translated
    assert "译文：Value" in translated
    assert "译文：Measured" in translated
    assert "1.5" in translated


def test_image_only_block_is_not_sent_to_model():
    service = _service_with_fake_translation()
    translated = service.translate_markdown("![](image/fig1.jpg)\n")
    assert translated.strip() == "![](image/fig1.jpg)"


def test_estimate_tokens_positive():
    assert estimate_tokens("hello world") >= 2
    assert estimate_tokens("中文测试") >= 4


def test_missing_caption_is_marked_in_chinese():
    service = _service_with_fake_translation()
    assert service.translate_caption("[no caption]") == "[无图注]"


def test_clean_translation_removes_model_separators():
    assert _clean_translation("---\n译文正文\n---") == "译文正文"


def test_sanitize_removes_pdf_control_characters():
    assert sanitize_text("Sato\x01, Iida") == "Sato, Iida"

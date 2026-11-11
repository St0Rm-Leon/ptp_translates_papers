from ptp.config import Config
from ptp.devices import DeviceSelection
from ptp.translate import (
    TranslationService,
    _clean_translation,
    _protect,
    _restore,
    estimate_tokens,
    sanitize_text,
)


def _service_with_fake_translation() -> TranslationService:
    service = TranslationService(Config(), selection=DeviceSelection(mode="cpu"))

    def fake_complete(prompt: str, **kwargs) -> str:
        return "译文：" + prompt.split("\n---\n", 1)[-1]

    service.complete = fake_complete  # type: ignore[method-assign]
    return service


def test_protect_restores_markdown_and_math():
    text = "See ![fig](images/a.jpg), $E=mc^2$, and [1]."
    protected, values = _protect(text)
    assert "images/a.jpg" not in protected
    assert "$E=mc^2$" not in protected
    restored = _restore("译文：" + protected, values)
    assert "![fig](images/a.jpg)" in restored
    assert "$E=mc^2$" in restored
    assert "[1]" in restored


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

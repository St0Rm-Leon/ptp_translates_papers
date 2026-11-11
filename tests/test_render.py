from pathlib import Path

from ptp import render
from ptp.config import RenderConfig
from ptp.render import _font_header


def test_font_header_uses_forward_slashes_and_bold(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    regular = fonts / "NotoSerifCJKsc-Regular.otf"
    bold = fonts / "NotoSerifCJKsc-Bold.otf"
    regular.write_text("", encoding="utf-8")
    bold.write_text("", encoding="utf-8")

    header = _font_header(
        RenderConfig(cjk_font_file=regular, cjk_font_bold_file=bold),
        tmp_path,
    )
    assert header is not None
    text = header.read_text(encoding="utf-8")
    assert "\\setCJKmainfont" in text
    assert "Path={" in text
    assert "BoldFont={NotoSerifCJKsc-Bold.otf}" in text
    assert fonts.as_posix() in text
    if str(fonts) != fonts.as_posix():
        assert str(fonts) not in text


def test_render_pdf_uses_utf8_text_subprocess(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        render, "resolve_tool", lambda name: f"{name}.exe" if name else None
    )

    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        output = Path(command[command.index("--output") + 1])
        output.write_bytes(b"%PDF-1.4\n")

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr(render.subprocess, "run", fake_run)
    markdown = tmp_path / "paper.md"
    markdown.write_text("# 标题\n", encoding="utf-8")
    output = tmp_path / "paper.pdf"

    render.render_pdf(markdown, output, RenderConfig(), tmp_path)

    kwargs = captured["kwargs"]
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"

"""Pandoc rendering stage."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from .compat import resolve_tool, subprocess_text_options
from .config import RenderConfig
from .markdown_tables import inline_html_to_latex_markdown

logger = logging.getLogger(__name__)


class RenderError(RuntimeError):
    """Pandoc or the PDF engine failed."""


def _normalized_markdown(markdown_path: Path, resource_dir: Path) -> Path:
    text = markdown_path.read_text(encoding="utf-8")
    normalized = inline_html_to_latex_markdown(text)
    if normalized == text:
        return markdown_path
    target = resource_dir / f"_{markdown_path.stem}_render.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(normalized, encoding="utf-8")
    return target


def _font_header(config: RenderConfig, resource_dir: Path) -> Path | None:
    """Write a LaTeX header that loads bundled font files directly.

    This keeps the portable Windows bundle independent of system font
    installation.  Paths use forward slashes because XeTeX on Windows accepts
    them and avoids backslash escaping in fontspec options.
    """
    font = config.cjk_font_file
    if font is None:
        return None
    font_dir = font.parent.as_posix()
    if not font_dir.endswith("/"):
        font_dir += "/"
    options = [f"Path={{{font_dir}}}"]
    if config.cjk_font_bold_file is not None:
        options.append(f"BoldFont={{{config.cjk_font_bold_file.name}}}")
    option_text = ",".join(options)
    header = (
        "\\usepackage{fontspec}\n"
        "\\usepackage{xeCJK}\n"
        f"\\setmainfont[{option_text}]{{{font.name}}}\n"
        f"\\setCJKmainfont[{option_text}]{{{font.name}}}\n"
    )
    target = resource_dir / "_ptp_fonts.tex"
    target.write_text(header, encoding="utf-8")
    return target


def render_pdf(
    markdown_path: Path, output_pdf: Path, config: RenderConfig, resource_dir: Path
) -> None:
    pandoc = resolve_tool(config.pandoc or "pandoc")
    if pandoc is None:
        raise RenderError(
            "pandoc not found; install Pandoc or set render.pandoc to pandoc.exe"
        )

    engine = config.engine
    engine_bin = config.xelatex if engine == "xelatex" else None
    engine_path = resolve_tool(engine_bin or engine)
    if engine_path is None:
        raise RenderError(
            f"PDF engine {engine!r} not found; install it or set render.xelatex"
        )

    cmd = [
        pandoc,
        str(_normalized_markdown(markdown_path, resource_dir)),
        "--from",
        "markdown+tex_math_dollars+raw_html+pipe_tables",
        "--to",
        "pdf",
        "--standalone",
        "--pdf-engine",
        engine_path,
        "--resource-path",
        str(resource_dir),
        "--output",
        str(output_pdf),
    ]
    if config.template is not None:
        cmd.extend(["--template", str(config.template)])
    if engine in {"xelatex", "lualatex"}:
        cmd.extend(["--pdf-engine-opt=-halt-on-error", "--pdf-engine-opt=-file-line-error"])
    if config.cjk_font_file is not None and engine in {"xelatex", "lualatex"}:
        header = _font_header(config, resource_dir)
        if header is not None:
            cmd.extend(["--include-in-header", str(header)])
    elif config.cjk_font:
        if engine == "typst":
            cmd.extend(["--variable", f"mainfont={config.cjk_font}"])
        else:
            cmd.extend(["--variable", f"CJKmainfont={config.cjk_font}"])
    cmd.extend(config.extra_args)

    logger.info("rendering PDF with %s", engine)
    proc = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        timeout=600,
        **subprocess_text_options(),
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + "\n" + proc.stderr).splitlines()[-40:])
        raise RenderError(f"pandoc failed (exit {proc.returncode}):\n{tail}")
    if not output_pdf.exists() or output_pdf.stat().st_size == 0:
        raise RenderError("pandoc reported success but produced no PDF")

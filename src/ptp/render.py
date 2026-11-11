"""Pandoc rendering stage."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from .config import RenderConfig

logger = logging.getLogger(__name__)


class RenderError(RuntimeError):
    """Pandoc or the PDF engine failed."""


def render_pdf(
    markdown_path: Path, output_pdf: Path, config: RenderConfig, resource_dir: Path
) -> None:
    pandoc = shutil.which("pandoc")
    if pandoc is None:
        raise RenderError("pandoc not found in PATH")

    engine = config.engine
    if shutil.which(engine) is None:
        raise RenderError(
            f"PDF engine {engine!r} not found in PATH; install it or change render.engine"
        )

    cmd = [
        pandoc,
        str(markdown_path),
        "--from",
        "markdown+tex_math_dollars+raw_html+pipe_tables",
        "--to",
        "pdf",
        "--standalone",
        "--pdf-engine",
        engine,
        "--resource-path",
        str(resource_dir),
        "--output",
        str(output_pdf),
    ]
    if config.template is not None:
        cmd.extend(["--template", str(config.template)])
    if engine in {"xelatex", "lualatex"}:
        cmd.extend(["--pdf-engine-opt=-halt-on-error", "--pdf-engine-opt=-file-line-error"])
    if config.cjk_font:
        if engine == "typst":
            cmd.extend(["--variable", f"mainfont={config.cjk_font}"])
        else:
            cmd.extend(["--variable", f"CJKmainfont={config.cjk_font}"])
    cmd.extend(config.extra_args)

    logger.info("rendering PDF with %s", engine)
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + "\n" + proc.stderr).splitlines()[-40:])
        raise RenderError(f"pandoc failed (exit {proc.returncode}):\n{tail}")
    if not output_pdf.exists() or output_pdf.stat().st_size == 0:
        raise RenderError("pandoc reported success but produced no PDF")

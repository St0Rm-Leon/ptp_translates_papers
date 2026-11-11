"""MinerU integration: text-layer detection, tier policy, and parsing."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium

from .config import Config
from .devices import DeviceSelection, mineru_env_vars, mineru_environment

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TextLayerStats:
    pages: int
    text_pages: int
    low_text_pages: int
    chars_per_page: tuple[int, ...]

    @property
    def coverage(self) -> float:
        return self.text_pages / self.pages if self.pages else 0.0


@dataclass(frozen=True)
class MineruArtifacts:
    directory: Path
    markdown_path: Path
    structured_content_path: Path
    images_dir: Path
    tier: str


def inspect_text_layer(pdf_path: Path) -> TextLayerStats:
    """Measure how many pages contain a usable text layer."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        counts: list[int] = []
        for index in range(len(pdf)):
            page = pdf[index]
            text_page = page.get_textpage()
            text = text_page.get_text_range() or ""
            counts.append(len(text.strip()))
    finally:
        pdf.close()
    text_pages = sum(1 for count in counts if count >= 50)
    return TextLayerStats(
        pages=len(counts),
        text_pages=text_pages,
        low_text_pages=sum(1 for count in counts if count < 50),
        chars_per_page=tuple(counts),
    )


def resolve_tier(config: Config, selection: DeviceSelection, stats: TextLayerStats) -> str:
    """Resolve `tier: auto` according to the documented CPU/GPU policy."""
    if config.mineru.tier != "auto":
        return config.mineru.tier
    if selection.mode == "gpu":
        return "standard"
    if stats.coverage >= config.mineru.auto_basic_text_coverage and stats.low_text_pages == 0:
        return "basic"
    return "standard"


def parse_pdf(
    pdf_path: Path,
    work_dir: Path,
    config: Config,
    selection: DeviceSelection,
    tier: str,
) -> MineruArtifacts:
    """Run MinerU in-process (development/fallback path)."""
    from .mineru_worker import run_parse

    logger.info("MinerU tier=%s device=%s", tier, selection.mode)
    started = time.perf_counter()
    with mineru_environment(config, selection):
        mineru_dir = run_parse(
            pdf_path,
            work_dir,
            tier,
            image_analysis=config.mineru.image_analysis,
        )
    logger.info("MinerU finished in %.1fs", time.perf_counter() - started)

    markdown_path = mineru_dir / "markdown.md"
    structured_path = mineru_dir / "structured_content.json"
    images_dir = mineru_dir / "images"
    return MineruArtifacts(
        directory=mineru_dir,
        markdown_path=markdown_path,
        structured_content_path=structured_path,
        images_dir=images_dir,
        tier=tier,
    )


def _resolve_mineru_python(path: Path | None) -> Path:
    """Resolve a configured interpreter or a virtualenv directory."""
    if path is None:
        return Path(sys.executable)
    candidate = path.expanduser()
    if candidate.is_dir():
        for executable in (
            candidate / "bin" / "python",
            candidate / "Scripts" / "python.exe",
            candidate / "python.exe",
        ):
            if executable.exists():
                return executable
        raise RuntimeError(f"MinerU Python not found in virtualenv: {candidate}")
    if not candidate.exists():
        raise RuntimeError(f"MinerU Python not found: {candidate}")
    return candidate


_MINERU_CHECKED: set[str] = set()


def _ensure_mineru_available(python: Path) -> None:
    key = str(python)
    if key in _MINERU_CHECKED:
        return
    proc = subprocess.run(
        [str(python), "-c", "import mineru"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"MinerU is not installed in {python}. "
            "Run `ptp-install-mineru --accept-license` for an isolated install, "
            "or `uv sync --extra mineru` for the development environment."
        )
    _MINERU_CHECKED.add(key)


def parse_pdf_subprocess(
    pdf_path: Path,
    work_dir: Path,
    config: Config,
    selection: DeviceSelection,
    tier: str,
) -> MineruArtifacts:
    """Run MinerU in a child process so its GPU memory is released afterwards."""
    python = _resolve_mineru_python(config.mineru.python)
    _ensure_mineru_available(python)
    worker = Path(__file__).with_name("mineru_worker.py").resolve()
    cmd = [
        str(python),
        str(worker),
        "--pdf",
        str(pdf_path),
        "--work-dir",
        str(work_dir),
        "--tier",
        tier,
    ]
    if config.mineru.image_analysis:
        cmd.append("--image-analysis")
    env = os.environ.copy()
    env.update(mineru_env_vars(config, selection))
    logger.info(
        "MinerU child process: tier=%s device=%s python=%s",
        tier,
        selection.mode,
        python,
    )
    proc = subprocess.run(cmd, check=False, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"MinerU child process failed with exit code {proc.returncode}")
    mineru_dir = work_dir / "mineru"
    markdown_path = mineru_dir / "markdown.md"
    structured_path = mineru_dir / "structured_content.json"
    if not markdown_path.exists() or not structured_path.exists():
        raise RuntimeError("MinerU child process did not produce expected artifacts")
    return MineruArtifacts(
        directory=mineru_dir,
        markdown_path=markdown_path,
        structured_content_path=structured_path,
        images_dir=mineru_dir / "images",
        tier=tier,
    )


def load_structured_content(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

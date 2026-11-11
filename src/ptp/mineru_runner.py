"""MinerU integration: text-layer detection, tier policy, and parsing."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium

from .config import Config
from .devices import DeviceSelection, mineru_environment

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
    """Run MinerU and persist Markdown, structured content, and images."""
    from mineru import parse
    from mineru.parser.writer import FileBasedDataWriter

    mineru_dir = work_dir / "mineru"
    if mineru_dir.exists():
        shutil.rmtree(mineru_dir)
    mineru_dir.mkdir(parents=True, exist_ok=True)

    logger.info("MinerU tier=%s device=%s", tier, selection.mode)
    started = time.perf_counter()
    with mineru_environment(config, selection):
        result = parse(
            str(pdf_path),
            tier=tier,  # type: ignore[arg-type]
            image_analysis=config.mineru.image_analysis,
        )
        result.save(FileBasedDataWriter(str(mineru_dir)))
    logger.info("MinerU finished in %.1fs", time.perf_counter() - started)

    markdown_path = mineru_dir / "markdown.md"
    structured_path = mineru_dir / "structured_content.json"
    images_dir = mineru_dir / "images"
    if not markdown_path.exists():
        raise RuntimeError("MinerU did not produce markdown.md")
    if not structured_path.exists():
        raise RuntimeError("MinerU did not produce structured_content.json")
    return MineruArtifacts(
        directory=mineru_dir,
        markdown_path=markdown_path,
        structured_content_path=structured_path,
        images_dir=images_dir,
        tier=tier,
    )


def parse_pdf_subprocess(
    pdf_path: Path,
    work_dir: Path,
    config: Config,
    selection: DeviceSelection,
    tier: str,
) -> MineruArtifacts:
    """Run MinerU in a child process so its GPU memory is released afterwards."""
    cmd = [
        sys.executable,
        "-m",
        "ptp.mineru_worker",
        "--pdf",
        str(pdf_path),
        "--work-dir",
        str(work_dir),
        "--tier",
        tier,
        "--device",
        selection.mode,
        "--gpu-backend",
        config.gpu_backend,
    ]
    if config.gpu_index is not None:
        cmd.extend(["--gpu-index", str(config.gpu_index)])
    if isinstance(config.threads, int):
        cmd.extend(["--threads", str(config.threads)])
    if config.mineru.image_analysis:
        cmd.append("--image-analysis")
    logger.info("MinerU child process: tier=%s device=%s", tier, selection.mode)
    proc = subprocess.run(cmd, check=False)
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

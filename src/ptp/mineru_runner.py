"""MinerU integration: text-layer detection, tier policy, and parsing."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
import yaml

from .compat import WINDOWS, resolve_tool, utf8_env
from .config import Config
from .devices import DeviceSelection, mineru_env_vars

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


def _resolve_mineru_cli(python: Path) -> Path | None:
    """Locate the MinerU CLI for venv and standalone Python layouts."""
    name = "mineru-kit.exe" if WINDOWS else "mineru-kit"
    script_dir = "Scripts" if WINDOWS else "bin"
    for candidate in (
        python.parent / name,
        python.parent / script_dir / name,
    ):
        if candidate.exists():
            return candidate
    fallback = resolve_tool("mineru-kit")
    return Path(fallback) if fallback else None


def _safe_extract_zip(zip_path: Path, destination: Path) -> None:
    """Extract a MinerU result ZIP while rejecting path traversal."""
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target = (root / member.filename).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"unsafe ZIP member in MinerU result: {member.filename}")
        archive.extractall(root)


def _mineru_command(
    cli: Path, pdf_path: Path, zip_path: Path, tier: str, image_analysis: bool
) -> list[str]:
    command = [
        str(cli),
        "parse",
        str(pdf_path),
        "-o",
        str(zip_path),
        "--format",
        "zip",
        "--tier",
        tier,
        "--pages",
        "all",
    ]
    if not image_analysis:
        command.append("--disable-image-analysis")
    return command


def _write_mineru_config(
    config: Config, selection: DeviceSelection, work_dir: Path
) -> Path | None:
    """Write an absolute, per-run MinerU config for portable Windows layouts.

    MinerU's home config may contain build-machine paths after a portable
    package is moved.  Pointing ``MINERU_CONFIG`` at a generated file keeps
    ``model.base_dir`` correct no matter where the package is extracted.
    """
    if not WINDOWS:
        return None

    model: dict[str, object] = {"small_backend": "onnx", "vlm": {"engine": "llama-cpp"}}
    if config.mineru.model_source:
        model["source"] = config.mineru.model_source
    if config.mineru.model_dir is not None:
        model["base_dir"] = str(config.mineru.model_dir)
    if config.mineru.device == "gpu" or (
        config.mineru.device != "cpu" and selection.mode == "gpu"
    ):
        model["onnx_device"] = "gpu"
    else:
        model["onnx_device"] = "cpu"

    path = work_dir / "mineru-config.yaml"
    path.write_text(
        yaml.safe_dump({"model": model}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def parse_pdf_subprocess(
    pdf_path: Path,
    work_dir: Path,
    config: Config,
    selection: DeviceSelection,
    tier: str,
) -> MineruArtifacts:
    """Run MinerU through its independent CLI process.

    PTP only passes paths and environment variables to ``mineru-kit`` and reads
    the resulting ZIP.  No PTP/GPL code is imported into the MinerU process.
    """
    python = _resolve_mineru_python(config.mineru.python)
    cli = _resolve_mineru_cli(python)
    if cli is None:
        raise RuntimeError(
            f"MinerU CLI not found next to {python}. "
            "Run `ptp-install-mineru --accept-license` or install the mineru component."
        )

    mineru_dir = work_dir / "mineru"
    if mineru_dir.exists():
        shutil.rmtree(mineru_dir, ignore_errors=True)
    zip_path = work_dir / "mineru.zip"
    zip_path.unlink(missing_ok=True)
    cmd = _mineru_command(cli, pdf_path, zip_path, tier, config.mineru.image_analysis)

    env = utf8_env()
    env.update(mineru_env_vars(config, selection))
    mineru_config = _write_mineru_config(config, selection, work_dir)
    if mineru_config is not None:
        env["MINERU_CONFIG"] = str(mineru_config)
    logger.info(
        "MinerU CLI process: tier=%s device=%s cli=%s",
        tier,
        selection.mode,
        cli,
    )
    proc = subprocess.run(cmd, check=False, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"MinerU CLI process failed with exit code {proc.returncode}")
    if not zip_path.exists():
        raise RuntimeError("MinerU CLI did not produce a result ZIP")

    _safe_extract_zip(zip_path, mineru_dir)
    markdown_path = mineru_dir / "markdown.md"
    structured_path = mineru_dir / "structured_content.json"
    if not markdown_path.exists() or not structured_path.exists():
        raise RuntimeError("MinerU result ZIP is missing markdown.md or structured_content.json")
    zip_path.unlink(missing_ok=True)
    return MineruArtifacts(
        directory=mineru_dir,
        markdown_path=markdown_path,
        structured_content_path=structured_path,
        images_dir=mineru_dir / "images",
        tier=tier,
    )


def load_structured_content(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

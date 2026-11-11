"""Standalone MinerU worker.

This module intentionally imports only the standard library and MinerU so it
can run from a separate virtualenv that does not have PTP installed.  PTP sets
the MinerU device/model environment variables before starting it.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ptp-mineru-worker")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--tier", required=True)
    parser.add_argument("--image-analysis", action="store_true")
    return parser


def run_parse(
    pdf_path: Path,
    work_dir: Path,
    tier: str,
    image_analysis: bool = False,
) -> Path:
    """Run MinerU and return the directory containing its artifacts."""
    from mineru import parse
    from mineru.parser.writer import FileBasedDataWriter

    mineru_dir = work_dir / "mineru"
    if mineru_dir.exists():
        shutil.rmtree(mineru_dir)
    mineru_dir.mkdir(parents=True, exist_ok=True)

    result = parse(
        str(pdf_path),
        tier=tier,  # type: ignore[arg-type]
        image_analysis=image_analysis,
    )
    result.save(FileBasedDataWriter(str(mineru_dir)))

    if not (mineru_dir / "markdown.md").exists():
        raise RuntimeError("MinerU did not produce markdown.md")
    if not (mineru_dir / "structured_content.json").exists():
        raise RuntimeError("MinerU did not produce structured_content.json")
    return mineru_dir


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_parse(
        Path(args.pdf),
        Path(args.work_dir),
        args.tier,
        image_analysis=args.image_analysis,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

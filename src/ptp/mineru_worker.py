"""Isolated MinerU worker.

Running MinerU in a child process ensures its VLM/ONNX GPU allocations are
released before llama-server starts for translation.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import Config
from .devices import select_device
from .mineru_runner import parse_pdf


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ptp-mineru-worker")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--tier", required=True)
    parser.add_argument("--device", choices=["auto", "cpu", "gpu"], default="auto")
    parser.add_argument(
        "--gpu-backend", choices=["auto", "cuda", "vulkan", "metal"], default="auto"
    )
    parser.add_argument("--gpu-index", type=int)
    parser.add_argument("--threads", type=int)
    parser.add_argument("--image-analysis", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = Config()
    config.device = args.device
    config.gpu_backend = args.gpu_backend
    config.gpu_index = args.gpu_index
    config.threads = args.threads if args.threads is not None else "auto"
    config.mineru.tier = args.tier  # type: ignore[assignment]
    config.mineru.image_analysis = args.image_analysis
    selection = select_device(config)
    parse_pdf(Path(args.pdf), Path(args.work_dir), config, selection, args.tier)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

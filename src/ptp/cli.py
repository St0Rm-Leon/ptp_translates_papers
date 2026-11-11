"""Command-line entry point for PTP Translates Papers."""

from __future__ import annotations

import argparse
import logging
import sys

from . import __version__
from .config import Config, ConfigError, load_config
from .devices import DeviceError, select_device
from .pipeline import PipelineError, resolve_inputs, run_pipeline
from .render import RenderError
from .translate import TranslationError, download_default_model

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ptp",
        description="PTP Translates Papers — a local PDF paper translation pipeline.",
    )
    parser.add_argument("-i", "--input", nargs="+", metavar="PDF", help="input PDF(s) or directory")
    parser.add_argument("-o", "--output", metavar="DIR", help="output root directory")
    parser.add_argument("--config", metavar="FILE", help="config.yaml path")
    parser.add_argument(
        "--tier",
        choices=["auto", "flash", "basic", "standard", "advanced"],
        help="MinerU parsing tier",
    )
    parser.add_argument(
        "--mineru-python",
        metavar="PATH",
        help="Python executable/venv for the isolated MinerU worker",
    )
    parser.add_argument(
        "--mineru-model-source",
        choices=["auto", "huggingface", "modelscope", "local"],
        help="where MinerU downloads/loads models",
    )
    parser.add_argument(
        "--mineru-model-dir",
        metavar="DIR",
        help="MinerU model base directory (contains model subdirectories)",
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "gpu"],
        help="device policy for translation and MinerU",
    )
    device_aliases = parser.add_mutually_exclusive_group()
    device_aliases.add_argument(
        "--cpu-only",
        action="store_const",
        const="cpu",
        dest="device",
        help="alias for --device cpu",
    )
    device_aliases.add_argument(
        "--gpu-only",
        action="store_const",
        const="gpu",
        dest="device",
        help="alias for --device gpu",
    )
    parser.add_argument(
        "--gpu-backend",
        choices=["auto", "cuda", "vulkan", "metal"],
        help="GPU backend",
    )
    parser.add_argument("--gpu-index", type=int, help="llama.cpp GPU index")
    parser.add_argument("--threads", type=int, help="CPU threads")
    parser.add_argument("--task16", action="store_true", help="alias for --threads 16")
    parser.add_argument("--parallel", type=int, help="concurrent documents (default 1)")
    parser.add_argument(
        "--no-temp", action="store_false", dest="keep_temp", help="delete temp/ after success"
    )
    parser.add_argument(
        "--keep-temp", action="store_true", dest="keep_temp", help="keep temp/ (default)"
    )
    parser.add_argument("--resume", action="store_true", help="reuse completed stages")
    parser.add_argument(
        "--dry-run", action="store_true", help="print resolved work without running"
    )
    parser.add_argument(
        "--download-model", action="store_true", help="download the default Q4_K_M GGUF and exit"
    )
    parser.add_argument("--model", metavar="FILE", help="translation GGUF path")
    parser.add_argument("--server-url", metavar="URL", help="use an already running llama-server")
    parser.add_argument(
        "--layout",
        choices=["single", "bilingual"],
        help="single-column or bilingual two-column output",
    )
    parser.add_argument(
        "--engine",
        choices=["xelatex", "lualatex", "tectonic", "typst"],
        help="Pandoc PDF engine",
    )
    parser.add_argument("--cjk-font", metavar="FONT", help="CJK font family")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="logging level",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(levelname)s %(message)s",
    )


def _print_config(config: Config) -> None:
    print(f"input:      {config.input}")
    print(f"output:     {config.output}")
    print(f"tier:       {config.mineru.tier}")
    print(f"device:     {config.device}")
    print(f"gpu_backend:{config.gpu_backend}")
    print(f"gguf:       {config.translation.model}")
    print(f"engine:     {config.render.engine}")
    print(f"keep_temp:  {config.keep_temp}")
    print(f"parallel:   {config.parallel}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _configure_logging(args.log_level)
    try:
        config = load_config(args.config).with_cli_overrides(args)
        if args.download_model:
            path = download_default_model(config)
            print(f"model: {path}")
            return 0
        inputs = resolve_inputs(config, args.input)
        if args.dry_run:
            _print_config(config)
            selection = select_device(config)
            print(f"resolved_device: {selection.mode} ({selection.reason})")
            if selection.info:
                print(f"gpu: {selection.info.token} {selection.info.name}")
            print("inputs:")
            for path in inputs:
                print(f"  {path} -> {config.output / f'{path.stem}_zh'}")
            return 0

        results = run_pipeline(config, inputs)
        failures = 0
        for result in results:
            if result.error:
                failures += 1
                print(f"失败: {result.source} — {result.error}", file=sys.stderr)
            elif result.skipped:
                print(f"已完成: {result.pdf}")
            else:
                print(f"输出: {result.pdf}")
                if result.temp_dir:
                    print(f"过程文件: {result.temp_dir}")
                else:
                    print("已清理缓存的过程文件。")
        return 1 if failures else 0
    except (ConfigError, DeviceError, PipelineError, TranslationError, RenderError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

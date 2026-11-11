"""Install MinerU into an isolated virtual environment."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

DEFAULT_MINERU_SPEC = "mineru>=4.1,<5"
MINERU_LICENSE_URL = "https://github.com/opendatalab/MinerU/blob/master/LICENSE.md"


def default_target() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "ptp" / "mineru"


def venv_python(target: Path) -> Path:
    if os.name == "nt":
        return target / "Scripts" / "python.exe"
    return target / "bin" / "python"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ptp-install-mineru",
        description="Install MinerU in a separate virtualenv (not inside PTP's environment).",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=default_target(),
        help="virtualenv directory (default: platform user data directory)",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="base Python used to create the virtualenv",
    )
    parser.add_argument(
        "--mineru-spec",
        default=DEFAULT_MINERU_SPEC,
        help=f"pip requirement (default: {DEFAULT_MINERU_SPEC})",
    )
    parser.add_argument(
        "--accept-license",
        action="store_true",
        help="acknowledge the MinerU license before downloading it",
    )
    parser.add_argument("--upgrade", action="store_true", help="upgrade an existing install")
    parser.add_argument("--dry-run", action="store_true", help="print commands without running")
    return parser


def _run(command: list[str], *, dry_run: bool) -> None:
    print("+ " + shlex.join(command))
    if dry_run:
        return
    subprocess.run(command, check=True)


def _print_license() -> None:
    print("MinerU is licensed under the MinerU Open Source License")
    print("(Apache License 2.0 with additional terms).")
    print(f"Full text: {MINERU_LICENSE_URL}")
    print("MinerU models retain their own upstream licenses and attribution.")
    print()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _print_license()
    if not args.accept_license:
        print("Re-run with --accept-license after reviewing the license.")
        return 2

    target = args.target.expanduser().resolve()
    python = venv_python(target)
    base_python = Path(args.python).expanduser().resolve()
    if not base_python.exists():
        print(f"Base Python not found: {base_python}", file=sys.stderr)
        return 1

    if not args.dry_run:
        target.mkdir(parents=True, exist_ok=True)
    if not python.exists():
        _run([str(base_python), "-m", "venv", str(target)], dry_run=args.dry_run)

    _run(
        [str(python), "-m", "pip", "install", "--upgrade", "pip"],
        dry_run=args.dry_run,
    )
    install = [str(python), "-m", "pip", "install"]
    if args.upgrade:
        install.append("--upgrade")
    install.append(args.mineru_spec)
    _run(install, dry_run=args.dry_run)

    snippet = f"mineru:\n  python: {python}\n  model_source: auto\n"
    print("\nAdd this to config.yaml:\n")
    print(snippet)
    print(
        "MinerU models download automatically on the first parse. "
        "For an offline bundle, set model_source: local and model_dir."
    )
    if not args.dry_run:
        (target / "config-snippet.yaml").write_text(snippet, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

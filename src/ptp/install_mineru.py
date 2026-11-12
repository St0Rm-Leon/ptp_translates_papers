"""Install MinerU into an isolated virtual environment."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml

from .compat import format_command, subprocess_text_options, utf8_env

# MinerU 4.2 has not been validated with this pipeline; keep the tested 4.1 series.
DEFAULT_MINERU_SPEC = "mineru>=4.1,<4.2"
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
    parser.add_argument(
        "--wheelhouse",
        type=Path,
        help="offline wheel directory; installs with --no-index --find-links",
    )
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="do not query package indexes (use with a preconfigured find-links)",
    )
    parser.add_argument("--dry-run", action="store_true", help="print commands without running")
    return parser


def _run(command: list[str], *, dry_run: bool) -> None:
    print("+ " + format_command(command))
    if dry_run:
        return
    subprocess.run(command, check=True, env=utf8_env())


def _print_license() -> None:
    print("MinerU is licensed under the MinerU Open Source License")
    print("(Apache License 2.0 with additional terms).")
    print(f"Full text: {MINERU_LICENSE_URL}")
    print("MinerU models retain their own upstream licenses and attribution.")
    print()


def _absolute_without_symlink_resolution(path: Path) -> Path:
    """Make a path absolute without following a venv's python symlink."""
    path = path.expanduser()
    if path.is_absolute():
        return path
    return (Path.cwd() / path).absolute()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _print_license()
    if not args.accept_license:
        print("Re-run with --accept-license after reviewing the license.")
        return 2

    if getattr(sys, "frozen", False) and Path(args.python) == Path(sys.executable):
        print(
            "A frozen PTP executable cannot create a virtualenv. "
            "Pass --python with a real Python 3.11-3.14 interpreter.",
            file=sys.stderr,
        )
        return 1

    target = args.target.expanduser().resolve()
    python = venv_python(target)
    base_python = _absolute_without_symlink_resolution(Path(args.python))
    if not base_python.exists():
        print(f"Base Python not found: {base_python}", file=sys.stderr)
        return 1
    if args.wheelhouse is not None and not args.wheelhouse.expanduser().exists():
        print(f"Wheelhouse not found: {args.wheelhouse}", file=sys.stderr)
        return 1

    if not args.dry_run:
        target.mkdir(parents=True, exist_ok=True)
    if not python.exists():
        _run([str(base_python), "-m", "venv", str(target)], dry_run=args.dry_run)

    offline = args.wheelhouse is not None or args.no_index
    if not offline:
        _run(
            [str(python), "-m", "pip", "install", "--upgrade", "pip"],
            dry_run=args.dry_run,
        )
    install = [str(python), "-m", "pip", "install"]
    if args.upgrade:
        install.append("--upgrade")
    if args.wheelhouse is not None:
        install.extend(
            ["--no-index", "--find-links", str(args.wheelhouse.expanduser().resolve())]
        )
    elif args.no_index:
        install.append("--no-index")
    install.append(args.mineru_spec)
    _run(install, dry_run=args.dry_run)

    if not args.dry_run:
        check = subprocess.run(
            [str(python), "-c", "import mineru"],
            check=False,
            capture_output=True,
            env=utf8_env(),
            **subprocess_text_options(),
        )
        if check.returncode != 0:
            detail = check.stderr.strip().splitlines()
            print(
                "MinerU was installed but cannot be imported"
                + (f": {detail[-1]}" if detail else "."),
                file=sys.stderr,
            )
            return 1

    snippet = yaml.safe_dump(
        {"mineru": {"python": str(python), "model_source": "auto"}},
        sort_keys=False,
        allow_unicode=True,
    )
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

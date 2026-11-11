"""Cross-platform process, encoding and executable helpers.

Windows defaults to the ANSI code page for redirected child-process I/O and
for console streams.  PTP works with Chinese Markdown and LaTeX, so every text
subprocess must explicitly use UTF-8.  This module keeps that policy in one
place and also resolves configured executables (bundled Windows portable
layouts use paths such as ``tools/pandoc/pandoc.exe``).
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

WINDOWS = os.name == "nt"


def subprocess_text_options() -> dict[str, object]:
    """Return UTF-8 text-mode options for ``subprocess.run``/``Popen``."""
    return {"text": True, "encoding": "utf-8", "errors": "replace"}


def utf8_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Copy an environment and force UTF-8 mode in child Python processes."""
    env = dict(os.environ if base is None else base)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def configure_stdio() -> None:
    """Use UTF-8 for redirected stdout/stderr on Windows."""
    if not WINDOWS:
        return
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def hidden_window_flags() -> int:
    """Return creation flags that suppress a console window for child tools."""
    if not WINDOWS:
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def resolve_tool(value: str | os.PathLike[str] | None) -> str | None:
    """Resolve a configured executable name or path.

    Bare names (``pandoc``, ``llama-server``) go through ``PATH``.  Values that
    look like paths are used as-is when present; this supports portable Windows
    bundles without putting tool directories on ``PATH``.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    path = Path(text).expanduser()
    looks_like_path = path.is_absolute() or path.parent != Path(".")
    if looks_like_path:
        return str(path) if path.exists() else None
    return shutil.which(text)


def format_command(command: Sequence[str]) -> str:
    """Render a command in the platform's conventional quoting style."""
    if WINDOWS:
        return subprocess.list2cmdline(list(command))
    return shlex.join(command)

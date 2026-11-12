import os
import sys
from pathlib import Path

import pytest

from ptp.install_mineru import _absolute_without_symlink_resolution, main, venv_python


def test_venv_python_layout(tmp_path: Path):
    target = tmp_path / "ptp-mineru"
    executable = venv_python(target)
    assert executable.stem == "python"
    assert executable.parent.name in {"bin", "Scripts"}


def test_installer_requires_license_acceptance(tmp_path: Path, capsys):
    assert main(["--target", str(tmp_path / "ptp-mineru")]) == 2
    output = capsys.readouterr().out
    assert "MinerU Open Source License" in output


def test_installer_dry_run_prints_config(tmp_path: Path, capsys):
    target = tmp_path / "ptp-mineru-dry-run"
    result = main(
        [
            "--target",
            str(target),
            "--python",
            sys.executable,
            "--accept-license",
            "--dry-run",
        ]
    )
    assert result == 0
    output = capsys.readouterr().out
    assert "python:" in output
    assert target.name in output
    assert "mineru:" in output
    assert "model_source: auto" in output


def test_installer_dry_run_offline_wheelhouse(tmp_path: Path, capsys):
    target = tmp_path / "ptp-mineru-offline"
    wheelhouse = tmp_path / "wheels"
    wheelhouse.mkdir()
    result = main(
        [
            "--target",
            str(target),
            "--python",
            sys.executable,
            "--wheelhouse",
            str(wheelhouse),
            "--accept-license",
            "--dry-run",
        ]
    )
    assert result == 0
    output = capsys.readouterr().out
    assert "--no-index" in output
    assert "--find-links" in output
    assert "pip install --upgrade pip" not in output


@pytest.mark.skipif(os.name == "nt", reason="symlink creation may require privileges")
def test_installer_does_not_resolve_venv_python_symlink(tmp_path: Path):
    base = tmp_path / "base-python"
    base.write_text("", encoding="utf-8")
    venv = tmp_path / "venv" / "bin" / "python"
    venv.parent.mkdir(parents=True)
    venv.symlink_to(base)
    assert _absolute_without_symlink_resolution(venv) == venv

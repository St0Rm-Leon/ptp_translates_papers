import sys
from pathlib import Path

from ptp.install_mineru import main, venv_python


def test_venv_python_layout():
    target = Path("/tmp/ptp-mineru")
    executable = venv_python(target)
    assert executable.name == "python"
    assert executable.parent.name in {"bin", "Scripts"}


def test_installer_requires_license_acceptance(capsys):
    assert main(["--target", "/tmp/ptp-mineru"]) == 2
    output = capsys.readouterr().out
    assert "MinerU Open Source License" in output


def test_installer_dry_run_prints_config(capsys):
    result = main(
        [
            "--target",
            "/tmp/ptp-mineru-dry-run",
            "--python",
            sys.executable,
            "--accept-license",
            "--dry-run",
        ]
    )
    assert result == 0
    output = capsys.readouterr().out
    assert "mineru-venv" in output or "ptp-mineru-dry-run" in output
    assert "mineru:" in output
    assert "model_source: auto" in output

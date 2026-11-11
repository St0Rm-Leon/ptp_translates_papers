import zipfile
from pathlib import Path

import pytest
import yaml

from ptp.compat import WINDOWS
from ptp.config import Config
from ptp.devices import DeviceSelection
from ptp.mineru_runner import (
    _mineru_command,
    _resolve_mineru_cli,
    _safe_extract_zip,
    _write_mineru_config,
)


@pytest.mark.skipif(not WINDOWS, reason="portable MinerU config is Windows-specific")
def test_mineru_config_uses_absolute_model_dir_and_engine(tmp_path: Path):
    config = Config()
    config.mineru.model_dir = tmp_path / "mineru-models"
    config.mineru.model_source = "local"
    selection = DeviceSelection(mode="gpu")

    path = _write_mineru_config(config, selection, tmp_path)
    assert path is not None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["model"]["source"] == "local"
    assert data["model"]["base_dir"] == str(tmp_path / "mineru-models")
    assert data["model"]["small_backend"] == "onnx"
    assert data["model"]["onnx_device"] == "gpu"
    assert data["model"]["vlm"]["engine"] == "llama-cpp"


def test_resolve_mineru_cli_from_interpreter_directory(tmp_path: Path):
    python = tmp_path / ("python.exe" if WINDOWS else "python")
    python.write_text("", encoding="utf-8")
    cli_name = "mineru-kit.exe" if WINDOWS else "mineru-kit"
    cli = tmp_path / cli_name
    cli.write_text("", encoding="utf-8")

    assert _resolve_mineru_cli(python) == cli


def test_mineru_command_uses_zip_and_image_analysis_flag(tmp_path: Path):
    cli = tmp_path / "mineru-kit"
    command = _mineru_command(
        cli, tmp_path / "paper.pdf", tmp_path / "mineru.zip", "standard", False
    )
    assert command[:3] == [str(cli), "parse", str(tmp_path / "paper.pdf")]
    assert command[command.index("--format") + 1] == "zip"
    assert command[command.index("--tier") + 1] == "standard"
    assert command[command.index("--pages") + 1] == "all"
    assert "--disable-image-analysis" in command

    with_analysis = _mineru_command(
        cli, tmp_path / "paper.pdf", tmp_path / "mineru.zip", "basic", True
    )
    assert "--disable-image-analysis" not in with_analysis


def test_safe_extract_zip_extracts_expected_artifacts(tmp_path: Path):
    archive = tmp_path / "result.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("markdown.md", "# paper")
        zf.writestr("structured_content.json", "{}")
        zf.writestr("images/fig1.jpg", b"image")

    destination = tmp_path / "out"
    _safe_extract_zip(archive, destination)
    assert (destination / "markdown.md").read_text(encoding="utf-8") == "# paper"
    assert (destination / "structured_content.json").exists()
    assert (destination / "images" / "fig1.jpg").exists()


def test_safe_extract_zip_rejects_path_traversal(tmp_path: Path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../evil.txt", "bad")

    with pytest.raises(RuntimeError, match="unsafe ZIP member"):
        _safe_extract_zip(archive, tmp_path / "out")

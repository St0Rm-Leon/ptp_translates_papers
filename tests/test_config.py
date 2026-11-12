import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from ptp.config import Config, ConfigError, load_config


def test_example_config_loads():
    config = load_config("config.example.yaml")
    assert config.mineru.tier == "auto"
    assert config.render.engine == "xelatex"
    assert config.translation.model.name == "Hy-MT2-1.8B-Q4_K_M.gguf"
    assert config.output.name == "outputs"


def test_unknown_key_is_rejected(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text("version: 1\nnot_a_real_option: true\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown key"):
        load_config(str(path))


def test_cli_overrides_task16_and_temp(tmp_path: Path):
    args = SimpleNamespace(
        task16=True,
        threads=None,
        output=str(tmp_path / "out"),
        keep_temp=False,
        parallel=2,
        device="cpu",
        gpu_backend="vulkan",
        gpu_index=1,
        resume=True,
        tier="basic",
        model=None,
        server_url=None,
        engine="xelatex",
        cjk_font=None,
    )
    config = Config().with_cli_overrides(args)
    assert config.threads == 16
    assert config.output == tmp_path / "out"
    assert config.keep_temp is False
    assert config.parallel == 2
    assert config.device == "cpu"
    assert config.gpu_backend == "vulkan"
    assert config.gpu_index == 1
    assert config.resume is True
    assert config.mineru.tier == "basic"


def test_relative_paths_are_config_relative(tmp_path: Path):
    (tmp_path / "papers").mkdir()
    (tmp_path / "config.yaml").write_text(
        "version: 1\ninput: papers\noutput: out\n", encoding="utf-8"
    )
    config = load_config(str(tmp_path / "config.yaml"))
    assert config.input == tmp_path / "papers"
    assert config.output == tmp_path / "out"


def test_mineru_isolated_python_and_model_dir(tmp_path: Path):
    (tmp_path / "mineru-venv" / "bin").mkdir(parents=True)
    (tmp_path / "mineru-venv" / "bin" / "python").write_text("", encoding="utf-8")
    (tmp_path / "mineru-models").mkdir()
    path = tmp_path / "config.yaml"
    path.write_text(
        "version: 1\n"
        "mineru:\n"
        "  python: mineru-venv/bin/python\n"
        "  model_source: local\n"
        "  model_dir: mineru-models\n",
        encoding="utf-8",
    )
    config = load_config(str(path))
    assert config.mineru.python == tmp_path / "mineru-venv" / "bin" / "python"
    assert config.mineru.model_source == "local"
    assert config.mineru.model_dir == tmp_path / "mineru-models"


def test_portable_tool_and_font_paths_are_config_relative(tmp_path: Path):
    (tmp_path / "tools" / "pandoc").mkdir(parents=True)
    (tmp_path / "tools" / "pandoc" / "pandoc.exe").write_text("", encoding="utf-8")
    (tmp_path / "tools" / "llama").mkdir(parents=True)
    (tmp_path / "tools" / "llama" / "llama-server.exe").write_text("", encoding="utf-8")
    (tmp_path / "tools" / "llama" / "llama-cli.exe").write_text("", encoding="utf-8")
    (tmp_path / "fonts").mkdir()
    (tmp_path / "fonts" / "NotoSerifCJKsc-Regular.otf").write_text("", encoding="utf-8")
    path = tmp_path / "config.yaml"
    path.write_text(
        "version: 1\n"
        "translation:\n"
        "  server_bin: tools/llama/llama-server.exe\n"
        "  llama_cli: tools/llama/llama-cli.exe\n"
        "render:\n"
        "  pandoc: tools/pandoc/pandoc.exe\n"
        "  xelatex: xelatex\n"
        "  cjk_font_file: fonts/NotoSerifCJKsc-Regular.otf\n",
        encoding="utf-8",
    )
    config = load_config(str(path))
    assert Path(config.translation.server_bin) == (
        tmp_path / "tools" / "llama" / "llama-server.exe"
    )
    assert Path(config.translation.llama_cli) == (
        tmp_path / "tools" / "llama" / "llama-cli.exe"
    )
    assert Path(config.render.pandoc) == (tmp_path / "tools" / "pandoc" / "pandoc.exe")
    assert config.render.xelatex == "xelatex"
    assert config.render.cjk_font_file == (
        tmp_path / "fonts" / "NotoSerifCJKsc-Regular.otf"
    )


def test_translation_cpu_gpu_binary_selection():
    config = Config()
    config.translation.server_bin = "default-server"
    config.translation.server_bin_cpu = "cpu-server"
    config.translation.server_bin_gpu = "gpu-server"
    config.translation.llama_cli = "default-cli"
    config.translation.llama_cli_cpu = "cpu-cli"
    config.translation.llama_cli_gpu = "gpu-cli"
    assert config.translation.server_bin_for("cpu") == "cpu-server"
    assert config.translation.server_bin_for("gpu") == "gpu-server"
    assert config.translation.llama_cli_for("cpu") == "cpu-cli"
    assert config.translation.llama_cli_for("gpu") == "gpu-cli"
    config.translation.server_bin_cpu = None
    config.translation.server_bin_gpu = None
    assert config.translation.server_bin_for("cpu") == "default-server"
    assert config.translation.server_bin_for("gpu") == "default-server"


def test_invalid_mineru_model_source_is_rejected(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "version: 1\nmineru:\n  model_source: dropbox\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="mineru.model_source"):
        load_config(str(path))


@pytest.mark.skipif(os.name == "nt", reason="symlink creation may require privileges")
def test_mineru_python_symlink_is_not_resolved(tmp_path: Path):
    venv_python = tmp_path / "venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    base_python = tmp_path / "base-python"
    base_python.write_text("", encoding="utf-8")
    venv_python.symlink_to(base_python)
    path = tmp_path / "config.yaml"
    path.write_text(
        "version: 1\nmineru:\n  python: venv/bin/python\n", encoding="utf-8"
    )
    config = load_config(str(path))
    assert config.mineru.python == venv_python
    assert config.mineru.python.is_symlink()

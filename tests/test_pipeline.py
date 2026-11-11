from pathlib import Path

import pytest

from ptp.config import Config
from ptp.pipeline import PipelineError, resolve_inputs


def test_empty_default_input_directory_has_actionable_message(tmp_path: Path):
    config = Config()
    config.input = tmp_path / "inputs"
    config.input.mkdir()

    with pytest.raises(PipelineError, match="no PDF inputs found.*inputs"):
        resolve_inputs(config, None)


def test_empty_cli_input_directory_names_directory(tmp_path: Path):
    config = Config()
    empty = tmp_path / "empty"
    empty.mkdir()

    with pytest.raises(PipelineError, match="no PDF inputs found.*empty"):
        resolve_inputs(config, [str(empty)])

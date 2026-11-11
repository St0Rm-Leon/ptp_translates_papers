import os
from pathlib import Path

from ptp import devices
from ptp.config import Config
from ptp.devices import DeviceSelection, list_devices, mineru_env_vars


class _FakeCompleted:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.stderr = ""


def test_list_devices_parses_llama_output(monkeypatch):
    output = (
        "Available devices:\n"
        "  Vulkan0: AMD Radeon Graphics (RADV) (8964 MiB, 8686 MiB free)\n"
        "  Vulkan1: NVIDIA GeForce RTX 3050 (NVK) (4096 MiB, 3686 MiB free)\n"
    )
    monkeypatch.setattr(devices, "resolve_tool", lambda binary: "llama-cli")
    monkeypatch.setattr(devices.subprocess, "run", lambda *args, **kwargs: _FakeCompleted(output))

    parsed = list_devices("llama-cli")
    assert [device.token for device in parsed] == ["Vulkan0", "Vulkan1"]
    assert parsed[1].name == "NVIDIA GeForce RTX 3050 (NVK)"
    assert parsed[1].memory_mib == 4096
    assert parsed[1].free_mib == 3686


def test_mineru_env_vars_include_isolated_model_settings(tmp_path: Path):
    config = Config()
    config.mineru.model_source = "local"
    config.mineru.model_dir = tmp_path / "models"
    config.mineru.home = tmp_path / "mineru-home"
    config.mineru.device = "cpu"
    env = mineru_env_vars(config, DeviceSelection(mode="cpu"))
    assert env["MINERU_MODEL_SOURCE"] == "local"
    assert env["MINERU_MODEL_BASE_DIR"] == str(tmp_path / "models")
    assert env["MINERU_HOME"] == str(tmp_path / "mineru-home")
    assert env["MINERU_DEVICE_MODE"] == "cpu"
    if os.name == "nt":
        assert env["MINERU_MODEL_SMALL_BACKEND"] == "onnx"
        assert env["MINERU_MODEL_VLM_ENGINE"] == "llama-cpp"


def test_mineru_env_vars_use_vulkan_for_gpu(tmp_path: Path):
    config = Config()
    config.gpu_backend = "vulkan"
    selection = DeviceSelection(
        mode="gpu",
        info=devices.DeviceInfo(
            token="Vulkan1",
            backend="Vulkan",
            index=1,
            name="Test GPU",
        ),
    )
    env = mineru_env_vars(config, selection)
    assert env["MINERU_MODEL_ONNX_DEVICE"] == "gpu"
    assert env["MINERU_LLAMA_CPP_BACKEND"] == "vulkan"
    assert env["GGML_VK_VISIBLE_DEVICES"] == "1"

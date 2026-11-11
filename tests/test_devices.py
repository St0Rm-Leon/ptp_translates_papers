from pathlib import Path

from ptp.config import Config
from ptp.devices import DeviceSelection, list_devices, mineru_env_vars


def test_list_devices_parses_llama_output(tmp_path: Path):
    fake = tmp_path / "fake-llama"
    fake.write_text(
        "#!/bin/sh\n"
        "cat <<'EOF'\n"
        "Available devices:\n"
        "  Vulkan0: AMD Radeon Graphics (RADV) (8964 MiB, 8686 MiB free)\n"
        "  Vulkan1: NVIDIA GeForce RTX 3050 (NVK) (4096 MiB, 3686 MiB free)\n"
        "EOF\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)

    devices = list_devices(str(fake))
    assert [device.token for device in devices] == ["Vulkan0", "Vulkan1"]
    assert devices[1].name == "NVIDIA GeForce RTX 3050 (NVK)"
    assert devices[1].memory_mib == 4096
    assert devices[1].free_mib == 3686


def test_mineru_env_vars_include_isolated_model_settings(tmp_path: Path):
    config = Config()
    config.mineru.model_source = "local"
    config.mineru.model_dir = tmp_path / "models"
    config.mineru.device = "cpu"
    env = mineru_env_vars(config, DeviceSelection(mode="cpu"))
    assert env["MINERU_MODEL_SOURCE"] == "local"
    assert env["MINERU_MODEL_BASE_DIR"] == str(tmp_path / "models")
    assert env["MINERU_DEVICE_MODE"] == "cpu"

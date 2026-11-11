from pathlib import Path

from ptp.devices import list_devices


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

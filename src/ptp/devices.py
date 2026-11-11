"""llama.cpp device discovery and device policy."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass

from .compat import resolve_tool, subprocess_text_options
from .config import Config


class DeviceError(RuntimeError):
    """No usable device or an explicitly requested device is unavailable."""


@dataclass(frozen=True)
class DeviceInfo:
    token: str
    backend: str
    index: int
    name: str
    memory_mib: int | None = None
    free_mib: int | None = None


@dataclass(frozen=True)
class DeviceSelection:
    mode: str  # "cpu" or "gpu"
    info: DeviceInfo | None = None
    reason: str = "cpu"
    gpu_layers: int = 0

    @property
    def llama_device(self) -> str | None:
        return self.info.token if self.info else None


_DEVICE_RE = re.compile(
    r"^\s*(?P<backend>[A-Za-z]+)(?P<index>\d+):\s*(?P<name>.*?)"
    r"\s*\((?P<mem>\d+)\s*MiB,\s*(?P<free>\d+)\s*MiB free\)\s*$"
)


def list_devices(binary: str = "llama-cli") -> list[DeviceInfo]:
    """Return devices reported by llama.cpp, or an empty list if unavailable."""
    executable = resolve_tool(binary)
    if executable is None:
        return []
    try:
        proc = subprocess.run(
            [executable, "--list-devices"],
            check=False,
            capture_output=True,
            timeout=20,
            **subprocess_text_options(),
        )
    except (OSError, subprocess.SubprocessError):
        return []
    devices: list[DeviceInfo] = []
    for line in (proc.stdout + "\n" + proc.stderr).splitlines():
        match = _DEVICE_RE.match(line)
        if not match:
            continue
        devices.append(
            DeviceInfo(
                token=f"{match.group('backend')}{match.group('index')}",
                backend=match.group("backend"),
                index=int(match.group("index")),
                name=match.group("name").strip(),
                memory_mib=int(match.group("mem")),
                free_mib=int(match.group("free")),
            )
        )
    return devices


def _preferred_gpu(devices: list[DeviceInfo]) -> DeviceInfo:
    # Prefer a discrete NVIDIA/AMD GPU by name, then any discrete-looking device.
    for needle in ("nvidia", "geforce", "rtx", "radeon", "arc"):
        for device in devices:
            if needle in device.name.lower():
                return device
    return devices[0]


def select_device(config: Config, *, binary: str | None = None) -> DeviceSelection:
    """Resolve the top-level device policy for translation and MinerU."""
    devices = list_devices(binary or config.translation.llama_cli)
    requested = config.device
    backend = config.gpu_backend

    if requested == "cpu":
        return DeviceSelection(mode="cpu", reason="explicit_cpu", gpu_layers=0)

    if backend != "auto":
        filtered = [d for d in devices if d.backend.lower() == backend.lower()]
        if not filtered:
            raise DeviceError(
                f"requested GPU backend {backend!r} but llama.cpp reports no such device; "
                "install the matching backend or use --device cpu"
            )
        devices = filtered

    if requested == "gpu":
        if not devices:
            raise DeviceError(
                "requested GPU mode but llama.cpp reports no GPU device; "
                "install a Vulkan/CUDA backend or use --device cpu"
            )
        chosen = _select_index(devices, config.gpu_index)
        return DeviceSelection(mode="gpu", info=chosen, reason="explicit_gpu", gpu_layers=99)

    if requested == "auto":
        if devices:
            chosen = _select_index(devices, config.gpu_index)
            return DeviceSelection(mode="gpu", info=chosen, reason="auto_gpu", gpu_layers=99)
        return DeviceSelection(mode="cpu", reason="auto_cpu", gpu_layers=0)

    raise DeviceError(f"unsupported device policy: {requested!r}")


def _select_index(devices: list[DeviceInfo], index: int | None) -> DeviceInfo:
    if index is None:
        return _preferred_gpu(devices)
    for device in devices:
        if device.index == index:
            return device
    raise DeviceError(
        f"GPU index {index} not reported by llama.cpp; available: "
        + ", ".join(f"{d.token}={d.name}" for d in devices)
    )


def mineru_env_vars(config: Config, selection: DeviceSelection) -> dict[str, str]:
    """Environment variables for an isolated MinerU worker process."""
    updates: dict[str, str] = {}
    if os.name == "nt":
        # MinerU 4.1 selects the small-model and VLM runtimes independently.
        # The Windows x64 base package ships ONNX (DirectML) and llama.cpp;
        # pin both so a full-extra install cannot select LMDeploy unexpectedly.
        updates["MINERU_MODEL_SMALL_BACKEND"] = "onnx"
        updates["MINERU_MODEL_VLM_ENGINE"] = "llama-cpp"

    if selection.mode == "cpu":
        updates["MINERU_DEVICE_MODE"] = "cpu"
        updates["MINERU_MODEL_ONNX_DEVICE"] = "cpu"
        updates["MINERU_LLAMA_CPP_BACKEND"] = "cpu"
    elif selection.mode == "gpu":
        updates["MINERU_DEVICE_MODE"] = "gpu"
        updates["MINERU_MODEL_ONNX_DEVICE"] = "gpu"
        # MinerU's bundled llama.cpp supports Vulkan and Metal; CUDA is handled
        # by the optional Torch/vLLM path, so leave that to auto for now.
        if config.gpu_backend in {"auto", "vulkan"}:
            updates["MINERU_LLAMA_CPP_BACKEND"] = "vulkan"
        if selection.info and selection.info.backend.lower() == "vulkan":
            updates["GGML_VK_VISIBLE_DEVICES"] = str(selection.info.index)

    threads = config.threads
    if isinstance(threads, int):
        updates["MINERU_INTRA_OP_NUM_THREADS"] = str(threads)
        updates["MINERU_INTER_OP_NUM_THREADS"] = "1"
        updates["MINERU_CPU_NUM_THREADS"] = str(threads)
    if config.mineru.device == "cpu":
        updates["MINERU_DEVICE_MODE"] = "cpu"
        updates["MINERU_MODEL_ONNX_DEVICE"] = "cpu"
        updates["MINERU_LLAMA_CPP_BACKEND"] = "cpu"
    elif config.mineru.device == "gpu":
        updates["MINERU_DEVICE_MODE"] = "gpu"
        updates["MINERU_MODEL_ONNX_DEVICE"] = "gpu"

    updates["MINERU_MODEL_SOURCE"] = config.mineru.model_source
    if config.mineru.model_dir is not None:
        updates["MINERU_MODEL_BASE_DIR"] = str(config.mineru.model_dir)
    if config.mineru.home is not None:
        updates["MINERU_HOME"] = str(config.mineru.home)
    return updates

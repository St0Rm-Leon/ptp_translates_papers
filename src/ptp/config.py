"""Configuration loading and CLI override handling."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import yaml

Tier = Literal["auto", "flash", "basic", "standard", "advanced"]
Device = Literal["auto", "cpu", "gpu"]
GpuBackend = Literal["auto", "cuda", "vulkan", "metal"]
MineruModelSource = Literal["auto", "huggingface", "modelscope", "local"]
RenderEngine = Literal["xelatex", "lualatex", "tectonic", "typst"]
RenderLayout = Literal["single", "bilingual"]


class ConfigError(ValueError):
    """Invalid or unusable configuration."""


@dataclass
class MineruConfig:
    tier: Tier = "auto"
    device: Device | None = None
    auto_basic_text_coverage: float = 0.8
    image_analysis: bool = False
    python: Path | None = None
    model_source: MineruModelSource = "auto"
    model_dir: Path | None = None
    extra_args: list[str] = field(default_factory=list)


@dataclass
class TranslationConfig:
    model: Path = Path("models/Hy-MT2-1.8B-Q4_K_M.gguf")
    server_bin: str = "llama-server"
    server_url: str | None = None
    host: str = "127.0.0.1"
    port: int = 0
    threads: int | None = None
    gpu_layers: int | str = "auto"
    chunk_tokens: int = 800
    temperature: float = 0.3
    top_p: float = 0.6
    top_k: int = 20
    repetition_penalty: float = 1.05
    max_tokens: int = 2048
    timeout: int = 600
    context_size: int = 4096
    glossary: Path | None = None
    extra_args: list[str] = field(default_factory=list)


@dataclass
class RenderConfig:
    layout: RenderLayout = "single"
    engine: RenderEngine = "xelatex"
    cjk_font: str = "Noto Serif CJK SC"
    template: Path | None = None
    source_ratio: float = 0.48
    source_line_spacing: float = 1.35
    target_line_spacing: float = 1.15
    figure_max_height: float = 0.45
    extra_args: list[str] = field(default_factory=list)


@dataclass
class Config:
    input: Path = Path("inputs")
    output: Path = Path("outputs")
    keep_temp: bool = True
    resume: bool = False
    threads: int | str = "auto"
    parallel: int = 1
    device: Device = "auto"
    gpu_backend: GpuBackend = "auto"
    gpu_index: int | None = None
    mineru: MineruConfig = field(default_factory=MineruConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    render: RenderConfig = field(default_factory=RenderConfig)
    config_path: Path | None = None

    def with_cli_overrides(self, args: Any) -> Config:
        """Return a copy with explicitly provided command-line values applied."""
        changes: dict[str, Any] = {}

        if getattr(args, "output", None) is not None:
            changes["output"] = Path(args.output).expanduser()
        if getattr(args, "resume", False):
            changes["resume"] = True
        if getattr(args, "parallel", None) is not None:
            changes["parallel"] = args.parallel
        if getattr(args, "device", None) is not None:
            changes["device"] = args.device
        if getattr(args, "gpu_backend", None) is not None:
            changes["gpu_backend"] = args.gpu_backend
        if getattr(args, "gpu_index", None) is not None:
            changes["gpu_index"] = args.gpu_index

        if getattr(args, "keep_temp", None) is not None:
            changes["keep_temp"] = args.keep_temp

        threads = getattr(args, "threads", None)
        if getattr(args, "task16", False) and threads is None:
            threads = 16
        if threads is not None:
            changes["threads"] = threads

        mineru_changes: dict[str, Any] = {}
        if getattr(args, "tier", None) is not None:
            mineru_changes["tier"] = args.tier
        if getattr(args, "mineru_python", None) is not None:
            mineru_changes["python"] = Path(args.mineru_python).expanduser()
        if getattr(args, "mineru_model_source", None) is not None:
            mineru_changes["model_source"] = args.mineru_model_source
        if getattr(args, "mineru_model_dir", None) is not None:
            mineru_changes["model_dir"] = Path(args.mineru_model_dir).expanduser()
        translation_changes: dict[str, Any] = {}
        if getattr(args, "model", None) is not None:
            translation_changes["model"] = Path(args.model).expanduser()
        if getattr(args, "server_url", None) is not None:
            translation_changes["server_url"] = args.server_url
        render_changes: dict[str, Any] = {}
        if getattr(args, "layout", None) is not None:
            render_changes["layout"] = args.layout
        if getattr(args, "engine", None) is not None:
            render_changes["engine"] = args.engine
        if getattr(args, "cjk_font", None) is not None:
            render_changes["cjk_font"] = args.cjk_font

        if mineru_changes:
            changes["mineru"] = replace(self.mineru, **mineru_changes)
        if translation_changes:
            changes["translation"] = replace(self.translation, **translation_changes)
        if render_changes:
            changes["render"] = replace(self.render, **render_changes)

        return replace(self, **changes)


def _mapping(value: Any, where: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{where} must be a mapping")
    return value


def _unknown_keys(data: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ConfigError(f"unknown key(s) in {where}: {', '.join(unknown)}")


def _resolve_path(value: Any, base: Path, where: str) -> Path:
    if value is None or str(value).strip() == "":
        raise ConfigError(f"{where} must not be empty")
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _optional_path(value: Any, base: Path) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    return _resolve_path(value, base, "path")


def _optional_runtime_path(value: Any, base: Path) -> Path | None:
    """Resolve a path without following a venv's python symlink."""
    if value is None or str(value).strip() == "":
        return None
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else (base / path)


def _int_or_auto(value: Any, where: str) -> int | str:
    if value == "auto" or value is None:
        return "auto"
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{where} must be an integer or 'auto'") from exc
    if number < 1:
        raise ConfigError(f"{where} must be positive")
    return number


def _parse_config(data: dict[str, Any], base: Path, config_path: Path | None) -> Config:
    _unknown_keys(
        data,
        {
            "version",
            "input",
            "output",
            "keep_temp",
            "resume",
            "threads",
            "parallel",
            "device",
            "gpu_backend",
            "gpu_index",
            "mineru",
            "translation",
            "render",
        },
        "config",
    )
    version = data.get("version", 1)
    if version != 1:
        raise ConfigError(f"unsupported config version: {version!r}")

    raw_mineru = _mapping(data.get("mineru"), "mineru")
    _unknown_keys(
        raw_mineru,
        {
            "tier",
            "device",
            "auto_basic_text_coverage",
            "image_analysis",
            "python",
            "model_source",
            "model_dir",
            "extra_args",
        },
        "mineru",
    )
    raw_translation = _mapping(data.get("translation"), "translation")
    _unknown_keys(
        raw_translation,
        {
            "model",
            "server_bin",
            "server_url",
            "host",
            "port",
            "threads",
            "gpu_layers",
            "chunk_tokens",
            "temperature",
            "top_p",
            "top_k",
            "repetition_penalty",
            "max_tokens",
            "timeout",
            "context_size",
            "glossary",
            "extra_args",
        },
        "translation",
    )
    raw_render = _mapping(data.get("render"), "render")
    _unknown_keys(
        raw_render,
        {
            "layout",
            "engine",
            "cjk_font",
            "template",
            "source_ratio",
            "source_line_spacing",
            "target_line_spacing",
            "figure_max_height",
            "extra_args",
        },
        "render",
    )

    mineru = MineruConfig(
        tier=raw_mineru.get("tier", "auto"),
        device=raw_mineru.get("device"),
        auto_basic_text_coverage=float(raw_mineru.get("auto_basic_text_coverage", 0.8)),
        image_analysis=bool(raw_mineru.get("image_analysis", False)),
        python=_optional_runtime_path(raw_mineru.get("python"), base),
        model_source=raw_mineru.get("model_source", "auto"),
        model_dir=_optional_path(raw_mineru.get("model_dir"), base),
        extra_args=[str(v) for v in raw_mineru.get("extra_args", [])],
    )
    translation = TranslationConfig(
        model=_resolve_path(
            raw_translation.get("model", "models/Hy-MT2-1.8B-Q4_K_M.gguf"),
            base,
            "translation.model",
        ),
        server_bin=str(raw_translation.get("server_bin", "llama-server")),
        server_url=raw_translation.get("server_url") or None,
        host=str(raw_translation.get("host", "127.0.0.1")),
        port=int(raw_translation.get("port", 0)),
        threads=(
            None
            if raw_translation.get("threads") in (None, "auto")
            else int(raw_translation["threads"])
        ),
        gpu_layers=raw_translation.get("gpu_layers", "auto"),
        chunk_tokens=int(raw_translation.get("chunk_tokens", 800)),
        temperature=float(raw_translation.get("temperature", 0.3)),
        top_p=float(raw_translation.get("top_p", 0.6)),
        top_k=int(raw_translation.get("top_k", 20)),
        repetition_penalty=float(raw_translation.get("repetition_penalty", 1.05)),
        max_tokens=int(raw_translation.get("max_tokens", 2048)),
        timeout=int(raw_translation.get("timeout", 600)),
        context_size=int(raw_translation.get("context_size", 4096)),
        glossary=_optional_path(raw_translation.get("glossary"), base),
        extra_args=[str(v) for v in raw_translation.get("extra_args", [])],
    )
    render = RenderConfig(
        layout=raw_render.get("layout", "single"),
        engine=raw_render.get("engine", "xelatex"),
        cjk_font=str(raw_render.get("cjk_font", "Noto Serif CJK SC")),
        template=_optional_path(raw_render.get("template"), base),
        source_ratio=float(raw_render.get("source_ratio", 0.48)),
        source_line_spacing=float(raw_render.get("source_line_spacing", 1.35)),
        target_line_spacing=float(raw_render.get("target_line_spacing", 1.15)),
        figure_max_height=float(raw_render.get("figure_max_height", 0.45)),
        extra_args=[str(v) for v in raw_render.get("extra_args", [])],
    )

    config = Config(
        input=_resolve_path(data.get("input", "inputs"), base, "input"),
        output=_resolve_path(data.get("output", "outputs"), base, "output"),
        keep_temp=bool(data.get("keep_temp", True)),
        resume=bool(data.get("resume", False)),
        threads=_int_or_auto(data.get("threads", "auto"), "threads"),
        parallel=max(1, int(data.get("parallel", 1))),
        device=data.get("device", "auto"),
        gpu_backend=data.get("gpu_backend", "auto"),
        gpu_index=None if data.get("gpu_index") is None else int(data["gpu_index"]),
        mineru=mineru,
        translation=translation,
        render=render,
        config_path=config_path,
    )
    _validate(config)
    return config


def _validate(config: Config) -> None:
    if config.mineru.tier not in {"auto", "flash", "basic", "standard", "advanced"}:
        raise ConfigError("mineru.tier must be auto, flash, basic, standard or advanced")
    if config.mineru.device not in {None, "auto", "cpu", "gpu"}:
        raise ConfigError("mineru.device must be auto, cpu or gpu")
    if config.mineru.model_source not in {"auto", "huggingface", "modelscope", "local"}:
        raise ConfigError("mineru.model_source must be auto, huggingface, modelscope or local")
    if config.device not in {"auto", "cpu", "gpu"}:
        raise ConfigError("device must be auto, cpu or gpu")
    if config.gpu_backend not in {"auto", "cuda", "vulkan", "metal"}:
        raise ConfigError("gpu_backend must be auto, cuda, vulkan or metal")
    if config.render.engine not in {"xelatex", "lualatex", "tectonic", "typst"}:
        raise ConfigError("render.engine must be xelatex, lualatex, tectonic or typst")
    if config.render.layout not in {"single", "bilingual"}:
        raise ConfigError("render.layout must be single or bilingual")
    if not 0.2 <= config.render.source_ratio <= 0.8:
        raise ConfigError("render.source_ratio must be between 0.2 and 0.8")
    if not 0.8 <= config.render.source_line_spacing <= 2.0:
        raise ConfigError("render.source_line_spacing must be between 0.8 and 2.0")
    if not 0.8 <= config.render.target_line_spacing <= 2.0:
        raise ConfigError("render.target_line_spacing must be between 0.8 and 2.0")
    if not 0.1 <= config.render.figure_max_height <= 0.9:
        raise ConfigError("render.figure_max_height must be between 0.1 and 0.9")
    if not 0.0 <= config.mineru.auto_basic_text_coverage <= 1.0:
        raise ConfigError("mineru.auto_basic_text_coverage must be between 0 and 1")
    if not 0.0 <= config.translation.temperature <= 2.0:
        raise ConfigError("translation.temperature must be between 0 and 2")
    if config.translation.chunk_tokens < 100:
        raise ConfigError("translation.chunk_tokens must be at least 100")
    if config.translation.max_tokens < 128:
        raise ConfigError("translation.max_tokens must be at least 128")
    if config.parallel < 1:
        raise ConfigError("parallel must be at least 1")


def find_config(explicit: str | None = None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.exists():
            raise ConfigError(f"config file not found: {path}")
        return path.resolve()
    candidate = Path.cwd() / "config.yaml"
    if candidate.exists():
        return candidate.resolve()
    return None


def load_config(path: str | None = None) -> Config:
    config_path = find_config(path)
    if config_path is None:
        return Config()
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {config_path}: {exc}") from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{config_path} must contain a YAML mapping")
    return _parse_config(raw, config_path.parent, config_path)

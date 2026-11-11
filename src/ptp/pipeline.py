"""End-to-end document pipeline."""

from __future__ import annotations

import json
import logging
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Config
from .devices import DeviceSelection, select_device
from .figures import FigureEntry, prepare_figures, write_fig_comments
from .markdown_tables import html_tables_to_markdown, normalize_math_entities
from .mineru_runner import (
    inspect_text_layer,
    load_structured_content,
    parse_pdf_subprocess,
    resolve_tier,
)
from .render import render_pdf
from .translate import TranslationService, sanitize_text

logger = logging.getLogger(__name__)

_MINERU_LOCK = threading.Lock()


@dataclass
class DocumentResult:
    source: Path
    output_dir: Path
    pdf: Path | None = None
    temp_dir: Path | None = None
    skipped: bool = False
    error: str | None = None
    timings: dict[str, float] = field(default_factory=dict)


class PipelineError(RuntimeError):
    """A document could not be processed."""


def resolve_inputs(config: Config, cli_inputs: list[str] | None) -> list[Path]:
    candidates: list[Path] = []
    if cli_inputs:
        for raw in cli_inputs:
            path = Path(raw).expanduser()
            if path.is_dir():
                candidates.extend(sorted(path.glob("*.pdf")))
            elif path.is_file():
                candidates.append(path)
            else:
                raise PipelineError(f"input not found: {path}")
    else:
        if config.input.is_dir():
            candidates.extend(sorted(config.input.glob("*.pdf")))
        elif config.input.is_file():
            candidates.append(config.input)
        else:
            raise PipelineError(f"input directory or file not found: {config.input}")

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved.suffix.lower() != ".pdf":
            logger.warning("skipping non-PDF input: %s", path)
            continue
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    if not unique:
        raise PipelineError("no PDF inputs found")
    return unique


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def process_document(
    source: Path,
    config: Config,
    selection: DeviceSelection,
) -> DocumentResult:
    stem = source.stem
    output_dir = config.output / f"{stem}_zh"
    temp_dir = output_dir / "temp"
    image_dir = temp_dir / "image"
    en_md = temp_dir / f"{stem}_en.md"
    zh_md = temp_dir / f"{stem}_zh.md"
    content_json = temp_dir / f"{stem}_content_list.json"
    state_path = temp_dir / "state.json"
    pdf_path = output_dir / f"{stem}_zh.pdf"
    result = DocumentResult(source=source, output_dir=output_dir, temp_dir=temp_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)

    state = _load_state(state_path)
    if config.resume and state.get("status") == "completed" and pdf_path.exists():
        logger.info("skip completed: %s", source.name)
        result.pdf = pdf_path
        result.skipped = True
        return result

    state.update(
        {
            "version": 1,
            "source": str(source),
            "stem": stem,
            "status": "running",
            "device": selection.mode,
        }
    )
    _write_state(state_path, state)

    try:
        started = time.perf_counter()
        stats = inspect_text_layer(source)
        tier = resolve_tier(config, selection, stats)
        result.timings["inspect"] = time.perf_counter() - started
        state["tier"] = tier
        state["text_coverage"] = stats.coverage
        state["pages"] = stats.pages
        _write_state(state_path, state)

        figures: list[FigureEntry]
        if config.resume and en_md.exists() and content_json.exists():
            logger.info("reuse MinerU output: %s", source.name)
            markdown = normalize_math_entities(sanitize_text(en_md.read_text(encoding="utf-8")))
            structured = load_structured_content(content_json)
            figures = _figures_from_existing(image_dir, structured)
        else:
            logger.info("PDF -> Markdown: %s (tier=%s)", source.name, tier)
            started = time.perf_counter()
            with _MINERU_LOCK:
                artifacts = parse_pdf_subprocess(source, temp_dir, config, selection, tier)
            result.timings["mineru"] = time.perf_counter() - started
            markdown = normalize_math_entities(
                sanitize_text(artifacts.markdown_path.read_text(encoding="utf-8"))
            )
            structured = load_structured_content(artifacts.structured_content_path)
            figure_result = prepare_figures(structured, artifacts.images_dir, image_dir, markdown)
            markdown = figure_result.markdown
            en_md.write_text(markdown, encoding="utf-8")
            content_json.write_text(
                json.dumps(structured, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            figures = figure_result.figures
            shutil.rmtree(artifacts.directory, ignore_errors=True)
            state["stages"] = {**state.get("stages", {}), "mineru": "completed"}
            _write_state(state_path, state)

        fig_comments = image_dir / "fig_comments.txt"
        if config.resume and zh_md.exists() and fig_comments.exists():
            logger.info("reuse translation: %s", source.name)
        else:
            logger.info("translating: %s", source.name)
            started = time.perf_counter()
            with TranslationService(config, selection) as service:
                zh_text = sanitize_text(service.translate_markdown(markdown))
                zh_md.write_text(zh_text, encoding="utf-8")
                for figure in figures:
                    figure.zh_caption = service.translate_caption(figure.en_caption)
            write_fig_comments(fig_comments, figures)
            result.timings["translate"] = time.perf_counter() - started
            state["stages"] = {**state.get("stages", {}), "translate": "completed"}
            _write_state(state_path, state)

        zh_text = normalize_math_entities(sanitize_text(zh_md.read_text(encoding="utf-8")))
        zh_md.write_text(html_tables_to_markdown(zh_text), encoding="utf-8")
        logger.info("rendering PDF: %s", source.name)
        started = time.perf_counter()
        render_pdf(zh_md, pdf_path, config.render, temp_dir)
        result.timings["render"] = time.perf_counter() - started
        result.pdf = pdf_path
        state["stages"] = {**state.get("stages", {}), "render": "completed"}
        state["status"] = "completed"
        state["timings"] = result.timings
        _write_state(state_path, state)

        if not config.keep_temp:
            shutil.rmtree(temp_dir, ignore_errors=True)
            result.temp_dir = None
        return result
    except Exception as exc:
        state["status"] = "failed"
        state["error"] = str(exc)
        _write_state(state_path, state)
        result.error = str(exc)
        raise


def _figures_from_existing(image_dir: Path, structured: dict) -> list[FigureEntry]:
    """Rebuild caption entries when reusing a previous MinerU run."""
    figures: list[FigureEntry] = []
    seen: set[str] = set()
    for page in structured.get("pages", []):
        for block in page.get("blocks", []):
            if str(block.get("type", "")).lower() not in {"image", "chart"}:
                continue
            source = block.get("image_source") or block.get("image_path")
            if not source:
                continue
            name = Path(str(source)).name
            if name in seen:
                continue
            seen.add(name)
            captions = block.get("captions") or block.get("image_caption") or []
            if isinstance(captions, (str, dict)):
                captions = [captions]
            text = " ".join(
                str((caption.get("content") if isinstance(caption, dict) else caption) or "")
                for caption in captions
            ).strip()
            # The previous run renamed figures to figN.ext in document order.
            filename = f"fig{len(figures) + 1}{Path(name).suffix.lower() or '.jpg'}"
            figures.append(
                FigureEntry(
                    filename=filename,
                    source=str(source),
                    en_caption=text or "[no caption]",
                )
            )
    return figures


def run_pipeline(
    config: Config,
    inputs: list[Path],
    *,
    selection: DeviceSelection | None = None,
    dry_run: bool = False,
) -> list[DocumentResult]:
    if dry_run:
        selection = selection or select_device(config)
        logger.info(
            "dry-run: %d input(s), output=%s, device=%s", len(inputs), config.output, selection.mode
        )
        for path in inputs:
            logger.info("  %s -> %s", path, config.output / f"{path.stem}_zh")
        return []

    results: list[DocumentResult] = []
    pending: list[Path] = []
    for source in inputs:
        output_dir = config.output / f"{source.stem}_zh"
        state_path = output_dir / "temp" / "state.json"
        pdf_path = output_dir / f"{source.stem}_zh.pdf"
        state = _load_state(state_path)
        if config.resume and state.get("status") == "completed" and pdf_path.exists():
            logger.info("skip completed: %s", source.name)
            results.append(
                DocumentResult(
                    source=source,
                    output_dir=output_dir,
                    pdf=pdf_path,
                    skipped=True,
                )
            )
        else:
            pending.append(source)

    if not pending:
        return results

    selection = selection or select_device(config)
    workers = config.parallel
    if selection.mode == "gpu" and workers > 1:
        logger.warning("GPU mode limits parallel documents to 1 to avoid VRAM contention")
        workers = 1
    if workers <= 1:
        for source in pending:
            results.append(process_document(source, config, selection))
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(process_document, source, config, selection): source for source in pending
            }
            for future in as_completed(futures):
                source = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:  # noqa: BLE001 - aggregate per-document failures
                    logger.error("failed: %s: %s", source.name, exc)
                    results.append(
                        DocumentResult(
                            source=source,
                            output_dir=config.output / f"{source.stem}_zh",
                            error=str(exc),
                        )
                    )
    return results

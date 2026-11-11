"""Figure extraction and bilingual figure-caption index generation."""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FigureEntry:
    filename: str
    source: str
    en_caption: str
    zh_caption: str = ""


@dataclass
class FigureResult:
    markdown: str
    figures: list[FigureEntry]
    copied_images: int


def _caption_text(block: dict) -> str:
    captions = (
        block.get("captions")
        or block.get("caption")
        or block.get("image_caption")
        or block.get("img_caption")
        or []
    )
    if isinstance(captions, str):
        return captions.strip()
    if isinstance(captions, dict):
        captions = [captions]
    parts: list[str] = []
    for caption in captions:
        if isinstance(caption, dict):
            text = caption.get("content") or caption.get("text") or ""
        else:
            text = str(caption)
        text = " ".join(str(text).split())
        if text:
            parts.append(text)
    return " ".join(parts).strip()


def _image_source(block: dict) -> str | None:
    for key in ("image_source", "image_path", "img_path", "path"):
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _markdown_image_path_replacements(markdown: str) -> str:
    """Point MinerU's ``images/`` references at our ``image/`` directory."""
    markdown = re.sub(r"(!\[[^\]]*\]\()images/", r"\1image/", markdown)
    markdown = markdown.replace('src="images/', 'src="image/')
    markdown = markdown.replace("src='images/", "src='image/")
    return markdown


def prepare_figures(
    structured_content: dict,
    mineru_images_dir: Path,
    output_images_dir: Path,
    markdown: str,
) -> FigureResult:
    """Copy images, rename figure images, and collect bilingual caption slots."""
    output_images_dir.mkdir(parents=True, exist_ok=True)
    copied = 0

    source_files: dict[str, Path] = {}
    if mineru_images_dir.exists():
        for path in mineru_images_dir.rglob("*"):
            if path.is_file():
                source_files[path.name] = path
                destination = output_images_dir / path.name
                if not destination.exists():
                    shutil.copy2(path, destination)
                copied += 1

    figures: list[FigureEntry] = []
    renamed: dict[str, str] = {}
    seen_sources: set[str] = set()

    for page in structured_content.get("pages", []):
        for block in page.get("blocks", []):
            block_type = str(block.get("type", "")).lower()
            source = _image_source(block)
            if not source:
                continue
            source_name = Path(source).name
            if source_name in seen_sources:
                continue
            seen_sources.add(source_name)
            if block_type not in {"image", "chart"}:
                continue
            original = source_files.get(source_name)
            if original is None:
                logger.warning("MinerU referenced missing image: %s", source)
                continue
            suffix = original.suffix.lower() or ".jpg"
            new_name = f"fig{len(figures) + 1}{suffix}"
            target = output_images_dir / new_name
            if target != original:
                shutil.copy2(original, target)
            # Drop the unrenamed copy that was made while copying all assets.
            if source_name != new_name:
                (output_images_dir / source_name).unlink(missing_ok=True)
            renamed[source_name] = new_name
            figures.append(
                FigureEntry(
                    filename=new_name,
                    source=source,
                    en_caption=_caption_text(block) or "[no caption]",
                )
            )

    for old_name, new_name in renamed.items():
        markdown = markdown.replace(f"images/{old_name}", f"image/{new_name}")
        markdown = markdown.replace(f"({old_name})", f"({new_name})")
    markdown = _markdown_image_path_replacements(markdown)

    return FigureResult(markdown=markdown, figures=figures, copied_images=copied)


def write_fig_comments(path: Path, figures: list[FigureEntry]) -> None:
    lines: list[str] = []
    if not figures:
        lines.append("# No figure captions found.")
    for figure in figures:
        lines.append(figure.filename)
        lines.append("EN: " + " ".join(figure.en_caption.split()))
        lines.append("ZH: " + " ".join((figure.zh_caption or "[translation failed]").split()))
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

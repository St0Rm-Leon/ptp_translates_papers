"""Bilingual two-column layout support."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .config import RenderConfig
from .translate import TranslationService, split_markdown_blocks

logger = logging.getLogger(__name__)

_BLOCK_KIND = Literal[
    "title", "metadata", "text", "figure", "table", "equation", "code", "reference"
]

_IMAGE_ONLY = re.compile(r"^\s*!\[[^\]]*\]\(([^)]+)\)\s*$")
_IMAGE_ANY = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_CAPTION = re.compile(r"^\s*(?:\*\*)?(figure|fig\.?|table|图|表)\s*[\dA-Z]", re.IGNORECASE)
_REF_HEADING = re.compile(
    r"^\s*#{0,6}\s*(references|bibliography|参考文献|引用文献)\s*$", re.IGNORECASE
)
_ABSTRACT = re.compile(
    r"^\s*(#{0,6}\s*)?(\*\*)?(abstract|summary|摘要)(\*\*)?\s*[:：]?", re.IGNORECASE
)
_METADATA_HINTS = re.compile(
    r"(@|orcid|university|institute|centre|center|department|laboratory|faculty|"
    r"e-?mail|received|accepted|published|keywords)",
    re.IGNORECASE,
)


def _looks_like_metadata(block: str) -> bool:
    # Author/affiliation lines can contain <sup>; body paragraphs often do too.
    # Keep the length guard so a long abstract does not stay untranslated.
    return len(block.strip()) < 900 and (
        bool(_METADATA_HINTS.search(block)) or "<sup>" in block.lower()
    )


@dataclass
class BilingualUnit:
    kind: _BLOCK_KIND
    source: str
    translated: str | None = None
    caption: str | None = None
    full_width: bool = False


def _is_code(block: str) -> bool:
    return block.lstrip().startswith("```")


def _is_equation(block: str) -> bool:
    stripped = block.strip()
    return (stripped.startswith("$$") and stripped.endswith("$$")) or (
        stripped.startswith(r"\[") and stripped.endswith(r"\]")
    )


def _is_table(block: str) -> bool:
    stripped = block.strip()
    return "<table" in stripped.lower() or _looks_like_md_table(stripped)


def _looks_like_md_table(block: str) -> bool:
    lines = block.splitlines()
    if len(lines) < 2 or "|" not in lines[0] or "|" not in lines[1]:
        return False
    return bool(re.match(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$", lines[1].strip()))


def _is_image_only(block: str) -> bool:
    return bool(_IMAGE_ONLY.match(block.strip()))


def _image_path(block: str) -> str | None:
    match = _IMAGE_ANY.search(block)
    return match.group(1) if match else None


def _is_caption(block: str) -> bool:
    return bool(_CAPTION.match(block.strip()))


def _is_ref_heading(block: str) -> bool:
    return bool(_REF_HEADING.match(block.strip()))


def _is_abstract(block: str) -> bool:
    return bool(_ABSTRACT.match(block.strip()))


def build_units(markdown: str, translator: TranslationService) -> list[BilingualUnit]:
    """Create paragraph-level source/translation pairs and full-width units."""
    blocks = split_markdown_blocks(markdown)
    units: list[BilingualUnit] = []
    reference_mode = False
    metadata_mode = False
    seen_title = False
    index = 0

    while index < len(blocks):
        block = blocks[index]
        if not block.strip():
            index += 1
            continue

        if reference_mode:
            units.append(BilingualUnit("reference", block, full_width=True))
            index += 1
            continue

        if _is_ref_heading(block):
            reference_mode = True
            units.append(BilingualUnit("reference", block, full_width=True))
            index += 1
            continue

        if _is_image_only(block):
            caption = None
            if index + 1 < len(blocks) and _is_caption(blocks[index + 1]):
                caption = blocks[index + 1]
                index += 1
            units.append(BilingualUnit("figure", block, caption=caption, full_width=True))
            index += 1
            continue

        if _is_caption(block) and index + 1 < len(blocks) and _is_table(blocks[index + 1]):
            table_source = blocks[index + 1]
            units.append(
                BilingualUnit(
                    "table",
                    _normalize_table(table_source),
                    caption=block,
                    full_width=True,
                )
            )
            index += 2
            continue

        if _is_table(block):
            caption = None
            if index + 1 < len(blocks) and _is_caption(blocks[index + 1]):
                caption = blocks[index + 1]
                index += 1
            units.append(
                BilingualUnit(
                    "table",
                    _normalize_table(block),
                    caption=caption,
                    full_width=True,
                )
            )
            index += 1
            continue

        if _is_equation(block):
            units.append(BilingualUnit("equation", block, full_width=True))
            index += 1
            continue

        if _is_code(block) or "<details" in block.lower():
            units.append(BilingualUnit("code", block, full_width=True))
            index += 1
            continue

        if not seen_title:
            if block.lstrip().startswith("#"):
                translated = translator.translate_block(block)
                units.append(
                    BilingualUnit("title", block, translated=translated, full_width=True)
                )
                seen_title = True
                metadata_mode = True
                index += 1
                continue
            if len(block.strip()) > 300:
                seen_title = True
                metadata_mode = False
                # Fall through and treat this long block as body text.
            else:
                units.append(BilingualUnit("metadata", block, full_width=True))
                index += 1
                continue

        if metadata_mode:
            if (
                _is_abstract(block)
                or block.lstrip().startswith("#")
                or (len(block.strip()) > 300 and not _looks_like_metadata(block))
            ):
                metadata_mode = False
            else:
                units.append(BilingualUnit("metadata", block, full_width=True))
                index += 1
                continue

        translated = translator.translate_block(block)
        units.append(BilingualUnit("text", block, translated=translated))
        index += 1

    return units


def _normalize_table(block: str) -> str:
    # Keep raw HTML tables so Pandoc can preserve rowspan/colspan as
    # \multirow/\multicolumn when converting to LaTeX.
    return block.strip()


def _markdown_to_latex(block: str) -> str:
    # Noto Serif CJK SC lacks U+2217; use an ASCII asterisk in titles/metadata.
    block = block.replace("\u2217", "*").replace("\u2009", " ")
    pandoc = shutil.which("pandoc")
    if pandoc is None:
        raise RuntimeError("pandoc is required for bilingual layout")
    proc = subprocess.run(
        [
            pandoc,
            "-f",
            "markdown+tex_math_dollars+raw_html+pipe_tables",
            "-t",
            "latex",
            "--wrap=none",
        ],
        input=block,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "pandoc block conversion failed")
    return proc.stdout.strip()


def _title_latex(source: str, translated: str | None) -> str:
    source_text = _markdown_to_latex(re.sub(r"^\s*#+\s*", "", source.strip()))
    translated_text = _markdown_to_latex(re.sub(r"^\s*#+\s*", "", (translated or "").strip()))
    lines = [r"\begin{center}", rf"{{\LARGE\bfseries {source_text}}}"]
    if translated_text:
        lines.append(r"\\[0.35em]")
        lines.append(rf"{{\Large\bfseries {translated_text}}}")
    lines.append(r"\end{center}")
    return "\n".join(lines)


def _figure_latex(unit: BilingualUnit, config: RenderConfig) -> str:
    path = _image_path(unit.source)
    if not path:
        return _markdown_to_latex(unit.source)
    lines = [
        r"\begin{center}",
        rf"\includegraphics[width=0.85\fullwidth,height={config.figure_max_height:.2f}\textheight,keepaspectratio]{{{path}}}",
    ]
    if unit.caption:
        lines.append(rf"\captionof{{figure}}{{{_markdown_to_latex(unit.caption)}}}")
    lines.append(r"\end{center}")
    return "\n".join(lines)


def _html_table_to_latex(table_html: str) -> str:
    pandoc = shutil.which("pandoc")
    if pandoc is None:
        raise RuntimeError("pandoc is required for bilingual layout")
    proc = subprocess.run(
        [pandoc, "-f", "html", "-t", "latex", "--wrap=none"],
        input=table_html,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "pandoc HTML table conversion failed")
    return proc.stdout.strip()


def _table_latex(unit: BilingualUnit) -> str:
    if "<table" in unit.source.lower():
        table_latex = _html_table_to_latex(unit.source)
    else:
        table_latex = _markdown_to_latex(unit.source)
    lines = [r"\begin{center}"]
    if unit.caption:
        lines.append(rf"\captionof{{table}}{{{_markdown_to_latex(unit.caption)}}}")
        lines.append(r"\par")
    lines.extend([r"\small", table_latex, r"\end{center}"])
    return "\n".join(lines)


class _TexBuilder:
    def __init__(self, config: RenderConfig) -> None:
        self.config = config
        self.lines: list[str] = []
        self.paracol_open = False

    def open_paracol(self) -> None:
        if not self.paracol_open:
            self.lines.extend([r"\begin{paracol}{2}", ""])
            self.paracol_open = True

    def close_paracol(self) -> None:
        if self.paracol_open:
            self.lines.extend([r"\end{paracol}", ""])
            self.paracol_open = False

    def add_pair(self, source: str, translated: str) -> None:
        self.open_paracol()
        self.lines.extend(
            [
                rf"\linespread{{{self.config.source_line_spacing:.2f}}}\selectfont",
                source,
                "",
                r"\switchcolumn",
                "",
                rf"\linespread{{{self.config.target_line_spacing:.2f}}}\selectfont",
                translated,
                "",
                r"\switchcolumn[0]*",
                "",
            ]
        )

    def add_full_width(self, content: str) -> None:
        self.close_paracol()
        self.lines.extend([content, ""])

    def result(self) -> str:
        self.close_paracol()
        return "\n".join(self.lines).rstrip() + "\n"


def build_bilingual_tex(units: list[BilingualUnit], config: RenderConfig) -> str:
    builder = _TexBuilder(config)
    for unit in units:
        if unit.kind == "title":
            builder.add_full_width(_title_latex(unit.source, unit.translated))
        elif unit.kind in {"metadata", "reference", "equation", "code"}:
            builder.add_full_width(_markdown_to_latex(unit.source))
        elif unit.kind == "figure":
            builder.add_full_width(_figure_latex(unit, config))
        elif unit.kind == "table":
            builder.add_full_width(_table_latex(unit))
        else:
            builder.add_pair(
                _markdown_to_latex(unit.source),
                _markdown_to_latex(unit.translated or unit.source),
            )
    return builder.result()


def bilingual_preamble(config: RenderConfig) -> str:
    ratio = config.source_ratio
    font = config.cjk_font
    return "\n".join(
        [
            r"\documentclass[10pt,a4paper]{article}",
            r"\usepackage[a4paper,margin=1.6cm]{geometry}",
            r"\usepackage{fontspec}",
            r"\usepackage{xeCJK}",
            rf"\setmainfont{{{font}}}",
            rf"\setCJKmainfont{{{font}}}",
            r"\usepackage{paracol}",
            r"\usepackage{setspace}",
            r"\usepackage{graphicx}",
            r"\usepackage{caption}",
            r"\usepackage{booktabs}",
            r"\usepackage{longtable}",
            r"\usepackage{array}",
            r"\usepackage{multirow}",
            r"\usepackage{calc}",
            r"\usepackage{amsmath,amssymb}",
            r"\usepackage{hyperref}",
            r"\newcounter{none}",
            rf"\columnratio{{{ratio:.3f},{1 - ratio:.3f}}}",
            r"\setlength{\columnsep}{1.2em}",
            r"\captionsetup{font=small,labelfont=bf,labelformat=empty}",
            r"\newlength{\fullwidth}",
            r"\setlength{\fullwidth}{\textwidth}",
            r"\setlength{\parindent}{0pt}",
            r"\setlength{\parskip}{0.35em}",
            r"\makeatletter",
            r"\newsavebox\pandoc@box",
            r"\newcommand*\pandocbounded[1]{%",
            r"  \sbox\pandoc@box{#1}%",
            r"  \Gscale@div\@tempa{\textheight}{\dimexpr\ht\pandoc@box+\dp\pandoc@box\relax}%",
            r"  \Gscale@div\@tempb{\linewidth}{\wd\pandoc@box}%",
            r"  \ifdim\@tempb\p@<\@tempa\p@\let\@tempa\@tempb\fi%",
            r"  \ifdim\@tempa\p@<\p@\scalebox{\@tempa}{\usebox\pandoc@box}%",
            r"  \else\usebox{\pandoc@box}%",
            r"  \fi%",
            r"}",
            r"\makeatother",
            r"\setcounter{secnumdepth}{-\maxdimen}",
            r"\providecommand{\tightlist}{\setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}",
            r"\setlength{\emergencystretch}{2em}",
            r"\sloppy",
            r"\pagestyle{plain}",
            r"\begin{document}",
            "",
        ]
    )


def render_bilingual_pdf(
    units: list[BilingualUnit],
    output_pdf: Path,
    config: RenderConfig,
    resource_dir: Path,
    stem: str,
) -> None:
    if config.engine != "xelatex":
        raise RuntimeError("bilingual layout currently requires render.engine=xelatex")
    resource_dir = resource_dir.resolve()
    output_pdf = output_pdf.resolve()
    tex_path = resource_dir / f"{stem}_bilingual.tex"
    tex_path.write_text(
        bilingual_preamble(config) + build_bilingual_tex(units, config) + "\n\\end{document}\n",
        encoding="utf-8",
    )
    pdf_name = f"{stem}_bilingual.pdf"
    cmd = [
        "xelatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-output-directory",
        str(resource_dir),
        tex_path.name,
    ]
    logger.info("rendering bilingual PDF with xelatex")
    for _ in range(2):
        proc = subprocess.run(
            cmd,
            cwd=resource_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if proc.returncode != 0:
            tail = "\n".join((proc.stdout + "\n" + proc.stderr).splitlines()[-50:])
            raise RuntimeError(f"xelatex failed (exit {proc.returncode}):\n{tail}")
    built_pdf = resource_dir / pdf_name
    if not built_pdf.exists():
        raise RuntimeError("xelatex produced no bilingual PDF")
    built_pdf.replace(output_pdf)

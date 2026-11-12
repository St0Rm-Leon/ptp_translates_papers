"""Bilingual two-column layout support."""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .compat import resolve_tool, subprocess_text_options
from .config import RenderConfig
from .markdown_tables import inline_html_to_latex_markdown
from .translate import TranslationService, split_markdown_blocks

logger = logging.getLogger(__name__)

_BLOCK_KIND = Literal[
    "title",
    "metadata",
    "text",
    "figure",
    "table",
    "equation",
    "code",
    "reference",
    "footnote",
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
_TERMINAL_PUNCTUATION = re.compile(r"[.!?。！？:：;；][\"'”’)\]]*\s*$")
_LOWERCASE_START = re.compile(r"^[a-z]")
_LIST_ITEM_START = re.compile(r"^\s*(?:[•·]|[-*]\s|\d+[.)]\s|[A-Z][.)]\s)")


def _is_page_footnote(block: str) -> bool:
    lowered = block.lower()
    return (
        'data-block-type="page_footnote"' in lowered
        or "docvortex-page-footnote" in lowered
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

        if _is_page_footnote(block) and seen_title:
            units.append(BilingualUnit("footnote", block, full_width=True))
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

    return _merge_continuation_units(units, translator)


def _merge_continuation_units(
    units: list[BilingualUnit], translator: TranslationService
) -> list[BilingualUnit]:
    """Join paragraphs that MinerU split at a page/column or figure boundary.

    When a text unit ends mid-sentence and the next text unit (possibly after
    a figure/table) starts lowercase, translate them as one paragraph.  The
    merged paragraph is placed after the intervening figure/table, matching
    the original reading order.
    """
    merged: list[BilingualUnit] = []
    index = 0
    while index < len(units):
        unit = units[index]
        if (
            unit.kind != "text"
            or _TERMINAL_PUNCTUATION.search(unit.source.strip())
            or _LIST_ITEM_START.match(unit.source)
        ):
            merged.append(unit)
            index += 1
            continue

        look = index + 1
        while look < len(units) and units[look].kind in {"figure", "table"}:
            look += 1
        if (
            look < len(units)
            and units[look].kind == "text"
            and _LOWERCASE_START.match(units[look].source.lstrip())
        ):
            previous = unit.source.rstrip()
            following = units[look].source.lstrip()
            separator = "" if previous.endswith("-") else " "
            combined_source = previous + separator + following
            logger.debug(
                "merged continuation paragraph: %s", combined_source[:80].replace("\n", " ")
            )
            translated = translator.translate_block(combined_source)
            merged.extend(units[index + 1 : look])
            merged.append(
                BilingualUnit("text", combined_source, translated=translated)
            )
            index = look + 1
            continue

        merged.append(unit)
        index += 1
    return merged


def _normalize_table(block: str) -> str:
    # Keep raw HTML tables so Pandoc can preserve rowspan/colspan as
    # \multirow/\multicolumn when converting to LaTeX.
    return block.strip()


def _markdown_to_latex(block: str, pandoc: str | None = None) -> str:
    # Noto Serif CJK SC lacks U+2217; use an ASCII asterisk in titles/metadata.
    block = block.replace("\u2217", "*").replace("\u2009", " ")
    block = inline_html_to_latex_markdown(block)
    executable = resolve_tool(pandoc or "pandoc")
    if executable is None:
        raise RuntimeError("pandoc is required for bilingual layout")
    proc = subprocess.run(
        [
            executable,
            "-f",
            "markdown+tex_math_dollars+raw_html+pipe_tables",
            "-t",
            "latex",
            "--wrap=none",
            "--syntax-highlighting=none",
        ],
        input=block,
        capture_output=True,
        check=False,
        **subprocess_text_options(),
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "pandoc block conversion failed")
    return proc.stdout.strip()


def _title_latex(source: str, translated: str | None, pandoc: str | None = None) -> str:
    source_text = _markdown_to_latex(re.sub(r"^\s*#+\s*", "", source.strip()), pandoc)
    translated_text = _markdown_to_latex(
        re.sub(r"^\s*#+\s*", "", (translated or "").strip()), pandoc
    )
    lines = [r"\begin{center}", rf"{{\LARGE\bfseries {source_text}}}"]
    if translated_text:
        lines.append(r"\\[0.35em]")
        lines.append(rf"{{\Large\bfseries {translated_text}}}")
    lines.append(r"\end{center}")
    return "\n".join(lines)


def _figure_latex(
    unit: BilingualUnit, config: RenderConfig, pandoc: str | None = None
) -> str:
    path = _image_path(unit.source)
    if not path:
        return _markdown_to_latex(unit.source, pandoc)
    lines = [
        r"\begin{center}",
        rf"\includegraphics[width=0.85\fullwidth,height={config.figure_max_height:.2f}\textheight,keepaspectratio]{{{path}}}",
    ]
    if unit.caption:
        lines.append(
            rf"\captionof{{figure}}{{{_markdown_to_latex(unit.caption, pandoc)}}}"
        )
    lines.append(r"\end{center}")
    return "\n".join(lines)


def _html_table_to_latex(table_html: str, pandoc: str | None = None) -> str:
    executable = resolve_tool(pandoc or "pandoc")
    if executable is None:
        raise RuntimeError("pandoc is required for bilingual layout")
    proc = subprocess.run(
        [
            executable,
            "-f",
            "html",
            "-t",
            "latex",
            "--wrap=none",
            "--syntax-highlighting=none",
        ],
        input=table_html,
        capture_output=True,
        check=False,
        **subprocess_text_options(),
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "pandoc HTML table conversion failed")
    return proc.stdout.strip()


def _table_latex(unit: BilingualUnit, pandoc: str | None = None) -> str:
    if "<table" in unit.source.lower():
        table_latex = _html_table_to_latex(unit.source, pandoc)
    else:
        table_latex = _markdown_to_latex(unit.source, pandoc)
    lines = [r"\begin{center}"]
    if unit.caption:
        lines.append(
            rf"\captionof{{table}}{{{_markdown_to_latex(unit.caption, pandoc)}}}"
        )
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


def _notes_latex(units: list[BilingualUnit], pandoc: str | None = None) -> str:
    lines = [r"\section*{Notes / 注释}", r"{\small"]
    for unit in units:
        lines.append(_markdown_to_latex(unit.source, pandoc))
        lines.append("")
    lines.append("}")
    return "\n".join(lines)


def build_bilingual_tex(
    units: list[BilingualUnit], config: RenderConfig, pandoc: str | None = None
) -> str:
    builder = _TexBuilder(config)
    footnotes = [unit for unit in units if unit.kind == "footnote"]
    for unit in units:
        if unit.kind == "footnote":
            continue
        if unit.kind == "title":
            builder.add_full_width(_title_latex(unit.source, unit.translated, pandoc))
        elif unit.kind in {"metadata", "reference", "equation", "code"}:
            builder.add_full_width(_markdown_to_latex(unit.source, pandoc))
        elif unit.kind == "figure":
            builder.add_full_width(_figure_latex(unit, config, pandoc))
        elif unit.kind == "table":
            builder.add_full_width(_table_latex(unit, pandoc))
        else:
            builder.add_pair(
                _markdown_to_latex(unit.source, pandoc),
                _markdown_to_latex(unit.translated or unit.source, pandoc),
            )
    if footnotes:
        builder.add_full_width(_notes_latex(footnotes, pandoc))
    return builder.result()


def bilingual_preamble(config: RenderConfig) -> str:
    ratio = config.source_ratio
    if config.cjk_font_file is not None:
        font_dir = config.cjk_font_file.parent.as_posix()
        if not font_dir.endswith("/"):
            font_dir += "/"
        options = [f"Path={{{font_dir}}}"]
        if config.cjk_font_bold_file is not None:
            options.append(f"BoldFont={{{config.cjk_font_bold_file.name}}}")
        option_text = ",".join(options)
        main_font = rf"\setmainfont[{option_text}]{{{config.cjk_font_file.name}}}"
        cjk_font = rf"\setCJKmainfont[{option_text}]{{{config.cjk_font_file.name}}}"
    else:
        main_font = rf"\setmainfont{{{config.cjk_font}}}"
        cjk_font = rf"\setCJKmainfont{{{config.cjk_font}}}"
    return "\n".join(
        [
            r"\documentclass[10pt,a4paper]{article}",
            r"\usepackage[a4paper,margin=1.6cm]{geometry}",
            r"\usepackage{fontspec}",
            r"\usepackage{xeCJK}",
            main_font,
            cjk_font,
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
) -> None:
    if config.engine != "xelatex":
        raise RuntimeError("bilingual layout currently requires render.engine=xelatex")
    pandoc = resolve_tool(config.pandoc or "pandoc")
    if pandoc is None:
        raise RuntimeError("pandoc is required for bilingual layout")
    xelatex = resolve_tool(config.xelatex or "xelatex")
    if xelatex is None:
        raise RuntimeError(
            "xelatex not found; install TeX Live/MiKTeX or set render.xelatex"
        )
    resource_dir = resource_dir.resolve()
    output_pdf = output_pdf.resolve()
    # Use ASCII temporary names so XeLaTeX on Windows is not asked to open a
    # .tex file whose name comes from an arbitrary (possibly CJK) PDF stem.
    tex_path = resource_dir / "_ptp_bilingual.tex"
    tex_path.write_text(
        bilingual_preamble(config)
        + build_bilingual_tex(units, config, pandoc)
        + "\n\\end{document}\n",
        encoding="utf-8",
    )
    pdf_name = "_ptp_bilingual.pdf"
    cmd = [
        xelatex,
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
            timeout=600,
            **subprocess_text_options(),
        )
        if proc.returncode != 0:
            tail = "\n".join((proc.stdout + "\n" + proc.stderr).splitlines()[-50:])
            raise RuntimeError(f"xelatex failed (exit {proc.returncode}):\n{tail}")
    built_pdf = resource_dir / pdf_name
    if not built_pdf.exists():
        raise RuntimeError("xelatex produced no bilingual PDF")
    try:
        built_pdf.replace(output_pdf)
    except OSError as exc:
        raise RuntimeError(
            f"could not move bilingual PDF to {output_pdf}: {exc}; "
            "close the PDF if it is open in a viewer"
        ) from exc

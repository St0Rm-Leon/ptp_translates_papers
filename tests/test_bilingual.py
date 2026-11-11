from ptp.bilingual import BilingualUnit, build_bilingual_tex, build_units
from ptp.config import RenderConfig


class FakeTranslator:
    def translate_block(self, block: str) -> str:
        return "译文：" + block


def _source() -> str:
    return (
        "# A Test Paper\n\n"
        "Alice Example and Bob Example\n\n"
        "Example Institute\n\n"
        "## Abstract\n\n"
        "This is a long abstract paragraph that should be paired in two columns. "
        "It is intentionally longer than three hundred characters. "
        "The abstract continues with more technical text. "
        "The abstract continues with more technical text. "
        "The abstract continues with more technical text. "
        "The abstract continues with more technical text.\n\n"
        "## INTRODUCTION\n\n"
        "A source paragraph.\n\n"
        "![](image/fig1.jpg)\n\n"
        "Figure 1. A source figure caption.\n\n"
        "Table 1. A source table caption.\n\n"
        "<table><tr><th>Material</th><th>Value</th></tr>"
        "<tr><td>Iron</td><td>7.87</td></tr></table>\n\n"
        "## REFERENCES\n\n"
        "1. A source reference."
    )


def test_build_units_pairs_text_and_keeps_figures_tables_original():
    units = build_units(_source(), FakeTranslator())
    kinds = [unit.kind for unit in units]
    assert kinds[0] == "title"
    assert "metadata" in kinds
    assert "figure" in kinds
    assert "table" in kinds
    assert "reference" in kinds

    figure = next(unit for unit in units if unit.kind == "figure")
    assert figure.caption and "Figure 1" in figure.caption
    table = next(unit for unit in units if unit.kind == "table")
    assert table.caption and "Table 1" in table.caption
    assert "Material" in table.source
    assert table.translated is None

    for unit in units:
        if unit.kind == "text":
            assert unit.translated and unit.translated.startswith("译文：")


def test_build_bilingual_tex_has_columns_and_full_width_blocks():
    units = build_units(_source(), FakeTranslator())
    tex = build_bilingual_tex(units, RenderConfig(layout="bilingual"))
    assert r"\begin{paracol}{2}" in tex
    assert r"\switchcolumn" in tex
    assert r"\switchcolumn[0]*" in tex
    assert r"\includegraphics" in tex
    assert r"\captionof{figure}" in tex
    assert r"\captionof{table}" in tex
    assert "A source figure caption" in tex
    assert "A source table caption" in tex
    assert "A source reference." in tex
    assert "译文：A source paragraph." in tex
    assert "译文：A source reference." not in tex


def test_page_footnote_is_collected_into_notes_section():
    footnote = (
        '<small><span class="docvortex-page-footnote" '
        'data-block-type="page_footnote" style="color:#6b7280">'
        "Received 30 October 2022; Accepted 11 February 2023"
        "</span></small>"
    )
    units = build_units(_source() + "\n\n" + footnote, FakeTranslator())
    note = next(unit for unit in units if unit.kind == "footnote")
    assert note.translated is None
    assert "Received 30 October 2022" in note.source

    tex = build_bilingual_tex(units, RenderConfig(layout="bilingual"))
    assert r"\section*{Notes / 注释}" in tex
    assert "Received 30 October 2022" in tex
    assert tex.index("A source reference.") < tex.index(r"\section*{Notes / 注释}")


def test_continuation_after_figure_is_merged():
    prefix = "The first part ends mid sentence, " + "technical detail. " * 20
    source = (
        "# A Test Paper\n\n"
        f"{prefix}In the workshop,\n\n"
        "![](image/fig1.jpg)\n\n"
        "Figure 1. A source figure caption.\n\n"
        "the second part continues with lowercase text.\n"
    )
    units = build_units(source, FakeTranslator())
    text_units = [unit for unit in units if unit.kind == "text"]
    assert len(text_units) == 1
    assert "In the workshop, the second part" in text_units[0].source
    assert text_units[0].translated and text_units[0].translated.startswith("译文：")

    figure_index = next(i for i, unit in enumerate(units) if unit.kind == "figure")
    text_index = next(i for i, unit in enumerate(units) if unit.kind == "text")
    assert figure_index < text_index


def test_complete_paragraph_is_not_merged_across_figure():
    prefix = "The first part ends here. " + "Additional detail. " * 20
    source = (
        "# A Test Paper\n\n"
        f"{prefix}\n\n"
        "![](image/fig1.jpg)\n\n"
        "Figure 1. A source figure caption.\n\n"
        "the next paragraph starts here.\n"
    )
    units = build_units(source, FakeTranslator())
    assert len([unit for unit in units if unit.kind == "text"]) == 2


def test_sup_and_sub_tags_become_latex_commands():
    units = [
        BilingualUnit(
            "text",
            "exposure<sup>2</sup> and 222<sub>Rn</sub>",
            translated="暴露<sup>2</sup>和 222<sub>Rn</sub>",
        )
    ]
    tex = build_bilingual_tex(units, RenderConfig(layout="bilingual"))
    assert r"exposure\textsuperscript{2}" in tex
    assert r"222\textsubscript{Rn}" in tex
    assert r"暴露\textsuperscript{2}" in tex

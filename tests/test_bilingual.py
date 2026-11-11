from ptp.bilingual import build_bilingual_tex, build_units
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

from ptp.markdown_tables import (
    html_tables_to_markdown,
    inline_html_to_latex,
    inline_html_to_latex_markdown,
    normalize_math_entities,
)


def test_html_table_with_rowspan_and_colspan_becomes_pipe_table():
    html = (
        "<table>"
        '<tr><td rowspan="2">Distance</td><td colspan="2">Facing</td></tr>'
        "<tr><td>C</td><td>Value</td></tr>"
        "<tr><td>0.5</td><td>5.8</td><td>0.0076</td></tr>"
        "</table>"
    )
    markdown = html_tables_to_markdown("Before.\n\n" + html + "\n\nAfter.")
    assert "<table" not in markdown
    assert "| Distance | Facing | Facing |" in markdown
    assert "|---|---|---|" in markdown
    assert "| 0.5 | 5.8 | 0.0076 |" in markdown
    assert "Before." in markdown
    assert "After." in markdown


def test_pipe_characters_are_escaped():
    html = "<table><tr><th>Name</th></tr><tr><td>A | B</td></tr></table>"
    markdown = html_tables_to_markdown(html)
    assert r"A \| B" in markdown


def test_text_without_tables_is_unchanged():
    text = "# Title\n\nNo table here.\n"
    assert html_tables_to_markdown(text) == text


def test_math_entities_are_decoded_but_prose_is_not():
    text = "$$a &lt; b$$\n\nOutside &lt; stays."
    normalized = normalize_math_entities(text)
    assert "$$a < b$$" in normalized
    assert "Outside &lt; stays." in normalized


def test_inline_sup_and_sub_become_latex_commands():
    assert inline_html_to_latex("10 m<sup>3</sup>/kg") == r"10 m\textsuperscript{3}/kg"
    assert inline_html_to_latex("222<sub>Rn</sub>") == r"222\textsubscript{Rn}"
    assert inline_html_to_latex("<sup>1,2</sup>") == r"\textsuperscript{1,2}"


def test_inline_html_conversion_skips_fenced_code():
    text = "```\n<sup>1</sup>\n```\n\nA<sup>2</sup>"
    converted = inline_html_to_latex_markdown(text)
    assert "<sup>1</sup>" in converted
    assert r"A\textsuperscript{2}" in converted

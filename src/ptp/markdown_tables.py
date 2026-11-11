"""Convert MinerU HTML tables into Pandoc-friendly Markdown pipe tables."""

from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup, Tag

_MATH_SPAN = re.compile(r"(\$\$.*?\$\$|\$[^$\n]+\$)", re.DOTALL)
_TABLE_BLOCK = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)


def normalize_math_entities(text: str) -> str:
    """Decode HTML entities inside math spans before handing them to LaTeX."""
    return _MATH_SPAN.sub(lambda match: html.unescape(match.group(0)), text)


def _cell_text(cell: Tag) -> str:
    text = cell.get_text(" ", strip=True)
    return " ".join(text.split()).replace("|", r"\|")


def _table_to_markdown(table: Tag) -> str:
    rows = table.find_all("tr")
    if not rows:
        return ""
    grid: list[list[str | None]] = [[] for _ in rows]
    max_cols = 0

    def ensure(row: int, col: int) -> None:
        nonlocal max_cols
        if row >= len(grid):
            return
        while len(grid[row]) <= col:
            grid[row].append(None)
        max_cols = max(max_cols, col + 1)

    for row_index, row in enumerate(rows):
        col = 0
        cells = row.find_all(["th", "td"], recursive=False)
        for cell in cells:
            while col < len(grid[row_index]) and grid[row_index][col] is not None:
                col += 1
            text = _cell_text(cell)
            try:
                rowspan = max(1, int(cell.get("rowspan", 1)))
            except (TypeError, ValueError):
                rowspan = 1
            try:
                colspan = max(1, int(cell.get("colspan", 1)))
            except (TypeError, ValueError):
                colspan = 1
            for rr in range(row_index, row_index + rowspan):
                for cc in range(col, col + colspan):
                    ensure(rr, cc)
                    # Repeat a colspan value so Markdown/Pandoc keeps readable
                    # headers; leave rowspan continuation cells blank.
                    if rr == row_index:
                        grid[rr][cc] = text
                    elif grid[rr][cc] is None:
                        grid[rr][cc] = ""
            col += colspan

    if max_cols == 0:
        return ""
    normalized: list[list[str]] = []
    for row in grid:
        values = ["" if value is None else str(value) for value in row[:max_cols]]
        values.extend([""] * (max_cols - len(values)))
        normalized.append(values)
    if not any(any(cell for cell in row) for row in normalized):
        return ""

    header = normalized[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join(["---"] * max_cols) + "|",
    ]
    for row in normalized[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def html_tables_to_markdown(text: str) -> str:
    if "<table" not in text.lower():
        return text

    def replace_table(match: re.Match[str]) -> str:
        soup = BeautifulSoup(match.group(0), "html.parser")
        table = soup.find("table")
        if table is None:
            return match.group(0)
        markdown = _table_to_markdown(table)
        return "\n\n" + markdown + "\n\n" if markdown else ""

    return _TABLE_BLOCK.sub(replace_table, text)

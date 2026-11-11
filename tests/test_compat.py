from pathlib import Path

from ptp import compat


def test_subprocess_text_options_force_utf8():
    options = compat.subprocess_text_options()
    assert options["text"] is True
    assert options["encoding"] == "utf-8"
    assert options["errors"] == "replace"


def test_utf8_env_sets_python_io(monkeypatch):
    monkeypatch.setenv("EXISTING", "1")
    env = compat.utf8_env()
    assert env["EXISTING"] == "1"
    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_resolve_tool_uses_path_for_bare_names(monkeypatch):
    monkeypatch.setattr(compat.shutil, "which", lambda name: f"/resolved/{name}")
    assert compat.resolve_tool("pandoc") == "/resolved/pandoc"


def test_resolve_tool_uses_existing_path(tmp_path: Path):
    tool = tmp_path / "tools" / "pandoc.exe"
    tool.parent.mkdir()
    tool.write_text("", encoding="utf-8")
    assert compat.resolve_tool(tool) == str(tool)
    assert compat.resolve_tool(tmp_path / "tools" / "missing.exe") is None

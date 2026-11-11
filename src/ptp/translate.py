"""Chunked Markdown translation through a local llama.cpp server."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType
from typing import Self
from urllib.error import URLError
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup, NavigableString

from .config import Config
from .devices import DeviceSelection, select_device

logger = logging.getLogger(__name__)

DEFAULT_HF_REPO = "tencent/Hy-MT2-1.8B-GGUF"
DEFAULT_HF_FILE = "Hy-MT2-1.8B-Q4_K_M.gguf"

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？])\s+")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ufffe\uffff]")
_PLACEHOLDER_TOKEN = "@@P{}@@"
_PLACEHOLDER_RE = re.compile(r"@@P\d+@@")
_SEGMENT_MIN_LETTERS = 3
_MAX_FALLBACK_SEGMENTS = 80
_PROSE_HINT = re.compile(
    r"\b(?:the|of|and|in|is|are|was|were|for|with|to|a|an|this|that|we|it|as|by|on|from)\b",
    re.IGNORECASE,
)


def sanitize_text(text: str) -> str:
    """Remove PDF-extraction control characters that break LaTeX."""
    return _CONTROL_CHARS.sub("", text)


_PROTECT_PATTERNS = (
    (re.compile(r"\$\$.*?\$\$", re.DOTALL), "math"),
    (re.compile(r"!\[[^\]]*\]\([^)]+\)"), "image"),
    (re.compile(r"\[[^\]]+\]\([^)]+\)"), "link"),
    (re.compile(r"`[^`\n]+`"), "code"),
    (re.compile(r"\$[^$\n]+\$"), "math"),
    (re.compile(r"\[\d+(?:[-,]\d+)*\]"), "citation"),
    (re.compile(r"https?://\S+"), "url"),
)


class TranslationError(RuntimeError):
    """Translation server or translation output failed validation."""


def estimate_tokens(text: str) -> int:
    """Rough token estimate used only for chunk sizing."""
    words = len(re.findall(r"[A-Za-z0-9_]+", text))
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    return max(1, words + cjk)


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def _protect(text: str) -> tuple[str, dict[str, str]]:
    protected = text
    values: dict[str, str] = {}
    counter = 0
    for pattern, _kind in _PROTECT_PATTERNS:

        def repl(match: re.Match[str]) -> str:
            nonlocal counter
            token = _PLACEHOLDER_TOKEN.format(counter)
            values[token] = match.group(0)
            counter += 1
            return token

        protected = pattern.sub(repl, protected)
    return protected, values


def _restore(text: str, values: dict[str, str]) -> str:
    restored = text
    missing = []
    for token, value in values.items():
        if token not in restored:
            missing.append(token)
        restored = restored.replace(token, value)
    if missing:
        raise TranslationError(
            f"model dropped {len(missing)} protected placeholder(s): {missing[:5]}"
        )
    return restored


def _split_protected(text: str) -> list[tuple[str, bool]]:
    """Split text into plain and protected pieces using the protection rules."""
    protected, values = _protect(text)
    pieces: list[tuple[str, bool]] = []
    last = 0
    for match in _PLACEHOLDER_RE.finditer(protected):
        token = match.group(0)
        if token not in values:
            continue
        if match.start() > last:
            pieces.append((protected[last : match.start()], False))
        pieces.append((values[token], True))
        last = match.end()
    if last < len(protected):
        pieces.append((protected[last:], False))
    return pieces


def _segment_is_translatable(text: str) -> bool:
    """Skip whitespace, punctuation, units and short identifiers."""
    stripped = text.strip()
    if not stripped:
        return False
    letters = re.findall(r"[A-Za-z]", stripped)
    if len(letters) < _SEGMENT_MIN_LETTERS:
        return False
    compact = stripped.strip(".,;:()[]{}")
    short_unit = (
        len(letters) <= 5 and re.fullmatch(r"[A-Za-z%°/·.\-]+", compact) is not None
    )
    short_identifier = len(compact) <= 12 and re.search(r"\d", compact) is not None
    return " " in compact or not (short_unit or short_identifier)


def _looks_like_prose(text: str) -> bool:
    """Heuristic for body text, so short labels are not forced into Chinese."""
    return len(re.findall(r"[A-Za-z]", text)) >= 20 and bool(_PROSE_HINT.search(text))


def _clean_translation(text: str) -> str:
    """Remove ``---`` separators the model tends to wrap around blocks."""
    lines = text.strip().splitlines()
    while lines and re.fullmatch(r"\s*-{3,}\s*", lines[0]):
        lines.pop(0)
    while lines and re.fullmatch(r"\s*-{3,}\s*", lines[-1]):
        lines.pop()
    return "\n".join(lines).strip()


def _split_blocks(text: str) -> list[tuple[str, bool]]:
    """Split Markdown into blank-line separated blocks and whether to translate."""
    blocks: list[tuple[str, bool]] = []
    current: list[str] = []
    in_fence = False

    def flush() -> None:
        if not current:
            return
        block = "\n".join(current)
        stripped = block.strip()
        translatable = bool(stripped) and not stripped.startswith("```")
        if translatable and "<details" in stripped.lower():
            translatable = False
        blocks.append((block, translatable))
        current.clear()

    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            current.append(line)
            continue
        if not in_fence and not line.strip():
            flush()
        else:
            current.append(line)
    flush()
    return blocks


def split_markdown_blocks(text: str) -> list[str]:
    """Expose blank-line block splitting for layout-specific renderers."""
    return [block for block, _translatable in _split_blocks(text)]


def _split_long_block(block: str, max_chars: int) -> list[str]:
    if len(block) <= max_chars:
        return [block]
    sentences = _SENTENCE_SPLIT.split(block)
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for sentence in sentences:
        if current and length + len(sentence) + 1 > max_chars:
            chunks.append(" ".join(current))
            current = []
            length = 0
        current.append(sentence)
        length += len(sentence) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def _looks_like_markdown_table(block: str) -> bool:
    lines = block.splitlines()
    if len(lines) < 2 or "|" not in lines[0] or "|" not in lines[1]:
        return False
    return bool(_TABLE_SEPARATOR.match(lines[1].strip()))


def _split_markdown_row(line: str) -> tuple[list[str], bool, bool]:
    stripped = line.strip()
    leading = stripped.startswith("|")
    trailing = stripped.endswith("|")
    body = stripped[1:] if leading else stripped
    body = body[:-1] if trailing else body
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", body)], leading, trailing


def _load_glossary(path: Path | None) -> list[tuple[str, str]]:
    if path is None or not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    pairs: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" in line:
            source, target = line.split("\t", 1)
        elif "=" in line:
            source, target = line.split("=", 1)
        else:
            continue
        if source.strip() and target.strip():
            pairs.append((source.strip(), target.strip()))
    return pairs


def _prompt(text: str, glossary: list[tuple[str, str]]) -> str:
    terms = ""
    if glossary:
        rendered = "\n".join(f"{source} => {target}" for source, target in glossary[:40])
        terms = f"\n参考术语表（必须优先使用）：\n{rendered}\n"
    return (
        "你是学术论文翻译助手。将下面的 Markdown 文本翻译为简体中文。\n"
        "只输出译文，不要解释。保留 Markdown 标记、LaTeX 公式、引用、"
        "链接、图片和形如 @@P0@@ 的占位符不变。\n"
        f"{terms}\n---\n{text}"
    )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class TranslationService(AbstractContextManager["TranslationService"]):
    """Own a local llama-server process (or use an external one)."""

    def __init__(self, config: Config, selection: DeviceSelection | None = None) -> None:
        self.config = config
        self.translation = config.translation
        self.selection = selection or select_device(config)
        self.base_url = (
            self.translation.server_url.rstrip("/") if self.translation.server_url else ""
        )
        self.process: subprocess.Popen[str] | None = None
        self.log_path: Path | None = None
        self.glossary = _load_glossary(self.translation.glossary)
        self.fallback_counts: dict[str, int] = {
            "placeholder_retries": 0,
            "segment_fallbacks": 0,
            "segment_untranslated": 0,
            "no_cjk_fallbacks": 0,
            "no_cjk_kept": 0,
        }
        self.fallback_samples: list[str] = []

    def __enter__(self) -> Self:
        if not self.base_url:
            self._start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _start(self) -> None:
        model = self.translation.model
        if not model.exists():
            raise TranslationError(
                f"translation model not found: {model}\n"
                "Download it with `ptp --download-model` or set translation.model in config.yaml."
            )
        executable = shutil.which(self.translation.server_bin)
        if executable is None:
            raise TranslationError(
                f"llama.cpp server not found: {self.translation.server_bin!r}; install llama-cpp"
            )
        port = self.translation.port or _free_port()
        self.base_url = f"http://{self.translation.host}:{port}"
        cmd = [
            executable,
            "-m",
            str(model),
            "--host",
            self.translation.host,
            "--port",
            str(port),
            "-c",
            str(self.translation.context_size),
            "-np",
            "1",
            "--jinja",
        ]
        if self.selection.mode == "gpu":
            layers = self.translation.gpu_layers
            cmd.extend(["-ngl", str(99 if layers == "auto" else layers)])
            if self.selection.llama_device:
                cmd.extend(["-dev", self.selection.llama_device])
        else:
            cmd.extend(["-ngl", "0"])
        threads = self.translation.threads
        if threads is None:
            threads = self.config.threads if isinstance(self.config.threads, int) else None
        if threads is not None:
            cmd.extend(["-t", str(threads)])
        cmd.extend(self.translation.extra_args)

        fd, log_name = tempfile.mkstemp(prefix="ptp-llama-", suffix=".log")
        os.close(fd)
        self.log_path = Path(log_name)
        log_file = self.log_path.open("w", encoding="utf-8")
        logger.info("starting translation server on %s (%s)", self.base_url, self.selection.reason)
        self.process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            self._wait_ready()
        except Exception:
            self.close()
            raise

    def _wait_ready(self, timeout: float = 180.0) -> None:
        deadline = time.monotonic() + timeout
        health = self.base_url + "/health"
        while time.monotonic() < deadline:
            if self.process is not None and self.process.poll() is not None:
                raise TranslationError(
                    "translation server exited during startup:\n" + self._log_tail()
                )
            try:
                with urlopen(health, timeout=2) as response:
                    if response.status == 200:
                        return
            except (URLError, OSError):
                pass
            time.sleep(0.5)
        raise TranslationError("translation server did not become ready:\n" + self._log_tail())

    def _log_tail(self, lines: int = 30) -> str:
        if self.log_path is None or not self.log_path.exists():
            return "(no server log)"
        content = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])

    def close(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.process = None

    def complete(self, prompt: str, *, temperature: float | None = None) -> str:
        payload = {
            "model": "default",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.translation.temperature if temperature is None else temperature,
            "top_p": self.translation.top_p,
            "top_k": self.translation.top_k,
            "repeat_penalty": self.translation.repetition_penalty,
            "max_tokens": self.translation.max_tokens,
            "stream": False,
        }
        request = Request(
            self.base_url + "/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.translation.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (URLError, OSError, json.JSONDecodeError) as exc:
            raise TranslationError(f"translation request failed: {exc}") from exc
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise TranslationError(f"unexpected translation response: {body!r}") from exc
        content = (content or "").strip()
        if not content:
            raise TranslationError("translation server returned empty content")
        return content

    def _record_fallback(self, kind: str, text: str) -> None:
        self.fallback_counts[kind] = self.fallback_counts.get(kind, 0) + 1
        if len(self.fallback_samples) < 10:
            self.fallback_samples.append(f"{kind}: {text[:80].replace(chr(10), ' ')}")

    def fallback_stats(self) -> dict[str, int]:
        """Expose per-document fallback counters for state and logging."""
        return dict(self.fallback_counts)

    def _translate_segments(self, text: str) -> str:
        """Translate natural-language pieces around protected spans.

        Used only when the model fails to reproduce placeholders. Formula,
        link, citation and image spans are copied verbatim; only the plain
        text between them is sent to the model.
        """
        self._record_fallback("segment_fallbacks", text)
        pieces = _split_protected(text)
        if len(pieces) > _MAX_FALLBACK_SEGMENTS:
            self._record_fallback("segment_untranslated", text)
            logger.warning(
                "segment fallback skipped (%d pieces); keeping source text: %s",
                len(pieces),
                text[:80].replace("\n", " "),
            )
            return text
        max_chars = max(400, self.translation.chunk_tokens * 4)
        output: list[str] = []
        translated = False
        for piece, protected in pieces:
            if protected or not _segment_is_translatable(piece):
                output.append(piece)
                continue
            leading = piece[: len(piece) - len(piece.lstrip())]
            trailing = piece[len(piece.rstrip()) :]
            core = piece.strip()
            parts: list[str] = []
            try:
                for chunk in _split_long_block(core, max_chars):
                    result = self.complete(_prompt(chunk, self.glossary), temperature=0.0)
                    parts.append(_clean_translation(result))
            except TranslationError as exc:
                logger.warning("segment fallback request failed: %s", exc)
                output.append(piece)
                continue
            combined = " ".join(part for part in parts if part)
            if not _has_cjk(combined) or _PLACEHOLDER_RE.search(combined):
                output.append(piece)
                continue
            output.append(leading + combined + trailing)
            translated = True
        if not translated:
            self._record_fallback("segment_untranslated", text)
            logger.warning(
                "segment fallback produced no Chinese; keeping source text: %s",
                text[:80].replace("\n", " "),
            )
            return text
        return "".join(output)

    def translate_text(self, text: str, *, retry_on_missing_cjk: bool = True) -> str:
        text = sanitize_text(text)
        if not text.strip():
            return text
        protected, values = _protect(text)
        # Avoid sending image-only lines, citations, formulas, or URLs to the model.
        if not re.search(r"[A-Za-z]", _PLACEHOLDER_RE.sub("", protected)):
            return text
        result = self.complete(_prompt(protected, self.glossary))
        try:
            restored = _restore(result, values)
        except TranslationError:
            self._record_fallback("placeholder_retries", text)
            result = self.complete(_prompt(protected, self.glossary), temperature=0.0)
            try:
                restored = _restore(result, values)
            except TranslationError:
                logger.warning(
                    "translation dropped protected placeholders; retrying in segments: %s",
                    text[:80].replace("\n", " "),
                )
                return self._translate_segments(text)
        if retry_on_missing_cjk and not _has_cjk(restored) and re.search(r"[A-Za-z]", text):
            result = self.complete(_prompt(protected, self.glossary), temperature=0.0)
            try:
                restored = _restore(result, values)
            except TranslationError:
                self._record_fallback("placeholder_retries", text)
                logger.warning(
                    "translation dropped protected placeholders; retrying in segments: %s",
                    text[:80].replace("\n", " "),
                )
                return self._translate_segments(text)
            if not _has_cjk(restored):
                if _looks_like_prose(text):
                    self._record_fallback("no_cjk_fallbacks", text)
                    translated = self._translate_segments(text)
                    if translated != text:
                        return translated
                else:
                    self._record_fallback("no_cjk_kept", text)
                    logger.debug(
                        "translation returned no Chinese characters; keeping label: %s",
                        text[:80].replace("\n", " "),
                    )
                return text
        return _clean_translation(restored)

    def _translate_cell(self, cell: str) -> str:
        cell = sanitize_text(cell)
        if len(re.findall(r"[A-Za-z]", cell)) < 2:
            return cell
        try:
            return self.translate_text(cell)
        except TranslationError as exc:
            logger.warning("table cell translation failed: %s", exc)
            return cell

    def translate_markdown_table(self, block: str) -> str:
        """Translate a pipe table while preserving its structure and alignment row."""
        lines = block.splitlines()
        output: list[str] = []
        for index, line in enumerate(lines):
            if index == 1 and _TABLE_SEPARATOR.match(line.strip()):
                output.append(line)
                continue
            if "|" not in line:
                output.append(line)
                continue
            cells, leading, trailing = _split_markdown_row(line)
            translated = [self._translate_cell(cell) for cell in cells]
            row = " | ".join(translated)
            if leading:
                row = "| " + row
            if trailing:
                row = row + " |"
            output.append(row)
        return "\n".join(output)

    def translate_html_table(self, block: str) -> str:
        """Translate text nodes in an HTML table without touching tags or code."""
        soup = BeautifulSoup(block, "html.parser")
        for node in list(soup.find_all(string=True)):
            if not isinstance(node, NavigableString):
                continue
            parent = node.parent.name if node.parent is not None else ""
            if parent in {"code", "pre", "script", "style", "math"}:
                continue
            text = str(node)
            if len(re.findall(r"[A-Za-z]", text)) < 2:
                continue
            leading = text[: len(text) - len(text.lstrip())]
            trailing = text[len(text.rstrip()) :]
            try:
                translated = self.translate_text(text.strip())
            except TranslationError as exc:
                logger.warning("HTML table cell translation failed: %s", exc)
                continue
            node.replace_with(NavigableString(leading + translated + trailing))
        return str(soup)

    def translate_block(self, block: str) -> str:
        """Translate one Markdown block for the bilingual layout."""
        stripped = block.strip()
        if (
            not stripped
            or stripped.startswith(("```", "$$"))
            or "<table" in stripped.lower()
            or "<details" in stripped.lower()
            or _looks_like_markdown_table(block)
            or re.fullmatch(r"!\[[^\]]*\]\([^)]+\)", stripped)
        ):
            return block
        max_chars = max(400, self.translation.chunk_tokens * 4)
        pieces = _split_long_block(block, max_chars)
        return " ".join(self.translate_text(piece) for piece in pieces)

    def translate_markdown(self, text: str) -> str:
        max_chars = max(400, self.translation.chunk_tokens * 4)
        output: list[str] = []
        for block, translatable in _split_blocks(text):
            if not translatable or not re.search(r"[A-Za-z]", block):
                output.append(block)
                continue
            if _looks_like_markdown_table(block):
                output.append(self.translate_markdown_table(block))
                continue
            if "<table" in block.lower():
                output.append(self.translate_html_table(block))
                continue
            pieces = _split_long_block(block, max_chars)
            translated = " ".join(self.translate_text(piece) for piece in pieces)
            output.append(translated)
        return "\n\n".join(output).rstrip() + "\n"

    def translate_caption(self, caption: str) -> str:
        if not caption:
            return "[无图注]"
        if caption == "[no caption]":
            return "[无图注]"
        return self.translate_text(caption, retry_on_missing_cjk=False)


def download_default_model(config: Config) -> Path:
    """Download the pinned Q4_K_M GGUF into the configured model directory."""
    target = config.translation.model
    if target.exists():
        logger.info("model already exists: %s", target)
        return target
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise TranslationError("huggingface_hub is required for --download-model") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    logger.info("downloading %s/%s to %s", DEFAULT_HF_REPO, DEFAULT_HF_FILE, target.parent)
    path = hf_hub_download(
        repo_id=DEFAULT_HF_REPO,
        filename=DEFAULT_HF_FILE,
        local_dir=str(target.parent),
    )
    downloaded = Path(path)
    if downloaded != target:
        shutil.move(str(downloaded), target)
    logger.info("model ready: %s", target)
    return target

# AGENTS.md

`docs/user_manual.md` is the authoritative user/configuration spec; `README.md` is the feature overview and quick start. The implementation lives in `src/ptp/`, tests in `tests/`, and the sample configuration in `config.example.yaml`. Developer docs: `docs/dev.md` (architecture/debugging).

## Status and scope

- The Python CLI and the full PDF → MinerU → translation → Pandoc pipeline are implemented.
- Verified end-to-end on `inputs/nci195.pdf` with real Hy-MT2 Q4_K_M on NVIDIA NVK Vulkan:
  - `flash`: ~51 s (MinerU 2.1 s, translation 46.6 s, Pandoc 2.0 s).
  - `standard`: ~63–65 s (MinerU ~16 s, translation ~46 s, Pandoc ~2 s); HTML table translated and rendered.
- Bilingual two-column layout is implemented (`--layout bilingual`) and was exercised on all four PDFs in `inputs/` (4, 6, 9 and 11 pages).
- Placeholder failures now retry and then fall back to segment-wise translation; `state.json` records `translation_fallbacks`. In the four-PDF acceptance run, all body pairs in `s41598` and `nci195` had Chinese, and only metadata (ORCID/DOI) remained English.
- Bilingual layout now moves `page_footnote` blocks to an end-of-document `Notes / 注释` section, merges figure-interrupted continuation paragraphs, and converts `<sup>`/`<sub>` to LaTeX superscript/subscript commands. Long paragraphs spanning pages can still drift between columns; sentence-level alignment is future work.
- MinerU runs in a child process (`ptp/mineru_worker.py`) so its VLM leaves VRAM before llama-server starts; without this, standard translation falls to ~5 tok/s.
- `llama-bench` on Vulkan1: pp128 ≈ 1021 t/s, tg64 ≈ 78.7 t/s (asserts-enabled Arch build).
- v1 excludes original-layout fidelity, 7B, generated image descriptions, and default `advanced` tier.
- 10 minutes is a soft target, not an SLA.

## Commands

```bash
uv sync --extra mineru
uv run ptp --help
uv run ptp --dry-run -i inputs/nci195.pdf --device cpu
uv run ptp --download-model
uv run ptp -i inputs/nci195.pdf -o outputs
uv run ptp -i inputs/nci195.pdf -o outputs --layout bilingual
uv run ptp-install-mineru --accept-license
uv run pytest -q
uv run ruff check src tests
```

Use `uv` for everything. The environment is Python 3.13.18; `pip` is not installed.

The `mineru` package is an optional extra. For development use `uv sync --extra mineru`; for a license-separated install use `ptp-install-mineru` and point `mineru.python` at that venv.

## Architecture

- `cli.py` / `config.py`: argparse CLI, YAML defaults, CLI > config > built-ins.
- `pipeline.py`: per-document stages, state.json, resume, optional document-level threads.
- `mineru_runner.py`: text-layer coverage, `tier: auto`, MinerU child-process orchestration.
- `install_mineru.py`: create an isolated MinerU venv outside PTP's environment.
- `translate.py`: chunking, placeholder protection, llama-server lifecycle, GGUF download.
- `figures.py`: copy/rename figures (`fig1.jpg`…), extract captions, write bilingual `fig_comments.txt`.
- `render.py`: single-column Pandoc + XeLaTeX and `CJKmainfont`.
- `bilingual.py`: block pairing, paracol LaTeX generation, full-width figures/tables, direct XeLaTeX compile.
- `markdown_tables.py`: HTML table → Markdown pipe table; math entity normalization.
- `devices.py`: `llama-cli --list-devices`, GPU policy, MinerU environment.
- `mineru_worker.py`: standalone MinerU process (stdlib + MinerU only) to release GPU memory and allow a separate venv.

## Non-obvious rules

- `-o` is an output root directory, not a PDF path. Single PDF: `outputs/<stem>_zh/<stem>_zh.pdf`; bilingual PDF: `outputs/<stem>_zh/<stem>_bilingual.pdf`.
- MinerU is an optional dependency (`--extra mineru`) and can run from an isolated venv configured via `mineru.python`. It remains a separate program under the MinerU Open Source License; do not import it into PTP's main process.
- `render.layout: single|bilingual`; bilingual currently requires `render.engine: xelatex` and `paracol` from `texlive-latexextra`.
- In bilingual layout, title is bilingual; body text is paired per paragraph; figures/tables span both columns once; figure/table captions and references stay original; `fig_comments.txt` uses `ZH: [未翻译]`.
- `--task16` means `--threads 16`; it is not 16 parallel tasks. Use `--parallel N` for document concurrency.
- `tier: auto`: GPU → `standard`; CPU + high text coverage and no low-text pages → `basic`; CPU + scanned pages → `standard`. The heuristic does not detect table complexity.
- Use only Q4_K_M. Avoid 1.25-bit/2-bit variants (STQ kernel, quality loss).
- Translation chunks are ≤1k tokens; Markdown/LaTeX/images/citations are protected with `@@P0@@` placeholders. Markdown pipe tables and HTML tables are translated cell-wise; fenced code-block tables from MinerU `flash` remain untouched. If the model drops a placeholder, the block is retried and then translated segment-by-segment around the protected spans; only a final failure falls back to source text.
- `fig_comments.txt` contains extracted captions, not generated descriptions. `standard` VLM may split multi-panel figures, so compare caption alignment with `basic`.
- `--no-temp` deletes temp only after success; keep it on failure. `--resume` requires temp and skips completed documents without starting llama-server.
- `--gpu-only` must fail clearly when no GPU backend exists; `--device auto` may fall back to CPU.
- XeLaTeX needs `texlive-langchinese` for `ctexhook.sty` (installed); `texlive-langcjk` alone is not enough.
- Tectonic is installed but not used: its default bundle is ~2.62 GB. Use XeLaTeX.
- External `--server-url` skips llama-server startup; useful for tests or a shared GPU server.

## Environment (verified)

- Arch Linux; Pandoc 3.11; TeX Live 2026 XeLaTeX; `texlive-langchinese` and `texlive-latexextra` (`paracol`) installed.
- MinerU 4.1.7 installed via `uv`; llama.cpp 0.6.0 (build 11429) with `ggml-vulkan`.
- Vulkan detects AMD RADV iGPU and NVIDIA NVK RTX 3050; `llama-server` GPU path works. CUDA is not installed/verified.
- Noto Sans/Serif CJK SC installed. Host: Ryzen 7 5800H (8C/16T), 13 GiB RAM, 431 GB free.
- The Q4_K_M GGUF is present at `models/Hy-MT2-1.8B-Q4_K_M.gguf`. `ptp --download-model` is idempotent. MinerU `standard` downloads its own VLM/OCR models on first use.

## Verification

- Fixtures: `nci195.pdf` (4 pages), `Operation...` (6), `mfortuna...` (9), `s41598...` (11). Use all four for layout/robustness checks.
- Unit tests currently pass (`uv run pytest -q`).
- For a real run, start with `--tier flash --device cpu` if models are not ready; then try `standard` and GPU.
- Do not commit `outputs/`, `models/`, `.venv/`, or temporary PDFs.

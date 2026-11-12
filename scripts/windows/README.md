# Windows portable build

This directory builds the offline Windows x64 portable package described in
`docs/windows.md`.

## Prerequisites (build machine)

- Windows x64, PowerShell 7 (`pwsh`).
- `uv` (Scoop/winget or standalone).
- 7-Zip (`7z`) in `PATH`.
- .NET Framework 4.8 `csc.exe` (included with Windows 10/11).
- Network access for the first build if assets are not already cached.
- Optional: Scoop's `pandoc` and MiKTeX for local development (the portable
  package uses TinyTeX, not MiKTeX).

## Build

From the repository root:

```powershell
pwsh -File scripts/windows/build_portable.ps1
```

The output is `build\windows-portable\`.

Reusing already-downloaded test assets:

```powershell
pwsh -File scripts/windows/build_portable.ps1 `
  -E2EAssets "$env:LOCALAPPDATA\ptp-e2e" `
  -TinyTexDir "$env:LOCALAPPDATA\ptp-e2e\tex-test\TinyTeX"
```

Useful options:

- `-OutputDir <dir>`: output directory (default `build\windows-portable`).
- `-PythonDir <dir>`: use a specific relocatable CPython 3.13 directory.
- `-PythonVersion 3.13`: uv-managed CPython version to use when `-PythonDir` is omitted.
- `-PandocExe <path>`: use a specific `pandoc.exe`.
- `-LlamaTag b12283`: llama.cpp release tag.
- `-TinyTexVersion v2026.11`: TinyTeX release tag.
- `-TinyTexDir <dir>`: copy an existing TinyTeX tree instead of downloading.
- `-E2EAssets <dir>`: copy existing models, fonts and llama.cpp builds from a
  prepared test directory.
- `-Wheelhouse <dir>`: install Python packages offline from wheels.
- `-SkipDoctor`: skip the final `ptp.exe --doctor` check.
- `-Force`: replace an existing output directory that is not the default.

## Component split and release archives

After the full directory build passes, split it into the three release
components:

```powershell
pwsh -File scripts/windows/build_components.ps1 `
  -SourceDir build\windows-portable `
  -PythonVersion 3.13

pwsh -File scripts/windows/package_components.ps1 -CompressionLevel 5
```

This writes to `dist/`:

- `PTP-Windows-x64-core.7z`: PTP runtime, Pandoc, TinyTeX, llama.cpp, fonts,
  launcher, installers, and an **empty** `runtime/mineru` Python runtime.
- `PTP-Windows-x64-hy-model.7z`: Hy-MT2 GGUF, model readme, and notices.
- `PTP-Windows-x64-mineru.7z`: MinerU runtime packages, MinerU models,
  `data/mineru-home/config.yaml`, and notices.
- `SHA256SUMS.txt`.

Users choose one of:

- Lite: extract `core`, run `install-all.cmd` (or both component scripts).
- Model: extract `core` + `hy-model`, run `install-mineru.cmd`.
- Full: extract all three archives into the same directory.

The old `package_archives.ps1` remains for the monolith full-package layout,
but component releases should use `build_components.ps1` +
`package_components.ps1`.

## Installer scripts

Source files are in `scripts/windows/install/`:

- `install-hy.ps1`: online HF download or `-ModelDir` offline copy, SHA256 check.
- `install-mineru.ps1`: license gate, pinned `requirements-mineru.txt`,
  optional `-Wheelhouse`, optional `-ModelDir`, `mineru-kit` verification.
- `install-all.ps1`: runs both.
- `components.example.json`: expected revisions/hashes.
- `install-*.cmd`: Windows PowerShell 5.1 wrappers.

`build_components.ps1` copies the `.ps1` files into `core\install\`, the `.cmd`
wrappers into the core root, and writes `components.json`.

## What the script does

1. Copies a uv-managed relocatable CPython 3.13 into `runtime\ptp` and
   `runtime\mineru` (override with `-PythonDir` / `-PythonVersion`).
2. Builds/installs the PTP wheel into `runtime\ptp`.
3. Installs MinerU 4.1 into `runtime\mineru`.
4. Copies Pandoc into `tools\pandoc`.
5. Downloads/extracts llama.cpp Vulkan and CPU builds into `tools\llama`.
6. Downloads/extracts TinyTeX 1 into `tex\TinyTeX`, then installs required
   LaTeX packages with `tlmgr`.
7. Copies Noto Serif CJK SC Regular/Bold into `fonts`.
8. Downloads/copies Hy-MT2 at the revision pinned in
   `install/components.example.json`, verifies its SHA256, and installs the
   pinned MinerU version; model revisions are recorded in the build manifest.
9. Writes portable `config.yaml` and the MinerU runtime config.
10. Compiles the thin C# launcher `ptp.exe`.
11. Runs `ptp.exe --doctor`.

## Layout

```text
build/windows-portable/
  ptp.exe
  ptp.cmd
  config.yaml
  README-Windows.md
  build-manifest.json
  inputs/
  outputs/
  data/
  runtime/ptp/
  runtime/mineru/
  tools/pandoc/
  tools/llama/vulkan/
  tools/llama/cpu/
  tex/TinyTeX/
  fonts/
  models/
  mineru-models/
  LICENSES/
```

After `build_components.ps1`:

```text
build/components/
  core/          # runtime/mineru is empty, installers included
  hy-model/
  mineru/        # runtime/mineru is fully installed + mineru-models
```

The launcher sets the working directory to the package root and the runtime
environment variables. It intentionally does not put `tools\llama` on `PATH`,
so MinerU's own llama.cpp DLLs are not shadowed.

## Smoke test

```powershell
pwsh -File scripts/windows/verify_portable.ps1
```

Or manually:

```powershell
.\build\windows-portable\ptp.exe --doctor
.\build\windows-portable\ptp.exe --dry-run -i inputs\nci195.pdf --device cpu
```

For a real run, use a PDF from the repository `inputs/` directory or copy it
into `build\windows-portable\inputs\`.

## Notes

- TinyTeX is extracted from the official `TinyTeX-1-windows-vYYYY.MM.exe`
  7-Zip archive; no installer/registry changes are required.
- `tlmgr` may need `tlmgr update --self` before installing packages; the build
  script takes care of it.
- At runtime PTP writes an absolute per-run `mineru-config.yaml` and sets
  `MINERU_CONFIG`, so the package still finds models after it is moved.
- The build output is large (several GB) and is intentionally ignored by Git.
- Do not commit `build/`, models, or generated runtimes.

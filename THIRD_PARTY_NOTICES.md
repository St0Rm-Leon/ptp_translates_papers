# Third-Party Notices

PTP Translates Papers is licensed under the GNU General Public License,
version 2 or (at your option) any later version.  See `LICENSE`.

Bundled or downloaded third-party components retain their own licenses.  This
file is a summary; the full texts for the licenses listed below are in
`LICENSES/`.

## Windows portable components

The Windows x64 release is split into `core`, `hy-model`, and `mineru`
components.  The `core` component contains a CPython runtime, Pandoc, TinyTeX,
llama.cpp, Noto CJK fonts, and an **empty** MinerU Python runtime (no MinerU
packages).  The `hy-model` and `mineru` components contain the model files and,
for `mineru`, the MinerU runtime packages.  Lite/Model variants download
missing components through `install-hy` / `install-mineru`; those scripts do
not redistribute the downloaded files.  These remain separate programs/assets
with their own licenses:

- CPython: PSF-2.0 (`runtime/ptp/LICENSE.txt`; copied to
  `LICENSES/Python-PSF-2.0.txt`).
- Pandoc: GPL-2.0-or-later.  The PTP GPL text is in `LICENSE` and
  `LICENSES/GPL-2.0-or-later.txt`.
- TinyTeX / TeX Live: license files are in `tex/TinyTeX/LICENSE.TL` and
  `tex/TinyTeX/LICENSE.CTAN` (copied into `LICENSES/`).
- llama.cpp: MIT, see `LICENSES/llama.cpp-MIT.txt`.
- Noto Serif/Sans CJK: SIL Open Font License 1.1, see
  `LICENSES/OFL-1.1.txt`.
- MinerU: see the section below; the `mineru` component/full version ships it
  as a separate runtime, not imported into PTP's main process.  PTP invokes
  `mineru-kit parse` as an independent CLI process and reads its result ZIP;
  no PTP/GPL code runs inside the MinerU process.  The `install-mineru` script
  shows the license and requires acceptance.
- Models: see the models section below.  Model files are not covered by PTP's
  GPL license.

## MinerU (optional component)

- Package: `mineru` <https://github.com/opendatalab/MinerU>
- License: **MinerU Open Source License**, based on Apache License 2.0 with
  additional terms (commercial-use thresholds and online-service attribution).
- Full text: `LICENSES/MinerU-LICENSE.md`
- PTP does not bundle MinerU in the Python wheel or source distribution.  The
  `ptp-install-mineru` command installs it into a separate virtual environment
  so it remains an independent program.
- The Windows `core` component contains only an empty `runtime/mineru/` Python
  runtime.  The `mineru` component/full version installs MinerU packages into
  it; the `install-mineru` script installs the same pinned version from PyPI.
  PTP invokes the independent `mineru-kit parse` CLI; MinerU is not imported
  by PTP's main process and no PTP/GPL code runs inside the MinerU process.
  The MinerU license and attribution requirements apply whenever MinerU is
  bundled or installed.

## Models

- **Hy-MT2-1.8B-GGUF** (`tencent/Hy-MT2-1.8B-GGUF`): Apache License 2.0.
  Downloaded by `ptp --download-model` and not included in the source
  distribution.
- **MinerU models** (`opendatalab/MinerU-4_models_onnx`,
  `MinerU2.5-Pro-2605-1.2B` and quantized derivatives): the upstream model
  cards specify the applicable licenses.  The MinerU ONNX model card states
  that original model licenses and attribution remain applicable.
- Model files are not part of the PTP source license.  Preserve the upstream
  model cards and license files when redistributing an offline bundle.
- The Windows `hy-model` and `mineru` components/full version include the model
  files under `models/` and `mineru-models/`; each directory contains a
  `README.txt` with source and license pointers.  Lite/Model variants may
  download the same files through `install-hy` / `install-mineru`.  The
  `.cache/` Hugging Face metadata is not included in release archives.

## Python dependencies

The core and optional Python dependencies are distributed under MIT,
BSD-2-Clause, BSD-3-Clause, Apache-2.0, MPL-2.0, PSF-2.0, or compatible
licenses.  License metadata is available from each installed distribution
(`importlib.metadata`), and the full texts of the common licenses are in
`LICENSES/`.

Notable components:

- CPython / python-build-standalone (Windows portable bundle): PSF-2.0 for
  CPython; the standalone build tooling is MPL-2.0.  See
  `runtime/ptp/LICENSE.txt` in the portable bundle.
- `pypdfium2` / PDFium: BSD-3-Clause and Apache-2.0; see
  `LICENSES/pypdfium2/` (in the wheel: `ptp/licenses/pypdfium2/`).
- `beautifulsoup4`: MIT, see `LICENSES/BeautifulSoup-MIT.txt`.
- `PyYAML`: MIT, see `LICENSES/PyYAML-MIT.txt`.
- `huggingface_hub`: Apache-2.0, see `LICENSES/huggingface_hub-Apache-2.0.txt`.
- `MinerU`: MinerU Open Source License (see above)
- `mineru-llama-cpp`: MIT
- `onnxruntime`: MIT
- `gradio`: Apache-2.0

## External programs

- **Pandoc**: GPL-2.0-or-later, <https://pandoc.org/>.  The Windows portable
  bundle includes `tools/pandoc/pandoc.exe`.
- **llama.cpp** / `llama-server`: MIT, <https://github.com/ggml-org/llama.cpp>.
  The Windows portable bundle includes Vulkan and CPU builds under
  `tools/llama/`.
- **XeLaTeX / TeX Live**: individual packages use LPPL, GPL, BSD, public
  domain, and other free licenses.  The Windows portable bundle uses TinyTeX;
  its `LICENSE.TL` and `LICENSE.CTAN` files are included at the TeX tree root.
  Preserve the TeX Live license files when bundling a TeX distribution.
- **Noto Serif/Sans CJK**: SIL Open Font License 1.1
  (`LICENSES/OFL-1.1.txt`).  The Windows portable bundle includes Serif
  Regular/Bold OTF files under `fonts/`.

## GPU drivers

Vulkan/CUDA/Metal drivers are system components and are not bundled.  Their
licenses are determined by the GPU vendor.

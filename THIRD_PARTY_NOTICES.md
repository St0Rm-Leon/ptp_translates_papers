# Third-Party Notices

PTP Translates Papers is licensed under the GNU General Public License,
version 2 or (at your option) any later version.  See `LICENSE`.

Bundled or downloaded third-party components retain their own licenses.  This
file is a summary; the full texts for the licenses listed below are in
`LICENSES/`.

## MinerU (optional component)

- Package: `mineru` <https://github.com/opendatalab/MinerU>
- License: **MinerU Open Source License**, based on Apache License 2.0 with
  additional terms (commercial-use thresholds and online-service attribution).
- Full text: `LICENSES/MinerU-LICENSE.md`
- PTP does not bundle MinerU.  The `ptp-install-mineru` command installs it
  into a separate virtual environment so it remains an independent program.

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

## Python dependencies

The core and optional Python dependencies are distributed under MIT,
BSD-2-Clause, BSD-3-Clause, Apache-2.0, MPL-2.0, PSF-2.0, or compatible
licenses.  License metadata is available from each installed distribution
(`importlib.metadata`), and the full texts of the common licenses are in
`LICENSES/`.

Notable components:

- `pypdfium2` / PDFium: BSD-3-Clause and Apache-2.0
- `beautifulsoup4`: MIT
- `PyYAML`: MIT
- `huggingface_hub`: Apache-2.0
- `MinerU`: MinerU Open Source License (see above)
- `mineru-llama-cpp`: MIT
- `onnxruntime`: MIT
- `gradio`: Apache-2.0

## External programs

- **Pandoc**: GPL-2.0-or-later, <https://pandoc.org/>
- **llama.cpp** / `llama-server`: MIT, <https://github.com/ggml-org/llama.cpp>
- **XeLaTeX / TeX Live**: individual packages use LPPL, GPL, BSD, public
  domain, and other free licenses.  Preserve the TeX Live license files when
  bundling a TeX distribution.
- **Noto Serif/Sans CJK**: SIL Open Font License 1.1
  (`LICENSES/OFL-1.1.txt`).

## GPU drivers

Vulkan/CUDA/Metal drivers are system components and are not bundled.  Their
licenses are determined by the GPU vendor.

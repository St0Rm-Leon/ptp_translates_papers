# ptp translates papers

把英文论文 PDF 在本地转成中文 PDF：MinerU 负责版面解析，Hy-MT2-1.8B Q4_K_M 负责翻译，Pandoc + XeLaTeX 负责排版。

## 功能

- 输入带文本层的英文论文 PDF；`tier: auto` 自动选择 MinerU `basic`/`standard`，也可手动指定 `--tier`。
- 输出单栏中文 PDF，或“左原文 / 右译文”的双语双栏 PDF。
- 双语模式：标题双语、正文段落配对、图片/表格全宽、图注/表注/参考文献保留原文、页脚注集中到文末 `Notes / 注释`、上标/下标正确渲染。
- Markdown pipe table 和 HTML table 的单元格会翻译；双语 HTML 表格保留 `rowspan`/`colspan`；`flash` 的 code-fence 表格保留原文。
- `fig_comments.txt` 提取论文原有图注，中英双语；不生成图像描述。
- Hy-MT2 分块翻译、术语表、占位符保护；模型丢失占位符时自动重试并分段翻译。
- CPU/GPU 自动选择（Vulkan/CUDA/Metal），支持文档级并行、断点续跑和外部 llama-server。
- MinerU 可选独立 venv：`ptp-install-mineru`，不并入 PTP 的 GPL 代码范围。
- `config.yaml` 提供默认值，CLI 参数覆盖；输出到 `outputs/<stem>_zh/`。

## 快速开始

### 依赖

- Python 3.11–3.14 + `uv`
- Pandoc 3.x + XeLaTeX（`texlive-xetex`、`texlive-latexrecommended`、`texlive-fontsrecommended`、`texlive-langchinese`；双语还需 `texlive-latexextra`）
- llama.cpp：`llama-server`、`llama-cli`
- Noto Serif/Sans CJK SC
- MinerU：通过 `--extra mineru` 或 `ptp-install-mineru`
- GPU 可选：Vulkan/CUDA/Metal；没有 GPU 时用 `--device cpu`

Arch Linux 和 Windows 的完整系统依赖命令见[用户手册](docs/user_manual.md#2-安装与首次运行)。

Windows 下 `llama-server.exe`、`llama-cli.exe`、Pandoc 和 XeLaTeX 可以不加入 PATH，直接在 `config.yaml` 的 `translation.server_bin`、`translation.llama_cli`、`render.pandoc`、`render.xelatex` 指定路径。Windows 默认没有 Noto CJK，可用 `render.cjk_font_file` 指向字体文件。安装后先运行：

```powershell
uv run ptp --doctor
```

### 安装

开发环境（MinerU 与 PTP 共用一个 venv）：

```bash
uv sync --extra mineru
uv run ptp --download-model
```

推荐发行方式（MinerU 安装到独立 venv）：

```bash
uv sync
uv run ptp-install-mineru --accept-license
```

把安装器打印的配置加入 `config.yaml`：

```yaml
mineru:
  python: /path/to/mineru-venv/bin/python
```

然后下载 Hy-MT2：

```bash
uv run ptp --download-model
```

### 运行

```bash
# 单栏中文 PDF
uv run ptp -i inputs/nci195.pdf -o outputs

# 双语双栏
uv run ptp -i inputs/nci195.pdf -o outputs --layout bilingual

# 使用 config.yaml
cp config.example.yaml config.yaml
uv run ptp
```

输出：

```text
outputs/<stem>_zh/<stem>_zh.pdf
outputs/<stem>_zh/<stem>_bilingual.pdf
```

`-o` 是输出根目录，不是 PDF 文件路径。

完整配置、CLI、输出结构和故障排查见[用户手册](docs/user_manual.md)；架构、模块和调试见[开发者文档](docs/dev.md)。

## Windows 便携版

仓库包含 Windows x64 便携包的构建脚本，不要求用户安装 Python/uv。发行包拆成三个组件：

- `core`：PTP、Pandoc、TinyTeX、llama.cpp、字体、启动器和安装脚本。
- `hy-model`：Hy-MT2 翻译模型。
- `mineru`：MinerU runtime + MinerU 模型。

支持三种用法：最简版（core + 安装脚本）、模型版（core + hy-model + MinerU 安装脚本）、完整版（三个组件全部解压，离线可用）。

```powershell
pwsh -File scripts/windows/build_portable.ps1
pwsh -File scripts/windows/build_components.ps1
pwsh -File scripts/windows/package_components.ps1
```

产物在 `build\windows-portable\` 和 `build\components\`，发布压缩包在 `dist\`。使用说明见 [Windows 便携版文档](docs/windows.md)，构建细节见 [scripts/windows/README.md](scripts/windows/README.md)。

---

许可证：GPL-2.0-or-later。第三方组件和模型声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

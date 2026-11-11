# PTP Translates Papers — 开发者文档

本文面向继续开发、调试和扩展 `ptp translates papers` 的开发者。用户配置说明见 [user_manual.md](user_manual.md)，产品范围见 [README.md](../README.md)。

## 1. 项目定位

PTP 是一个本地 PDF 论文翻译流水线：

```text
PDF → MinerU → Markdown + 图片 + 结构化 JSON
    → Markdown 分块翻译（Hy-MT2-1.8B Q4_K_M）
    → Pandoc + XeLaTeX → 中文 PDF
```

设计约束：

- 10 分钟是**软目标**，不是 SLA；普通 4–6 页带文本层论文优先。
- v1 不追求与原 PDF 版式一致；翻译和渲染解耦，为后续自定义版式留接口。
- CPU 和 GPU 都支持；GPU 是加速项，不是必需项。
- 表格采用“翻译后转 Markdown 表格”的方案，不直接依赖 Pandoc 对 raw HTML table 的渲染。
- 复杂 HTML 表格的 `rowspan`/`colspan` 会展开成近似网格，版式仍可继续优化。

## 2. 仓库结构

```text
src/ptp/
  cli.py              argparse CLI、参数覆盖、错误输出
  config.py           dataclass 配置、YAML 解析、优先级与校验
  pipeline.py         单文档/多文档编排、状态、续跑、阶段调用
  mineru_runner.py    文本层检测、tier 决策、MinerU 子进程调用
  mineru_worker.py    独立 MinerU 子进程入口
  translate.py        分块、占位符保护、llama-server 生命周期
  figures.py          图片复制/重命名、图注提取、fig_comments.txt
  markdown_tables.py  HTML table → Markdown pipe table、数学实体规范化
  bilingual.py        双语 block 配对、paracol LaTeX、全宽图表
  render.py           单栏 Pandoc + XeLaTeX
  devices.py          llama.cpp 设备发现、GPU 策略、MinerU 环境变量
tests/
  test_cli.py
  test_config.py
  test_bilingual.py
  test_devices.py
  test_figures.py
  test_markdown_tables.py
  test_translate.py
config.example.yaml
```

## 3. 端到端流程

入口是 `ptp.cli:main`。核心执行顺序：

1. `load_config()` 读取 `config.yaml`，再用 `Config.with_cli_overrides()` 应用 CLI。
2. `resolve_inputs()` 解析 `-i` 或 config 的 `input`，支持目录和多个 PDF。
3. `run_pipeline()` 为每个输入建立 `outputs/<stem>_zh/`。
4. `inspect_text_layer()` 用 pypdfium2 统计每页文本字符数。
5. `resolve_tier()` 根据设备、文本覆盖率和 `mineru.tier` 决定档位。
6. `parse_pdf_subprocess()` 启动 `python -m ptp.mineru_worker`：
   - 子进程运行 MinerU；
   - 保存 `markdown.md`、`structured_content.json`、`images/`；
   - 子进程退出，释放 VLM/ONNX 占用的显存。
7. 主进程读取 Markdown 和结构化 JSON，`prepare_figures()`：
   - 把图片复制到 `temp/image/`；
   - 将实际图片重命名为 `fig1.jpg`、`fig2.jpg`…；
   - 把 Markdown 的 `images/...` 引用改成 `image/...`；
   - 提取图注，生成 `FigureEntry` 列表。
8. `TranslationService` 启动 `llama-server`，翻译 Markdown 和图注。
9. 单栏模式：`html_tables_to_markdown()` 把翻译后的 HTML 表格转换成 Markdown pipe table，`render_pdf()` 调用 Pandoc + XeLaTeX 生成 `_zh.pdf`。
10. 双语模式：`bilingual.build_units()` 生成 source/translation block 对，`build_bilingual_tex()` 生成 paracol LaTeX，`render_bilingual_pdf()` 直接运行 XeLaTeX 生成 `_bilingual.pdf`。
11. 写入 `state.json`（含 `layout`）；按 `keep_temp` 决定是否删除 `temp/`。

### 3.1 输出结构

```text
outputs/
  nci195_zh/
    temp/
      image/
        fig1.jpg
        fig2.jpg
        fig_comments.txt
        page_1_equation_8.jpg
      nci195_en.md
      nci195_zh.md
      nci195_content_list.json
      state.json
    nci195_zh.pdf
```

`state.json` 记录：

```json
{
  "version": 1,
  "source": "/abs/path/inputs/nci195.pdf",
  "stem": "nci195",
  "status": "completed",
  "device": "gpu",
  "tier": "standard",
  "text_coverage": 1.0,
  "pages": 4,
  "stages": {
    "mineru": "completed",
    "translate": "completed",
    "render": "completed"
  },
  "timings": {
    "inspect": 0.01,
    "mineru": 15.7,
    "translate": 45.0,
    "render": 2.1
  }
}
```

### 3.2 续跑

- `resume: true` 或 `--resume` 时，若 `state.json.status == "completed"` 且 PDF 存在，直接跳过。
- MinerU 阶段存在 `en.md` + `content_list.json` 时复用。
- 翻译阶段存在 `zh.md` + `fig_comments.txt` 时复用。
- `--no-temp` 只在成功后删除 `temp/`；失败时保留，便于续跑。
- 续跑前若改变了 tier/device，建议手动删除旧 `temp/` 或换输出目录，避免复用不匹配的中间结果。

## 4. 配置与优先级

配置类是 `src/ptp/config.py` 中的 dataclass：

- `Config`
- `MineruConfig`
- `TranslationConfig`
- `RenderConfig`

优先级：

```text
CLI 显式参数 > config.yaml > dataclass 默认值
```

关键规则：

- `--config PATH` 指定配置文件；否则查找当前工作目录的 `./config.yaml`。
- 配置文件里的相对路径按**配置文件所在目录**解析。
- CLI 里的 `-o`/`--model` 等相对路径按**当前工作目录**解析。
- 未知配置键会直接报错，避免拼写错误被静默忽略。
- `version` 目前只支持 `1`。
- `--task16` 等价于 `--threads 16`；`--parallel` 才是文档级并行。
- `--no-temp` / `--keep-temp` 映射到 `keep_temp` 布尔值。
- `--cpu-only` / `--gpu-only` 是 `--device cpu/gpu` 的互斥别名。
- `render.layout` 为 `single` 或 `bilingual`；双语模式使用 `source_ratio`、`source_line_spacing`、`target_line_spacing`、`figure_max_height`。
- 双语模式输出单独文件 `<stem>_bilingual.pdf`；`state.json.layout` 用于续跑匹配。

## 5. MinerU 集成

### 5.1 文本层与 tier

`inspect_text_layer()` 使用 `pypdfium2` 逐页提取文本，返回：

- 总页数；
- 每页字符数；
- 有文本页数；
- 低文本页数。

`resolve_tier()` 的规则：

- 显式 `--tier flash|basic|standard|advanced` 直接使用。
- `tier: auto`：
  - GPU 模式：`standard`。
  - CPU 且文本覆盖率 ≥ `auto_basic_text_coverage` 且没有低文本页：`basic`。
  - 其他：`standard`。

注意：这是启发式，**不判断表格复杂度**。表格多或公式多时，建议显式 `--tier standard`。

### 5.2 为什么要用子进程

MinerU `standard` 会在同一进程内加载 VLM（llama.cpp）和 ONNX 小模型。若主进程随后启动 `llama-server`：

- 两个模型同时占用 GPU；
- 在 4 GB 显存上翻译速度可能从约 78 tok/s 掉到约 5 tok/s；
- 总翻译时间可能从约 46 s 增加到约 585 s。

因此 `parse_pdf_subprocess()` 通过 `python -m ptp.mineru_worker` 隔离 MinerU。子进程退出后显存释放，再启动翻译服务。这是标准档性能的关键设计，不要改回进程内直接调用。

`mineru_worker.py` 接收：

```text
--pdf --work-dir --tier --device --gpu-backend --gpu-index --threads --image-analysis
```

它构造临时 `Config`，调用 `select_device()`，然后复用 `mineru_runner.parse_pdf()`。

### 5.3 MinerU 环境变量

`devices.mineru_environment()` 会在解析期间设置并在结束后恢复：

```text
MINERU_DEVICE_MODE
MINERU_MODEL_ONNX_DEVICE
MINERU_LLAMA_CPP_BACKEND
GGML_VK_VISIBLE_DEVICES
MINERU_INTRA_OP_NUM_THREADS
MINERU_INTER_OP_NUM_THREADS
MINERU_CPU_NUM_THREADS
```

其中 `GGML_VK_VISIBLE_DEVICES` 用于把 MinerU 的 Vulkan 设备限制到选中的 GPU。详细 GPU 策略见第 8 节。

### 5.4 模型下载

MinerU 首次运行会下载：

- `MinerU-4_models_onnx` 的布局、OCR、公式、表格模型；
- `MinerU2.5-Pro-2605-1.2B-GGUF` 的 VLM 主模型和 mmproj。

这些缓存在 `~/.mineru/models/`。如果 Hugging Face 下载中断，可以重试；MinerU 使用 `.mineru_complete` 标记完整仓库。不要手动删除正在使用的缓存。

## 6. 图片与图注

MinerU `structured_content.json` 的 image/chart block 通常包含：

```json
{
  "type": "image",
  "image_source": "images/page_1_image_2.jpg",
  "captions": [{"content": "Figure 1. ..."}]
}
```

`figures.prepare_figures()`：

1. 复制全部图片到 `temp/image/`。
2. 对 `type` 为 `image`/`chart` 的 block 按文档顺序重命名为 `figN.ext`。
3. 更新 Markdown 中对应的 `images/...` 引用为 `image/figN.ext`。
4. 删除未重命名的重复图片副本。
5. 仅对 `image`/`chart` 生成 `FigureEntry`；公式/表格图片保留原名。

`fig_comments.txt` 格式：

```text
fig1.jpg
EN: Figure 1. ...
ZH: 图 1. ...

fig2.jpg
EN: [no caption]
ZH: [无图注]
```

注意：MinerU `standard` VLM 可能把多 panel 图拆成多个图片；需要对比 `basic`/`standard` 的图注对齐效果。

## 7. 翻译实现

### 7.1 llama-server 生命周期

`TranslationService` 有两种模式：

- 本地启动：`llama-server -m <gguf> --host ... --port ... -c 4096 -np 1 --jinja`。
- 外部服务：`translation.server_url` 或 `--server-url`，不启动本地进程。

GPU 模式附加：

```text
-ngl 99 -dev Vulkan1
```

CPU 模式：

```text
-ngl 0 -t <threads>
```

服务通过 `/health` 等待就绪，通过 `/v1/chat/completions` 请求翻译。请求参数来自 `TranslationConfig`：`temperature`、`top_p`、`top_k`、`repetition_penalty`、`max_tokens`。

### 7.2 分块与保护

`translate_markdown()`：

- 按空行分块；
- 跳过 fenced code block 和 `<details>` 块；
- Markdown pipe table 走表格路径；
- HTML table 走 HTML 路径；
- 普通块按 `chunk_tokens` 切分。

`_protect()` 把以下内容替换成 `@@P0@@` 形式的占位符：

- `$$...$$` 和 `$...$`；
- 图片 `![...](...)`；
- 链接 `[...](...)`；
- 行内代码 `` `...` ``；
- 引用 `[1]` / `[1-3]`；
- URL。

HTML 标签不再整体保护，模型会看到 `<strong>`/`<sub>`/`<sup>` 等标签，以保留内联格式。

模型只看到占位符；恢复阶段检查每个占位符是否仍然存在。丢失占位符会重试一次；仍失败时按受保护片段切分，只翻译普通文本段并原样拼回公式/链接/引用/图片，最终仍失败才保留原文。`TranslationService.fallback_stats()` 记录重试和回退次数，写入 `state.json` 的 `translation_fallbacks`。输出还会：

- 检查是否包含中文（可配置重试）；
- 去掉模型习惯性添加的首尾 `---`；
- 清除 PDF 提取产生的控制字符（如 `\x01`）。

### 7.3 表格

Markdown pipe table：

- 识别第二行的 `---` 分隔行；
- 逐单元格翻译，保留 `|` 和分隔行；
- 单字母（如 `C`/`λ`）和纯数字单元格跳过，避免无意义请求。

HTML table：

- 用 BeautifulSoup 遍历文本节点；
- 跳过 `code`/`pre`/`script`/`style`/`math`；
- 保留标签结构；
- 少于 2 个 ASCII 字母的单元格跳过。

渲染前 `html_tables_to_markdown()`：

- 用 BeautifulSoup 解析每个 `<table>`；
- 展开 `rowspan`/`colspan`；
- 生成 Markdown pipe table；
- 用 `normalize_math_entities()` 解码数学 span 内的 `&lt;` 等实体，避免 XeLaTeX 把 `&` 当成对齐字符；
- 只替换 table 片段，不对整篇文档做 BeautifulSoup 序列化（否则会把普通 `<` 转成 `&lt;`）。

### 7.4 术语表

`translation.glossary` 指向文本文件，支持：

```text
Blanket region = 包层区域
Facing surface	迎向表面
```

每行 `source=target` 或 `source<TAB>target`，`#` 开头为注释。术语表最多取前 40 条加入 prompt。

## 8. 设备与并行

`devices.list_devices()` 执行：

```bash
llama-cli --list-devices
```

解析 `Vulkan0`、`Vulkan1`、`CUDA0` 等设备。

`select_device()`：

- `device: cpu` → CPU；
- `device: gpu` → 必须找到设备，否则报错；
- `device: auto` → 有 GPU 时优先按名称选择 NVIDIA/AMD 独显，否则 CPU；
- `gpu_backend` 可按 `vulkan`/`cuda`/`metal` 过滤；
- `gpu_index` 指定 llama.cpp 设备索引。

GPU 模式：

- `--parallel > 1` 会被强制降为 1，避免 4 GB 显存争用；
- MinerU 和翻译都按阶段串行使用 GPU；
- `--gpu-only` 在无 GPU 时必须报错，不静默回退。

CPU 模式：

- `--threads`/`--task16` 控制翻译和 MinerU 的线程；
- `--parallel` 可并行多个文档，但每个文档会各自启动 llama-server，需要足够内存；
- 16 GB 内存建议保持 `parallel: 1`。

## 9. 渲染

### 9.1 单栏渲染（Pandoc）

`render.render_pdf()` 的核心命令：

```bash
pandoc <zh.md> \
  --from markdown+tex_math_dollars+raw_html+pipe_tables \
  --to pdf --standalone \
  --pdf-engine xelatex \
  --resource-path <temp_dir> \
  --variable CJKmainfont="Noto Serif CJK SC" \
  --output <pdf>
```

- `render.engine` 支持 `xelatex`、`lualatex`、`tectonic`、`typst`；当前实际验证的是 `xelatex`。
- XeLaTeX 需要 `texlive-xetex`、`texlive-latexrecommended`、`texlive-fontsrecommended`、`texlive-langchinese`；双语模式还需要 `texlive-latexextra`。
- `texlive-langchinese` 提供 `ctexhook.sty`；只装 `texlive-langcjk` 会在 `CJKmainfont` 时报缺包。
- Tectonic 默认 bundle 约 2.62 GB，v1 不使用。
- `render.template` 是未来自定义版式的入口；当前不要求版式一致。
- `--pdf-engine-opt=-halt-on-error` 只用于 xelatex/lualatex，便于快速暴露错误。

### 9.2 双语双栏渲染（paracol）

`bilingual.py` 不经过 Pandoc 的单栏 PDF 路径，而是：

1. `split_markdown_blocks()` 把 `en.md` 分成 block；
2. `build_units()` 做段落级配对，图/表/公式/代码/参考文献变成 `full_width` unit；
3. 每个文本 unit 用 `pandoc -f markdown -t latex` 转为 LaTeX 片段；
4. 生成完整 `.tex`，用 `xelatex` 编译两次。

关键点：

- 需要 `texlive-latexextra` 的 `paracol`，当前只支持 `render.engine: xelatex`。
- 每对文本使用 `\begin{paracol}{2}` / `\switchcolumn` / `\switchcolumn[0]*`，`\linespread` 控制左右栏行距。
- 图表用 `\begin{center}` + `\includegraphics`/`longtable` 全宽输出，前后关闭/重开 `paracol`。
- HTML 表格保留 `rowspan`/`colspan`，由 Pandoc HTML→LaTeX 生成 `\multirow`/`\multicolumn`。
- 图注、表注和参考文献不翻译；标题双语，作者/单位区尽量保留原文。
- `fig_comments.txt` 在双语模式写 `ZH: [未翻译]`。
- 需要 `hyperref`（ORCID/email）、`amsmath`、`multirow`、`calc`、`\pandocbounded` 等 Pandoc 兼容宏。

## 10. 开发命令与测试

```bash
uv sync
uv run ptp --help
uv run ptp --dry-run -i inputs/nci195.pdf --device cpu
uv run ptp --download-model
uv run ptp -i inputs/nci195.pdf -o outputs
uv run pytest -q
uv run ruff check src tests
```

测试原则：

- 单元测试不下载模型、不跑 MinerU；
- 配置、切块、占位符、图注、表格转换、设备解析分别覆盖；
- 真实端到端测试使用 `inputs/nci195.pdf`；
- GPU/standard 测试需要 MinerU 模型和 llama.cpp GPU 后端，耗时长，不放进默认 CI。

当前实测（Ryzen 7 5800H + RTX 3050 NVK Vulkan）：

| 档位 | MinerU | 翻译 | Pandoc | 总计 |
|---|---:|---:|---:|---:|
| `flash` | 约 2.1 s | 约 46.6 s | 约 2.0 s | 约 51 s |
| `standard` | 约 16 s | 约 46 s | 约 2.1 s | 约 64 s |
| `standard` + bilingual | 约 19 s | 约 32 s | 约 8 s | 约 59 s |

双语模式已用 4 篇 PDF（4/6/9/11 页）验证；大页数论文的翻译和 XeLaTeX 编译时间会线性增加。

`llama-bench`（Vulkan1）：pp128 ≈ 1021 t/s，tg64 ≈ 78.7 t/s。

## 11. 故障排查

### Pandoc 报 `ctexhook.sty` 缺失

安装：

```bash
sudo pacman -S --needed texlive-langchinese
```

### Pandoc 报 invalid character / `^^A`

MinerU 可能输出控制字符。确认 pipeline 已调用 `sanitize_text()`；检查 `en.md` 和 `zh.md` 是否还有 `\x00-\x1f`。

### Pandoc 报 `Misplaced alignment tab character &`

通常是数学公式里的 HTML 实体 `&lt;` 被送进 LaTeX。确认 `normalize_math_entities()` 在翻译前和渲染前都执行。

### 双语模式报 `Undefined control sequence \pandocbounded`

`bilingual.py` 使用 Pandoc 转换文本块，Pandoc 可能生成 `\pandocbounded`。preamble 必须保留该宏定义；不要删除 `bilingual_preamble()` 里的兼容宏。

### 双语模式报 `Undefined control sequence \href` / `\tightlist`

preamble 需要 `hyperref`，并定义 `\tightlist`。当前 `bilingual_preamble()` 已包含。

### 翻译很慢（约 5 tok/s）

检查是否有 MinerU VLM 与 llama-server 同时占用 GPU。`standard` 必须通过 `mineru_worker` 子进程运行；不要改回进程内直接调用。

### 表格没有翻译

- `flash` 把表格放在 fenced code block 中，按代码块保留；请用 `--tier standard`。
- 检查 `standard` 的 `en.md` 是否包含 `<table>`；若包含，翻译阶段应走 HTML 表格路径。
- 检查最终 `zh.md` 是否已经由 `html_tables_to_markdown()` 转成 pipe table。

### GPU 不可用

```bash
llama-cli --list-devices
vulkaninfo --summary
```

可先用 `--device cpu` 验证逻辑，再排查 Vulkan/CUDA 后端。

### 模型文件不存在

```bash
uv run ptp --download-model
```

或把 `translation.model` 指向现有 GGUF。

## 12. 扩展点

- **自定义版式**：双语 `paracol` 已提供第一版；后续可做 bbox/HTML/CSS/LaTeX 模板、单栏/双栏切换和更细的图表布局。
- **7B 模型**：改 `translation.model`、`context_size` 和显存/内存限制；翻译接口不需要重写。
- **新翻译后端**：替换 `TranslationService.complete()` 或增加 provider 抽象。
- **更复杂的表格**：把 HTML table 转换为 LaTeX `tabular`（支持 `\multicolumn`/`\multirow`）而不是 Markdown pipe table。
- **并行**：当前是文档级；可进一步做翻译块级并发或共享 llama-server 多 slot。
- **`advanced` 档**：仅适合质量优先模式，必须显式开启并重新评估耗时/显存。

## 13. 开发约定

- 不要把 `outputs/`、`models/`、`.venv/` 提交进 git。
- 不要静默吞掉翻译占位符丢失、MinerU 失败或 Pandoc 失败。
- 修改配置字段时同步更新 `config.example.yaml`、`README.md` 和本文档。
- 修改表格/翻译逻辑时补 `tests/`，默认测试不要依赖网络或真实模型。
- GPU 相关修改必须在 `--device cpu` 下回归一次，确保 CPU 路径不坏。

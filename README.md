# ptp translates papers!: 一个PDF文献翻译工具

## 项目状态

- 目标 0（可行性）和目标 1（配置要求）已完成，结论见下文。
- 核心 Python 包、CLI、MinerU/翻译/Pandoc 管线和单元测试已落地。
- 已用真实 Hy-MT2 Q4_K_M 在 `nci195.pdf` 上跑通 `flash` 和 `standard` 端到端；`standard` 表格已翻译并渲染。
- 已实现双语双栏版式，并用 4 篇不同 PDF 做过稳健性测试。
- v1 的 10 分钟是**软目标**，不是硬性 SLA。

## 文档

- [用户手册（配置文件为主）](docs/user_manual.md)
- [开发者文档（架构、模块、调试）](docs/dev.md)

## v1 范围

- 输入带文本层的英文论文 PDF，主要场景为 4–6 页。
- MinerU 默认 `standard`；CPU 且文本层完整、无明显扫描页时自动降级到 `basic`。
- 翻译模型使用 Hy-MT2-1.8B-GGUF **Q4_K_M**；v1 不引入 7B。
- 输出单栏中文 PDF，或“左原文 / 右译文”的双语双栏 PDF；v1 不要求与原 PDF 版式一致，后续通过渲染模板扩展。
- `fig_comments.txt` 只提取论文原有图注，不生成图像描述；中英双语。
- Markdown pipe table 和 HTML table 的单元格会翻译；MinerU `flash` 的 code-fence 表格保留原文。
- 支持 CPU/GPU 和单文档/多文档并行；GPU 与并行都是可选增强。
- `config.yaml` 提供默认配置，CLI 参数可以覆盖；无参数启动时按配置处理 `inputs/`。

**v1 非目标**：扫描件也必须 10 分钟内完成、原版式复刻、图像内容描述、7B 模型、默认启用 `advanced` 档。

## 实现路径

1. 用户在 `inputs/` 下存放待翻译的英文文献（一般是 PDF）。
2. 通过 MinerU 把 PDF 转成 Markdown、图片和结构化 JSON，输出到 `temp/`。
3. 从结构化 JSON 提取图注，生成双语 `fig_comments.txt`。
4. 对 Markdown 按块使用 Hy-MT2-1.8B-GGUF 翻译成中文 Markdown。
5. 使用 Pandoc + PDF engine 把翻译后的 Markdown 渲染成 PDF。
6. 输出到 `outputs/<stem>_zh/`；按配置保留或清理 `temp/`。

链接：

1. MinerU：https://github.com/opendatalab/MinerU
2. Hy-MT2-1.8B-GGUF：https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF
3. Pandoc：https://github.com/jgm/pandoc （本地通过 `pandoc-cli` 安装，提供 `pandoc` 命令）

## 目标 0：可行性

**结论：v1 可行，但只对“带文本层的 4–6 页论文”给出参考时间，不构成硬性承诺。**

- 带文本层 4–6 页：预计 3–7 分钟（`basic`/`standard` + 1.8B Q4_K_M）。
- 扫描件、复杂表格、公式密集或页数更多：预计 8–15+ 分钟，不保证 10 分钟。
- MinerU 官方对 CPU 的定位是兼容/轻量，适合单篇处理，不适合大批量生产。
- `advanced` 默认会做图像描述和图表解析，CPU 上通常超出预算，v1 不默认启用。
- Pandoc 输出是重新排版的 PDF，不是原版式的翻译覆盖；双栏、图表位置会变化。
- 初步检查显示两个样本都含文本层，适合作为基准；第二个文件图多、文本量更大，作为压力测试。

## 目标 1：配置要求

| 项目 | 最低 | 推荐 | 说明 |
|---|---|---|---|
| CPU | 6C/12T，AVX2 | 8C/16T Zen3 / Alder Lake 或更新 | MinerU 的自动档位策略在 CPU 上需要 ≥12 逻辑核才启用 `standard`；低于此默认 `basic` |
| 内存 | 16 GB | 32 GB | MinerU `standard` 文档建议 8 GB+，加上模型、Pandoc 和系统占用；16 GB 可行但余量小 |
| GPU | 不需要 | 可选，8 GB+ VRAM | CPU-only 是 v1 目标；GPU 用于加速，不是必需 |
| 磁盘 | 10 GB 空闲 | 20 GB+ SSD | 环境约 1.3 GB + MinerU 模型约 2 GB + GGUF 1.13 GB + 输出/TeX |
| OS | Linux x86_64 / Windows | Arch Linux / Windows 11 | MinerU 和 Pandoc 都支持；GPU 后端支持因平台而异 |
| Python | 3.11–3.14 | 3.13.x / 3.14.x | 系统 Python 3.14.9；当前 uv 环境固定为 3.13.18；MinerU 4.1.7 支持 3.11–3.14 |
| 运行时 | `uv` + MinerU base（ONNX）+ llama.cpp | 同上 | CPU 环境不要装 MinerU `full`/Torch 版 |
| PDF | Pandoc 3.11 + XeLaTeX | `texlive-xetex` + `texlive-latexrecommended` + `texlive-fontsrecommended` + `texlive-langchinese` | Pandoc 单独不能生成 PDF；Tectonic 默认 bundle 约 2.62 GB，v1 不使用 |
| 字体 | 中文字体 | Noto Serif/Sans CJK SC | 已安装；Pandoc 用 `CJKmainfont` 指定 |
| 网络 | 首次下载 | 宽带 | 首次约 4 GB 环境/模型，安装+下载约 10–30+ 分钟，不计入单篇时间 |

### 时间预算（估算）

| 阶段 | 带文本层 4–6 页 | 扫描件/复杂版式 |
|---|---:|---:|
| MinerU `basic`/`standard` | 0.5–2.5 分钟 | 3–6 分钟 |
| Hy-MT2 1.8B Q4 翻译 | 1.5–4 分钟 | 3–6 分钟 |
| Pandoc + PDF engine | 5–30 秒 | 5–30 秒 |
| **合计** | **约 3–7 分钟** | **约 8–15+ 分钟** |

### 当前环境

- Arch Linux；系统 Python 3.14.9；`uv` 0.13.7；`pip` 未安装。使用 `uv` 管理环境。
- Pandoc 3.11 和 XeLaTeX 已安装；`texlive-langchinese` 提供 `ctexhook.sty`，`CJKmainfont` 可用；`texlive-latexextra` 提供双语版式所需的 `paracol`。
- MinerU 4.1.7、llama.cpp（Vulkan 后端）和 Python 依赖已安装；Hy-MT2 Q4_K_M 已下载到 `models/`。
- 当前 `uv` 环境使用 Python 3.13.18；`uv.lock` 已生成。
- Noto Sans/Serif CJK SC 已安装（`/usr/share/fonts/noto-cjk/`）。
- 当前机器：Ryzen 7 5800H（8C/16T，Zen3）、13 GiB 可见内存、NVMe。
- Vulkan 已可用：NVIDIA RTX 3050（NVK，4 GB）和 AMD Radeon iGPU（RADV）都被 `llama.cpp` 识别；`llama-server` + 真实 Hy-MT2 Q4_K_M 已在 Vulkan1 上跑通。CUDA 未安装。
- 并行路径仍需单独验证；GPU 模式下默认限制为单文档，避免 4 GB 显存争用。

## 设计决策

1. **10 分钟是软目标**：普通带文本层论文目标 5–10 分钟；复杂件允许更久。不设置硬超时，不为了 10 分钟牺牲翻译质量。
2. **v1 不要求版式一致**：翻译和渲染分离；保留 MinerU 的结构化 JSON，未来通过 `render.template` 或独立布局器实现用户自定义版式。当前输出是重排 PDF。
3. **固定 Q4_K_M**：使用 Hy-MT2-1.8B-GGUF 的 Q4_K_M（约 1.13 GB）；v1 不做 7B。不要使用 1.25-bit/2-bit 版本（需要特殊 STQ kernel，质量也不稳）。翻译层保留模型接口，后续可加 7B 预设。
4. **MinerU `tier: auto`**：GPU 环境用 `standard`；CPU + 文本覆盖率高 + 无明显扫描页时用 `basic`；其余用 `standard`。复杂表格/公式可用 `--tier standard` 强制覆盖。判定结果写入日志。
5. **`fig_comments.txt` 是双语图注索引**：只提取论文原有图注，不生成图像描述；从 MinerU 结构化 JSON 提取，中英双语。缺图注写 `[no caption]` / `[无图注]`。
6. **并行与 GPU 都是可选增强**：`--parallel N` 只表示多文档并行，默认 1；`--device auto|cpu|gpu` 控制设备，`--gpu-only`/`--cpu-only` 是别名。`--gpu-only` 在检测不到 GPU 时明确报错，不静默降级。
7. **`config.yaml` + 双击执行（规划）**：config 提供默认值，CLI 覆盖 config。当前 CLI 从工作目录读取 `config.yaml`；Windows `ptp.exe` 打包和双击读取同目录配置属于后续工作。相对路径按配置文件所在目录解析。

## CLI

```bash
# 单篇；输出根目录为 outputs/
uv run ptp -i inputs/nci195.pdf -o outputs

# 批量；成功结束后不保留 temp
uv run ptp -i inputs/*.pdf -o outputs --no-temp

# 16 线程；等价于 --threads 16
uv run ptp -i inputs/*.pdf -o outputs --task16

# 使用 config.yaml，无其他参数
uv run ptp
```

Windows 打包后的命令名是 `ptp.exe`；Linux/开发环境使用 `ptp`。

| 选项 | 说明 |
|---|---|
| `-i, --input PATH...` | 输入 PDF，可多个 |
| `-o, --output DIR` | 输出根目录，默认 `outputs/`；不是 PDF 文件路径 |
| `--config PATH` | 配置文件路径 |
| `--tier auto\|flash\|basic\|standard\|advanced` | MinerU 档位，默认 `auto` |
| `--device auto\|cpu\|gpu` | 设备选择，默认 `auto` |
| `--cpu-only` / `--gpu-only` | `--device cpu/gpu` 的别名；互斥 |
| `--gpu-backend auto\|cuda\|vulkan\|metal` | GPU 后端；`auto` 自动检测 |
| `--gpu-index N` | llama.cpp GPU 索引 |
| `--server-url URL` | 使用已在运行的 llama-server，不自动启动 |
| `--model FILE` | 指定 GGUF 路径 |
| `--layout single\|bilingual` | 单栏或双语双栏输出 |
| `--engine ENGINE` | `xelatex`/`lualatex`/`tectonic`/`typst` |
| `--threads N` | CPU 线程数 |
| `--task16` | 等价于 `--threads 16`；不是 16 个并行任务 |
| `--parallel N` | 同时处理的文档数，默认 1 |
| `--no-temp` / `--keep-temp` | 成功结束后删除/保留 `temp/`；默认保留 |
| `--resume` | 复用已有中间结果 |
| `--dry-run` | 打印解析后的配置和任务，不执行 |
| `--log-level` | 日志级别 |

## config.yaml

完整示例见 `config.example.yaml`。最高优先级是 CLI，其次是 `config.yaml`，最后是内置默认值。

```yaml
version: 1
input: inputs
output: outputs
keep_temp: true
resume: false
threads: auto
parallel: 1
device: auto
gpu_backend: auto
gpu_index: null

mineru:
  tier: auto
  auto_basic_text_coverage: 0.8
  image_analysis: false

translation:
  model: models/Hy-MT2-1.8B-Q4_K_M.gguf
  server_bin: llama-server
  server_url: null
  chunk_tokens: 800
  gpu_layers: auto
  context_size: 4096
  glossary: null

render:
  layout: single
  engine: xelatex
  cjk_font: Noto Serif CJK SC
  template: null
  source_ratio: 0.48
  source_line_spacing: 1.35
  target_line_spacing: 1.15
  figure_max_height: 0.45
```

说明：

- `threads: auto` 使用可用 CPU 核心；`--task16`/`--threads 16` 可覆盖。
- `parallel` 是文档级并行；16 GB 内存建议保持 1。
- `mineru.auto_basic_text_coverage` 是 CPU 自动降级阈值；GPU 下默认 `standard`。
- `translation.model` 可写绝对路径或相对 config 的路径；模型文件需在运行前准备好。
- `render.template` 为后续自定义版式预留，v1 可以为空。
- 当前 CLI 从工作目录查找 `config.yaml`；Windows 打包后计划从可执行文件目录查找。

### 双击执行（规划）

当前尚未实现 Windows 打包；以下是打包后的目标行为：

- Windows：`ptp.exe` 读取同目录 `config.yaml`；没有 `-i` 时处理 `input` 配置指定的目录（默认 `inputs/`）；错误时暂停，避免窗口直接关闭。
- Linux：使用 `.desktop` 文件或启动脚本调用 `ptp`；`ptp.exe` 是 Windows 产物名。
- 没有 `config.yaml` 时使用内置默认值；建议随包提供 `config.example.yaml`，不要覆盖用户配置。

## 输出结构

```text
outputs/
  nci195_zh/
    temp/
      image/
        fig1.jpg
        fig2.jpg
        ...
        fig_comments.txt
      nci195_en.md
      nci195_zh.md
      nci195_content_list.json
      state.json
    nci195_zh.pdf
```

- 单栏输出为 `nci195_zh.pdf`；`--layout bilingual` 输出为 `nci195_bilingual.pdf`。
- `temp/` 在成功结束后按 `--no-temp`/`keep_temp` 清理；失败时保留，方便续跑。
- `nci195_content_list.json` 是 MinerU 的结构化输出，用于图注映射和未来版式功能；`state.json` 记录阶段、耗时、tier/device、可续跑状态。
- `fig_comments.txt` 格式：

```text
fig1.jpg
EN: Figure 1. Overview of the experimental setup.
ZH: 图 1. 实验装置概览。

fig2.jpg
EN: Figure 2. ...
ZH: 图 2. ...
```

缺图注时写 `EN: [no caption]` / `ZH: [无图注]`。多 panel 图按 MinerU 输出的图片文件逐项记录；同一图注覆盖多个 panel 时允许重复。图注由翻译阶段一并翻译。

## 工作流细节

### MinerU tier auto

- `auto` 判定：
  - GPU：`standard`。
  - CPU + 文本覆盖率 ≥ `auto_basic_text_coverage` + 无明显扫描页：`basic`。
  - CPU + 扫描页：`standard`；复杂表格/公式可手动 `--tier standard`。
- 文本覆盖率用 PDF 文本层估算（例如 pypdfium2）；任何一页文本过少，视为扫描页。该启发式不判断表格复杂度。
- MinerU 自身会在 text layer/OCR 之间选择；`auto` 只是额外的速度/质量策略。判定错误时 `basic` 仍会 OCR，不会完全失败。
- `standard` 的 VLM 可能拆分多 panel 图，影响图注对齐；需要用两个样本对比 `basic` 和 `standard`，必要时对 JSON 做后处理或改用 `basic` 提取图注。

### 翻译

- 按段落/章节切块，建议 `chunk_tokens <= 1000`，默认 800；不要把整篇 Markdown 一次性送入 1.8B 模型。
- 保护 Markdown 结构、LaTeX 公式、引用、图片链接和占位符；使用 Hy-MT2 的结构化数据指令模板。
- 受保护片段使用 ASCII `@@P0@@` 占位符；模型丢失占位符时先重试，再按片段只翻译普通文本，公式/引用/图片原样拼回。
- 采样参数默认 temperature 0.3、top_p 0.6、top_k 20、repetition_penalty 1.05（模型卡参考值是 0.7；可在 config 中调整并做小范围对比）。
- 每块校验：目标语言、长度比例、原文直出、重复/漏翻；失败重试一次，仍失败则记录并继续。
- 可选术语表 `glossary`；v1 不引入 7B。

### 并行与 GPU

- `--parallel N` 只并行多个文档；默认 1。16 GB CPU 建议 1，32 GB 或纯文本小文件可尝试 2。
- GPU 模式复用同一个 llama.cpp server；不要为每个文档启动一份模型。
- `--device auto` 自动选择 CUDA/Vulkan/Metal/CPU；`--gpu-only` 检测失败时明确报错。
- MinerU 的 CPU base（ONNX）与 GPU 依赖不同；GPU 可能需要 `full`/Torch 或 Vulkan/WebGPU，安装文档需分开。
- 当前机器已用 NVIDIA NVK Vulkan 验证 `llama-server` + 真实 Hy-MT2；CUDA 尚未验证。
- `--parallel` 仍是实验性能力：MinerU 阶段会串行加锁，翻译请求由 llama-server 的 slot 排队；16 GB 内存建议保持 1。

### 双语双栏版式

```bash
uv run ptp -i inputs/nci195.pdf -o outputs --layout bilingual
```

或：

```yaml
render:
  layout: bilingual
  source_ratio: 0.48
  source_line_spacing: 1.35
  target_line_spacing: 1.15
  figure_max_height: 0.45
```

行为：

- 标题全宽双语；正文按段落左原文、右译文。
- 图片、表格跨双栏，只出现一次；图注、表注保留原文，不翻译。
- 表格保留原文；HTML 表格会保留 `rowspan`/`colspan` 转成 LaTeX。
- 参考文献从标题开始保留原文并全宽显示。
- 输出文件为 `outputs/<stem>_zh/<stem>_bilingual.pdf`，不覆盖单栏 `_zh.pdf`。
- 双语模式当前要求 `render.engine: xelatex`，并需要 `texlive-latexextra` 提供的 `paracol`。
- 对齐是段落级：左右栏在段落边界同步；长度差异会产生留白，不逐句对齐。
- `fig_comments.txt` 在双语模式仍会生成，但 `ZH` 标记为 `[未翻译]`。

### 已知限制

- 已支持 Markdown pipe table 和 HTML table 的单元格翻译；MinerU `flash` 把表格放进 code fence 时仍按代码块保留，推荐用 `standard` 处理表格。
- `standard` 的 VLM 可能拆分多 panel 图，图注映射需要实测后调优。
- GPU 模式下 `--parallel` 自动限制为 1，避免 4 GB 显存争用。
- 双语模式保留 HTML 表格的 `rowspan`/`colspan`；单栏模式的 Markdown 表格仍会展开成近似网格。
- 双语的列宽、行距和图表最大高度可配置；不同论文的标题/作者区识别仍需继续实测。
- 复杂内联标记/公式块如果模型丢失占位符，程序会先按受保护片段切分重译，仍失败才保留原文并记录 warning，而不是生成损坏的 LaTeX。

## 开发命令

```bash
uv sync
uv run ptp --help
uv run ptp --dry-run -i inputs/nci195.pdf --device cpu
uv run ptp --download-model
uv run ptp -i inputs/nci195.pdf -o outputs
uv run pytest -q
uv run ruff check src tests
```

`ptp --download-model` 下载 `tencent/Hy-MT2-1.8B-GGUF` 的 `Hy-MT2-1.8B-Q4_K_M.gguf` 到 `models/`。

## 验证与测试

- 快速 fixture：`inputs/nci195.pdf`（4 页）。
- 压力 fixture：`Operation...`（6 页）、`mfortuna...`（9 页）、`s41598...`（11 页）。
- 已通过：真实 Hy-MT2 Q4_K_M + `flash` / `standard` 档的端到端测试；输出 PDF、双语 `fig_comments.txt`、`--no-temp` 清理和 `--resume` 均已验证。
- `nci195.pdf` 实测（RTX 3050 / NVK Vulkan）：
  - `flash`：MinerU 2.1 s、翻译 46.6 s、Pandoc 2.0 s，总计约 51 s；8 页、473 KB。
  - `standard`：MinerU 15.7–16.5 s、翻译 45–46 s、Pandoc 2.1 s，总计约 63–65 s；7 页、470 KB；HTML 表格已翻译并转成 Markdown 表格。
- `llama-bench`：Q4_K_M 在 Vulkan1 上 pp128 ≈ 1021 t/s、tg64 ≈ 78.7 t/s（Arch 包的 asserts 版本，非最终性能）。
- 双语双栏已用 4 篇 PDF 跑通：9/16/27/23 页，图、表、参考文献和分页均能生成；单篇翻译耗时随页数增加。
- 单元测试已覆盖配置优先级、文本覆盖率判定、图注映射、切块/保护、Markdown/HTML 表格翻译、双语 block 配对和 CLI dry-run。
- 待完成：CUDA/parallel 真机验证。
- 基准脚本：后续添加 `scripts/bench.py`，记录每阶段耗时、tokens/s、峰值内存、选中的 tier/device。

## 任务清单

- [x] 评估实现的可行性
- [x] 预估这个工作流的配置要求
- [x] 优化这个工作流
- [x] 实现这个工作流（Python）
- [x] 制作 CLI 和 `config.yaml`
- [x] 实现 Markdown/HTML 表格翻译
- [x] 完成真实模型 + `standard` 档的本地测试和基准
- [x] 实现双语双栏版式并完成多样本测试
- [ ] 验证 CUDA/parallel（有硬件时）
- [ ] 添加可选项（自定义版式、7B 等后续）

## 后续工作

- 自定义版式：基于保留的结构化 JSON/bbox 和渲染模板，支持用户模板/字体/页边距。
- 7B 模型预设：只改 `translation.model` 和资源限制，不改主流程。
- GPU 后端实测：CUDA/Vulkan/Metal 分别验证。
- `advanced` 档评估：仅在质量优先模式启用。

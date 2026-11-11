# PTP Translates Papers — 用户手册

> A:什么是ptp?

> B: ptp translates papers!

> A: 所以什么是ptp?

> B: ptp translates papers!

## 0. 这篇文章是干什么的?

本文主要说明 **`config.yaml` 如何设置**，并给出安装、运行和常见问题。功能与快速开始见 [README.md](../README.md)，开发者细节见 [dev.md](dev.md)。

## 1. 它能做什么

PTP 把英文论文 PDF 转成中文 PDF：

```text
inputs/*.pdf
  → MinerU 解析为 Markdown + 图片 + 结构化 JSON
  → Hy-MT2-1.8B Q4_K_M 分块翻译
  → Pandoc + XeLaTeX 生成中文 PDF
```

输出目录：

```text
outputs/
  nci195_zh/
    temp/
      image/
        fig1.jpg
        ...
        fig_comments.txt
      nci195_en.md
      nci195_zh.md
      nci195_content_list.json
      state.json
    nci195_zh.pdf          # 单栏
    nci195_bilingual.pdf   # --layout bilingual
```

- `fig_comments.txt` 是论文原有图注的中英双语索引，不是模型生成的新描述。
- Markdown pipe table 和 HTML table 会翻译；MinerU `flash` 把表格放在 code fence 里时不翻译，表格请用 `standard`。
- 输出 PDF 是重新排版的，不保证与原 PDF 版式一致。

### 1.1 项目范围与非目标

- 主要输入是带文本层的英文论文 PDF，典型场景 4–6 页；扫描件、复杂表格和公式密集论文也可以处理，但更慢。
- 翻译模型固定为 Hy-MT2-1.8B-GGUF **Q4_K_M**；v1 不引入 7B。
- 单栏输出中文 PDF；双语模式输出“左原文 / 右译文”的双栏 PDF。
- CPU 和 GPU 都支持；GPU 和文档级并行都是可选增强。
- 10 分钟是**软目标**，不是硬性 SLA。

**v1 非目标**：扫描件也必须 10 分钟内完成、复刻原 PDF 版式、生成图像内容描述、7B 模型、默认启用 `advanced` 档。

### 1.2 时间与硬件

时间预算（带文本层 4–6 页）：

| 阶段 | 普通论文 | 扫描件/复杂版式 |
|---|---:|---:|
| MinerU `basic`/`standard` | 0.5–2.5 分钟 | 3–6 分钟 |
| Hy-MT2 1.8B Q4 翻译 | 1.5–4 分钟 | 3–6 分钟 |
| Pandoc + PDF engine | 5–30 秒 | 5–30 秒 |
| **合计** | **约 3–7 分钟** | **约 8–15+ 分钟** |

硬件建议：

| 项目 | 最低 | 推荐 | 说明 |
|---|---|---|---|
| CPU | 6C/12T，AVX2 | 8C/16T Zen3 / Alder Lake 或更新 | CPU 自动档位会参考逻辑核数 |
| 内存 | 16 GB | 32 GB | MinerU、模型、Pandoc 和系统同时占用 |
| GPU | 不需要 | 8 GB+ VRAM | GPU 是加速项，不是必需 |
| 磁盘 | 10 GB 空闲 | 20 GB+ SSD | 环境、MinerU 模型、GGUF 和 TeX 输出 |
| OS | Linux x86_64 / Windows | Arch Linux / Windows 11 | GPU 后端支持因平台而异 |
| Python | 3.11–3.14 | 3.13.x | 由 `uv` 管理 |
| 网络 | 首次下载 | 宽带 | 首次安装环境/模型约 4 GB，10–30+ 分钟 |

### 1.3 工作流

1. 把英文论文 PDF 放到 `inputs/`，或通过 `-i` 指定。
2. MinerU 解析为 Markdown、图片和结构化 JSON，中间文件写入 `temp/`。
3. 从结构化 JSON 提取图注，生成双语 `fig_comments.txt`。
4. 对 Markdown 按块使用 Hy-MT2 翻译成中文。
5. 表格按 Markdown/HTML 路径翻译并转换。
6. Pandoc + XeLaTeX 生成单栏或双语 PDF，输出到 `outputs/<stem>_zh/`；`state.json` 支持续跑。

## 2. 安装与首次运行

系统依赖（Arch Linux）：

```bash
sudo pacman -S --needed pandoc-cli llama-cpp
sudo pacman -S --needed texlive-xetex texlive-latexrecommended \
  texlive-fontsrecommended texlive-langchinese texlive-latexextra

# 可选：Vulkan GPU 路径（AMD iGPU 或 NVIDIA NVK）
sudo pacman -S --needed vulkan-radeon vulkan-tools ggml-vulkan
```

说明：

- `pandoc-cli` 提供 `pandoc`；Arch 没有名为 `pandoc` 的包。
- XeLaTeX 需要 `texlive-langchinese` 提供 `ctexhook.sty`；只装 `texlive-langcjk` 不够。
- Tectonic 默认 bundle 约 2.62 GB，v1 实际使用 XeLaTeX。
- Vulkan 包是可选的；没有 GPU 时可用 `--device cpu`。

Python 环境和模型：

```bash
cd /home/storm/src/ptp

# 方式 A：开发环境，MinerU 与 PTP 共用 venv
uv sync --extra mineru

# 方式 B：推荐发行方式，MinerU 独立 venv
uv sync
uv run ptp-install-mineru --accept-license

uv run ptp --download-model
```

方式 B 会把 MinerU 安装到独立目录，并打印 `mineru.python` 配置。MinerU 仍按其自身许可证分发，不进入 PTP 的 GPL 代码范围。`--download-model` 会把 `Hy-MT2-1.8B-Q4_K_M.gguf`（约 1.1 GB）下载到 `models/`。MinerU 首次运行还会下载自己的 OCR/VLM/表格模型，缓存在 `~/.mineru/models/`。

快速运行：

```bash
# 直接指定输入/输出
uv run ptp -i inputs/nci195.pdf -o outputs

# 使用 config.yaml
cp config.example.yaml config.yaml
uv run ptp
```

## 3. 配置文件位置与优先级

程序按以下顺序找配置：

1. `--config FILE` 指定；
2. 当前工作目录的 `./config.yaml`；
3. 都没有时使用内置默认值。

优先级：

```text
CLI 显式参数 > config.yaml > 内置默认值
```

几个容易混淆的规则：

- 配置文件里的相对路径按 **配置文件所在目录** 解析。
- CLI 的 `-o`、`--model` 等相对路径按 **当前工作目录** 解析。
- `-o` 是**输出根目录**，不是 PDF 文件路径。
- `--task16` 是 `--threads 16`，不是 16 个并行任务；并行用 `--parallel`。
- 配置里未知的键会报错，避免拼写错误被忽略。
- `version` 目前只支持 `1`。

当前还没有 Windows 双击打包；`ptp.exe` 是未来产物名。现在 Linux 下直接使用 `uv run ptp` 或 `ptp`。双击启动时从程序目录读取 `config.yaml` 的行为属于后续打包工作。

## 4. 完整配置示例

```yaml
version: 1

# 输入目录或单个 PDF；相对路径按 config.yaml 所在目录解析
input: inputs
# 输出根目录；每个输入生成 <stem>_zh/ 子目录
output: outputs

# 成功后是否保留 temp/；失败时无论此值都会保留
keep_temp: true
# 复用已完成的阶段；改变 tier/device 时建议清理 temp/ 或换输出目录
resume: false

# CPU 线程数：整数或 "auto"；--task16 等价于 16
threads: auto
# 同时处理的文档数；GPU 模式会自动限制为 1
parallel: 1

# auto | cpu | gpu
device: auto
# auto | cuda | vulkan | metal
gpu_backend: auto
# llama.cpp GPU 索引；null 表示自动优先独显
gpu_index: null

mineru:
  # auto | flash | basic | standard | advanced
  tier: auto
  # CPU 自动降级 basic 的文本覆盖率阈值（0–1）
  auto_basic_text_coverage: 0.8
  # 是否让 MinerU VLM 额外分析图片内容；默认关闭，开启会更慢
  image_analysis: false
  # 独立 MinerU venv 的 Python；null = 使用 PTP 的 Python
  python: null
  # auto | huggingface | modelscope | local
  model_source: auto
  # MinerU 模型根目录；null = ~/.mineru/models
  model_dir: null

translation:
  # 本地 GGUF 路径；相对 config.yaml
  model: models/Hy-MT2-1.8B-Q4_K_M.gguf
  # llama.cpp server 可执行文件
  server_bin: llama-server
  # 使用已运行的 server 时填写，例如 http://127.0.0.1:8080
  server_url: null
  host: 127.0.0.1
  port: 0                 # 0 = 自动选择空闲端口
  threads: null           # null = 跟随顶层 threads
  gpu_layers: auto        # auto 或整数；GPU 默认 99 层
  chunk_tokens: 800       # 翻译块大小
  temperature: 0.3
  top_p: 0.6
  top_k: 20
  repetition_penalty: 1.05
  max_tokens: 2048
  timeout: 600            # 单次请求超时，秒
  context_size: 4096      # llama-server 上下文
  glossary: null          # 术语表文件路径

render:
  # single | bilingual
  layout: single
  # xelatex | lualatex | tectonic | typst
  engine: xelatex
  cjk_font: Noto Serif CJK SC
  # 预留：后续自定义版式模板
  template: null
  # bilingual 专用：左栏比例、左右行距、图表最大高度
  source_ratio: 0.48
  source_line_spacing: 1.35
  target_line_spacing: 1.15
  figure_max_height: 0.45
```

## 5. 顶层配置说明

| 键 | 默认 | 说明 |
|---|---|---|
| `version` | `1` | 配置格式版本；目前只支持 1 |
| `input` | `inputs` | PDF 文件或目录 |
| `output` | `outputs` | 输出根目录 |
| `keep_temp` | `true` | 成功后保留 `temp/`；失败时总是保留 |
| `resume` | `false` | 复用已完成的 MinerU/翻译/PDF |
| `threads` | `auto` | CPU 线程数；整数或 `auto` |
| `parallel` | `1` | 文档级并行数；GPU 模式强制为 1 |
| `device` | `auto` | `auto` / `cpu` / `gpu` |
| `gpu_backend` | `auto` | `auto` / `cuda` / `vulkan` / `metal` |
| `gpu_index` | `null` | llama.cpp 设备索引；`null` 自动优先独显 |

### `device` 怎么选

- `auto`：有可用 GPU 时优先独显，否则 CPU。
- `cpu`：强制 CPU；适合没有 GPU 或调试。
- `gpu`：必须有可用 GPU；找不到会报错，不会静默降级。
- `--gpu-only` / `--cpu-only` 是 `--device gpu/cpu` 的别名。

### `gpu_backend` 和 `gpu_index`

- `vulkan`：当前 Linux 上验证过的路径（NVIDIA NVK / AMD RADV）。
- `cuda`：需要 CUDA 版 llama.cpp；当前环境未验证。
- `metal`：macOS。
- `gpu_index` 对应 `llama-cli --list-devices` 的编号。一般不需要设置。

### `parallel` 的注意点

- `1`：推荐值，16 GB 内存或 4 GB 显存都建议保持 1。
- CPU 且内存充足时可尝试 2；每个文档会各自启动一个 llama-server。
- GPU 模式下程序会自动把并行降为 1，避免显存争用。
- `--parallel` 仍是实验性能力：MinerU 阶段会串行加锁，翻译请求由各自的 llama-server 处理。

## 6. `mineru` 配置

| 键 | 默认 | 说明 |
|---|---|---|
| `tier` | `auto` | `auto` / `flash` / `basic` / `standard` / `advanced` |
| `auto_basic_text_coverage` | `0.8` | CPU 自动降级 `basic` 的文本覆盖阈值 |
| `image_analysis` | `false` | 是否启用 MinerU VLM 图片分析；会增加耗时 |
| `python` | `null` | 独立 MinerU venv 的 Python；`null` 使用 PTP 的 Python |
| `model_source` | `auto` | `auto` / `huggingface` / `modelscope` / `local` |
| `model_dir` | `null` | MinerU 模型根目录；`null` 使用 `~/.mineru/models` |

### tier 怎么选

- `flash`：最快，直接读文本层；表格可能变成 code fence，结构较差。适合预览。
- `basic`：ONNX 小模型，速度和结构平衡；适合带文本层、表格/公式不多的论文。
- `standard`：默认推荐；加 VLM，复杂版面、公式和表格更好。**需要翻译表格时用这个。**
- `advanced`：更多 VLM 计算，CPU 上很慢；v1 不默认使用。

`auto` 规则：

- GPU：`standard`。
- CPU 且文本覆盖率高、没有低文本页：`basic`。
- 其他：`standard`。

该规则不判断表格复杂度；表格多时请显式 `--tier standard`。

`standard` 的 VLM 可能把多 panel 图拆成多个图片，影响图注对齐；需要对比 `basic` 和 `standard`，必要时对结构化 JSON 做后处理或改用 `basic` 提取图注。

## 7. `translation` 配置

| 键 | 默认 | 说明 |
|---|---|---|
| `model` | `models/Hy-MT2-1.8B-Q4_K_M.gguf` | 本地 GGUF 路径 |
| `server_bin` | `llama-server` | llama.cpp server 程序名 |
| `server_url` | `null` | 使用外部 server；设置后不本地启动 |
| `host` | `127.0.0.1` | 本地 server 监听地址 |
| `port` | `0` | `0` 表示自动找空闲端口 |
| `threads` | `null` | `null` 跟随顶层 `threads` |
| `gpu_layers` | `auto` | GPU 默认 99；CPU 为 0 |
| `chunk_tokens` | `800` | 翻译块大小，建议不超过 1000 |
| `temperature` | `0.3` | 采样温度；模型卡参考值是 0.7 |
| `top_p` | `0.6` | 采样参数 |
| `top_k` | `20` | 采样参数 |
| `repetition_penalty` | `1.05` | 重复惩罚 |
| `max_tokens` | `2048` | 单块最大输出 |
| `timeout` | `600` | 单次 HTTP 请求超时，秒 |
| `context_size` | `4096` | llama-server 上下文大小 |
| `glossary` | `null` | 术语表文件路径 |

### 模型和 server

- 本地模式：`server_url: null`，程序自动启动 `llama-server`。
- 外部模式：先手动启动 server，再设置：

```yaml
translation:
  server_url: http://127.0.0.1:8080
```

外部模式仍需要 MinerU 的 GPU/CPU 设置；`model` 字段不参与本地启动。

### 采样参数怎么调

- 默认 `temperature: 0.3` 更稳定，适合论文。
- 想更贴近模型卡，可试 `0.7`；但可能更自由、术语更不稳定。
- `chunk_tokens` 不建议超过 1000；1.8B 模型长上下文容易漏翻/直出原文。
- `max_tokens` 应小于 `context_size - chunk_tokens` 的余量；默认 800 + 2048 在 4096 上下文内基本安全。

### 占位符与回退

- Markdown 结构、LaTeX 公式、引用、图片链接会替换成 ASCII 占位符（如 `@@P0@@`）。
- 模型丢失占位符时先重试一次；仍失败则按受保护片段切分，只翻译普通文本，公式/引用/图片原样拼回。
- 最终仍失败才保留原文并记录 warning；`temp/state.json` 的 `translation_fallbacks` 会记录次数。
- 图注、表注、表格内容和参考文献在双语模式下本来就保留原文，不属于回退失败。

### 表格翻译

- Markdown pipe table 和 HTML table 按单元格翻译。
- MinerU `flash` 把表格放进 fenced code block 时不翻译；需要表格翻译时用 `--tier standard`。
- 双语模式保留 HTML 表格的 `rowspan`/`colspan`；单栏模式会展开成近似网格。
- 表注和单元格内的公式/单位会尽量保留原样。

### 术语表

`glossary` 指向文本文件：

```text
Blanket region = 包层区域
Facing surface	迎向表面
Vacuum vessel = 真空容器
```

支持 `=` 或制表符分隔；`#` 开头为注释。对固定领域术语（如聚变、医学、材料）很有用。

## 8. `render` 配置

| 键 | 默认 | 说明 |
|---|---|---|
| `layout` | `single` | `single` 单栏中文；`bilingual` 左原文右译文 |
| `engine` | `xelatex` | `xelatex` / `lualatex` / `tectonic` / `typst` |
| `cjk_font` | `Noto Serif CJK SC` | 中文字体 |
| `template` | `null` | 预留的自定义版式模板路径 |
| `source_ratio` | `0.48` | 双语左栏宽度比例 |
| `source_line_spacing` | `1.35` | 原文行距 |
| `target_line_spacing` | `1.15` | 译文行距 |
| `figure_max_height` | `0.45` | 全宽图片最大高度（相对 `\textheight`） |

- 当前实际验证的是 `xelatex`。
- `tectonic`/`typst` 虽在 CLI 中可选，但未作为 v1 默认路径验证；Tectonic 首次运行会拉取约 2.62 GB bundle。
- 中文字体建议保持 Noto CJK；系统已安装 `Noto Serif CJK SC` 和 `Noto Sans CJK SC`。
- `template` 目前只透传给 Pandoc；真正的自定义版式是后续功能。

### 双语双栏

```yaml
render:
  layout: bilingual
  engine: xelatex
  source_ratio: 0.48
  source_line_spacing: 1.35
  target_line_spacing: 1.15
  figure_max_height: 0.45
```

或：

```bash
uv run ptp -i inputs/nci195.pdf -o outputs --layout bilingual
```

行为：

- 标题全宽双语；正文段落左原文、右译文，段落边界同步。
- 图片、表格跨双栏且只出现一次；图注、表注保留原文。
- 表格保留原文；HTML 表格会保留合并单元格。
- 参考文献保留原文并全宽显示。
- 页脚注不进入正文，统一放到文末 `Notes / 注释` 小节。
- 被图片/表格隔开的续段会自动合并后再翻译。
- `<sup>`/`<sub>` 会正确渲染成上标/下标。
- 输出 `outputs/<stem>_zh/<stem>_bilingual.pdf`，不覆盖单栏 PDF。
- 需要安装 `texlive-latexextra`（提供 `paracol`），且当前只支持 `engine: xelatex`。
- `fig_comments.txt` 仍生成，但双语模式 `ZH` 为 `[未翻译]`。
- 左右栏不逐句对齐；长度差异会产生留白。长段落跨页时左右栏可能因中英文长度不同而漂移。
- 页脚注统一放到文末，不放在原页底部；对齐是段落级，句级对齐属于后续工作。

## 9. 常用配置方案

### 方案 A：16 GB 内存、无独显、质量优先

```yaml
device: cpu
threads: 8
parallel: 1
mineru:
  tier: auto
translation:
  chunk_tokens: 800
  context_size: 4096
render:
  engine: xelatex
```

带文本层的论文会自动用 `basic`；表格/公式多时手动 `--tier standard`。

### 方案 B：4 GB 显存、Vulkan、表格论文

```yaml
device: gpu
gpu_backend: vulkan
gpu_index: 1
parallel: 1
mineru:
  tier: standard
render:
  engine: xelatex
```

`gpu_index` 请先用 `llama-cli --list-devices` 确认；不同机器编号不同。

### 方案 C：外部 llama-server

```yaml
translation:
  server_url: http://127.0.0.1:8080
```

适合多篇论文共用同一个模型进程，或把翻译服务放在另一台机器。

### 方案 D：先快速预览

```yaml
mineru:
  tier: flash
keep_temp: false
```

速度最快，但表格/结构质量差，不建议作为最终输出。

## 10. CLI 覆盖

CLI 参数会覆盖 config：

```bash
uv run ptp -i inputs/nci195.pdf -o outputs
uv run ptp -i inputs/*.pdf -o outputs --tier standard --device gpu
uv run ptp --config config.yaml --dry-run
uv run ptp --task16
uv run ptp --no-temp
uv run ptp --resume
uv run ptp --download-model
```

常用选项：

| 选项 | 说明 |
|---|---|
| `-i, --input` | 输入 PDF 或目录 |
| `-o, --output` | 输出根目录，不是 PDF 路径 |
| `--config` | 指定 config.yaml |
| `--tier` | 覆盖 MinerU 档位 |
| `--mineru-python` | 独立 MinerU venv 的 Python |
| `--mineru-model-source` | `auto`/`huggingface`/`modelscope`/`local` |
| `--mineru-model-dir` | MinerU 模型根目录 |
| `--device` | `auto`/`cpu`/`gpu` |
| `--cpu-only` / `--gpu-only` | 设备别名 |
| `--gpu-backend` | `auto`/`cuda`/`vulkan`/`metal` |
| `--gpu-index` | GPU 编号 |
| `--threads` | CPU 线程数 |
| `--task16` | 等价于 `--threads 16`；不是 16 个并行任务 |
| `--parallel` | 文档级并行 |
| `--no-temp` / `--keep-temp` | 是否保留中间文件 |
| `--resume` | 复用已完成阶段 |
| `--server-url` | 外部 llama-server |
| `--model` | 覆盖 GGUF 路径 |
| `--layout` | `single` 或 `bilingual` |
| `--engine` | PDF 引擎 |
| `--dry-run` | 只打印配置和任务 |
| `--log-level` | 日志级别 |
| `--download-model` | 下载 Q4_K_M |

## 11. 输出与清理

- 单栏输出：`outputs/<stem>_zh/<stem>_zh.pdf`。
- 双语输出：`outputs/<stem>_zh/<stem>_bilingual.pdf`。
- 默认保留 `temp/`；`--no-temp` 在成功结束后删除。
- 失败时保留 `temp/`，方便排查和 `--resume`。
- `--resume` 依赖 `state.json`；如果改了 tier/device，建议换输出目录或删除旧 `temp/`。
- `fig_comments.txt` 位于 `temp/image/`，包含 `EN:` 和 `ZH:` 两行。
- 图片按 `fig1.jpg`、`fig2.jpg` 重命名；公式/表格图片保留 MinerU 原名。

`fig_comments.txt` 格式：

```text
fig1.jpg
EN: Figure 1. Overview of the experimental setup.
ZH: 图 1. 实验装置概览。
```

缺图注时写 `EN: [no caption]` / `ZH: [无图注]`。多 panel 图按 MinerU 输出的图片文件逐项记录；同一图注覆盖多个 panel 时允许重复。双语模式下 `ZH` 为 `[未翻译]`。

## 12. 常见问题

### 报错 `unknown key(s) in config`

配置拼写错误。对照 `config.example.yaml` 修改；程序不会静默忽略未知键。

### 报错 `model not found`

```bash
uv run ptp --download-model
```

或把 `translation.model` 指向已有 GGUF。

### 报错 `requested GPU mode but llama.cpp reports no GPU device`

```bash
llama-cli --list-devices
vulkaninfo --summary
```

确认 Vulkan/CUDA 后端和驱动；或先用 `--device cpu`。

### 翻译很慢

- 确认 `standard` 的 MinerU 已通过子进程运行；不要把 MinerU 和 llama-server 放同一进程。
- 4 GB 显存建议 `parallel: 1`。
- 检查是否误用了 CPU：`--dry-run` 会打印 `resolved_device`。

### 表格没有翻译

- `flash` 的 fenced code block 表格不翻译；改用 `--tier standard`。
- 确认 `standard` 输出包含 `<table>`；程序会先翻译 HTML 单元格，再转 Markdown 表格。
- 复杂 `rowspan`/`colspan` 会展开成重复表头/空单元格，版式不完美。

### 某些正文段落仍是英文

先区分预期保留和异常回退：

- 作者/单位、ORCID、DOI、图注、表注、表格内容和参考文献在双语模式下本来就保留原文。
- `OPEN`、`CrossMark` 等短标签也可能保留英文，这是正常的。
- 正文段落若仍是英文，查看日志中的 `translation dropped protected placeholders` 和 `segment fallback`。程序会先重试一次，再按受保护片段切分翻译普通文本。
- 最终仍失败时，`temp/state.json` 的 `translation_fallbacks.segment_untranslated` 会大于 0；保留 `temp/<stem>_en.md` 便于定位该段。

### Pandoc 报 `ctexhook.sty` 缺失

```bash
sudo pacman -S --needed texlive-langchinese
```

### 输出 PDF 版式不好看

v1 是重排 PDF，不保留原版式。可先用 `--tier standard` 改善表格/公式；自定义版式是后续功能。

### 双语模式报 `paracol.sty` 缺失

```bash
sudo pacman -S --needed texlive-latexextra
```

双语模式当前也只支持 `render.engine: xelatex`；不要改成 `tectonic`/`typst`。

## 13. 设计约束与已知限制

- 10 分钟是软目标，不是 SLA；复杂论文允许更久。
- v1 输出重排 PDF，不保留原 PDF 版式；双语对齐是段落级，不是逐句对齐。
- 翻译模型固定 Q4_K_M；1.25-bit/2-bit 版本需要特殊 STK kernel，质量也不稳，不建议使用。
- `flash` 的 fenced code block 表格不翻译；需要表格翻译时用 `standard`。
- `standard` 的 VLM 可能拆分多 panel 图，图注映射需要实测；必要时用 `basic` 对比。
- GPU 模式下 `parallel` 自动限制为 1；CUDA 后端尚未在开发机验证。
- 双语模式保留 HTML 表格的 `rowspan`/`colspan`；单栏模式会展开成近似网格。
- 长段落跨页时左右栏可能漂移；彻底同步需要句级对齐。
- 复杂内联标记/公式块丢失占位符时会先分段重译，仍失败才保留原文并记录 warning。
- Windows 双击打包尚未实现；当前 `ptp.exe` 是未来产物名。

## 14. 相关文档

- 功能与快速开始：[README.md](../README.md)
- 开发者细节、模块和调试：[dev.md](dev.md)
- 示例配置：[config.example.yaml](../config.example.yaml)
- MinerU：https://github.com/opendatalab/MinerU
- Hy-MT2-1.8B-GGUF：https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF
- Pandoc：https://github.com/jgm/pandoc

## 15. 许可证

PTP 自身使用 **GPL-2.0-or-later**；完整文本见 [LICENSE](../LICENSE)。

MinerU 是可选组件，使用 **MinerU Open Source License**（Apache-2.0 + 附加条款），不并入 PTP 的 GPL 代码。第三方组件和模型的许可证说明见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) 与 `LICENSES/`。

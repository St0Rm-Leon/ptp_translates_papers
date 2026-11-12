# PTP Translates Papers — Windows 便携版

这是 Windows x64 便携包。Core 已包含 PTP 运行时、Pandoc、TinyTeX、llama.cpp、字体和启动器；Hy-MT2 与 MinerU 可按需安装或直接解压完整组件。

发布组件：

- `PTP-Windows-x64-core.7z`：PTP 运行时、工具、TinyTeX、字体、启动器、安装脚本，以及一个**空的** MinerU Python 运行时。
- `PTP-Windows-x64-hy-model.7z`：Hy-MT2 翻译模型、模型说明和许可证。
- `PTP-Windows-x64-mineru.7z`：MinerU runtime + MinerU 模型、`data/mineru-home/config.yaml` 和许可证。

三种用法：

- **最简版**：只解压 `core`，运行 `install-all.cmd`（或分别运行 `install-hy.cmd`、`install-mineru.cmd`）。
- **模型版**：解压 `core` + `hy-model`，运行 `install-mineru.cmd`。
- **完整版**：解压 `core` + `hy-model` + `mineru`，离线可用，不需要运行安装脚本。

## 支持范围

- Windows 10 1903+ / Windows 11，x64。
- CPU 和 Vulkan GPU；Vulkan 覆盖 NVIDIA / AMD / Intel 显卡。
- 完整版离线可用；最简版/模型版首次安装需要网络，或使用脚本的 `-Wheelhouse` / `-ModelDir` 离线参数。
- Windows ARM64 暂不支持。

## 快速开始

1. 解压到可写目录，例如 `D:\PTP`。
   - 完整版：依次解压 `core`、`hy-model`、`mineru` 到同一目录。
   - 模型版：解压 `core`、`hy-model`，然后运行 `install-mineru.cmd`。
   - 最简版：只解压 `core`，然后运行 `install-all.cmd`。
2. 如果使用了安装脚本，按提示接受 MinerU 许可证；Hy-MT2 会显示 Apache-2.0 来源说明。
3. 检查环境：

   ```powershell
   .\ptp.exe --doctor
   ```

   所有项目显示 `OK` 后再开始使用。

4. 把英文论文 PDF 放到 `inputs\`，或直接用 `-i` 指定。
5. 运行：

   ```powershell
   .\ptp.exe -i inputs\paper.pdf -o outputs
   ```

安装脚本示例：

```powershell
# 最简版：安装 Hy-MT2 + MinerU runtime/models
.\install-all.cmd

# 只安装 Hy-MT2
.\install-hy.cmd

# 只安装 MinerU runtime/models；国内可使用 modelscope
.\install-mineru.cmd -Source modelscope

# 离线安装：先准备 wheelhouse 和模型目录
.\install-hy.cmd -ModelDir D:\offline\hy-model
.\install-mineru.cmd -Wheelhouse D:\offline\mineru-wheels -ModelDir D:\offline\mineru-models

# 只打印安装计划，不下载/安装
.\install-all.cmd -DryRun -AcceptLicense

# 重新下载/修复已安装组件
.\install-all.cmd -Force -AcceptLicense
```

输出：

```text
outputs\<stem>_zh\<stem>_zh.pdf
outputs\<stem>_zh\<stem>_bilingual.pdf   # --layout bilingual
```

也可以把 PDF 直接拖到 `ptp.exe` 上，等价于传入位置参数。

## 常用命令

```powershell
# 单栏中文
.\ptp.exe -i inputs\paper.pdf -o outputs

# 双语双栏
.\ptp.exe -i inputs\paper.pdf -o outputs --layout bilingual

# 强制 CPU
.\ptp.exe -i inputs\paper.pdf -o outputs --device cpu

# 强制 Vulkan GPU
.\ptp.exe -i inputs\paper.pdf -o outputs --device gpu --gpu-backend vulkan

# 表格/复杂版面推荐 standard
.\ptp.exe -i inputs\paper.pdf -o outputs --tier standard

# 断点续跑
.\ptp.exe -i inputs\paper.pdf -o outputs --resume

# 成功后删除 temp/
.\ptp.exe -i inputs\paper.pdf -o outputs --no-temp
```

## 配置

默认配置在同目录的 `config.yaml`。关键项：

```yaml
input: inputs
output: outputs

device: auto
gpu_backend: auto

mineru:
  python: runtime/mineru/python.exe
  model_source: local
  model_dir: mineru-models
  home: data/mineru-home

translation:
  model: models/Hy-MT2-1.8B-Q4_K_M.gguf
  server_bin: tools/llama/vulkan/llama-server.exe
  server_bin_cpu: tools/llama/cpu/llama-server.exe
  llama_cli: tools/llama/vulkan/llama-cli.exe
  llama_cli_cpu: tools/llama/cpu/llama-cli.exe

render:
  pandoc: tools/pandoc/pandoc.exe
  xelatex: tex/TinyTeX/bin/windows/xelatex.exe
  cjk_font_file: fonts/NotoSerifCJKsc-Regular.otf
  cjk_font_bold_file: fonts/NotoSerifCJKsc-Bold.otf
```

默认 `device: auto`：检测到 Vulkan GPU 时使用 GPU，否则 CPU。没有 GPU 时请用 `--device cpu`，不要使用 `--gpu-only`；CPU 模式会自动使用 `server_bin_cpu` / `llama_cli_cpu`。

## 数据与日志

- `inputs\`：建议放输入 PDF。
- `outputs\`：输出 PDF 和 `temp/` 过程文件。
- `data\logs\`：预留日志目录。
- `data\mineru-home\`：MinerU 配置和缓存；完整组件包含一份指向 `mineru-models` 的配置。
- `data\hf-cache\`：Hugging Face 缓存；脚本在线安装时使用。

每个输出目录的 `temp\state.json` 记录阶段、耗时、`translation_fallbacks` 和错误信息。失败时保留 `temp/`。

## 常见问题

### `ptp.exe --doctor` 报缺少项目

按提示检查：

- `xelatex`：确认 `tex\TinyTeX\bin\windows\xelatex.exe` 存在。
- `pandoc`：确认 `tools\pandoc\pandoc.exe` 存在。
- `llama-server` / `llama-cli`：确认 `tools\llama\vulkan\` 完整。
- `MinerU`：确认 `runtime\mineru\python.exe` 和 `mineru-models\` 存在。
- 模型：确认 `models\Hy-MT2-1.8B-Q4_K_M.gguf` 存在。

最简版/模型版没有内置这些组件时：

```powershell
.\install-all.cmd          # 最简版
.\install-mineru.cmd       # 模型版
```

离线安装：

```powershell
.\install-hy.cmd -ModelDir D:\offline\hy-model
.\install-mineru.cmd -Wheelhouse D:\offline\mineru-wheels -ModelDir D:\offline\mineru-models
```

### 安装 MinerU 时提示许可证

脚本会显示 MinerU Open Source License；交互式运行时输入 `Y`，无人值守时使用 `-AcceptLicense`。不接受许可证不会继续安装。

### 启动时提示缺少 DLL / VC++ Runtime

安装 Microsoft Visual C++ 2015–2022 Redistributable (x64)，然后重试。

### GPU 没有被使用

```powershell
.\tools\llama\vulkan\llama-cli.exe --list-devices
```

确认能看到 `Vulkan0` 等设备。NVIDIA/AMD 驱动需要支持 Vulkan；否则使用 `--device cpu`。

### 中文乱码或字体缺失

便携包已使用 `fonts\` 下的 Noto Serif CJK SC，并通过 `render.cjk_font_file` 加载，不依赖系统字体。若仍报字体错误，运行 `.\ptp.exe --doctor` 检查字体文件是否存在。

### 杀毒软件/SmartScreen 拦截

便携包包含较大的 Python/模型文件，未签名时可能触发警告。请从可信来源获取，并核对发布页提供的 SHA256。

### 路径含空格或中文

支持。建议把整个包放在普通可写目录，避免只读目录；并确保解压工具没有截断长文件名。

## 许可证

- PTP：GPL-2.0-or-later，见 `LICENSE`。
- 第三方组件和模型：见 `THIRD_PARTY_NOTICES.md` 和 `LICENSES/`。
- Hy-MT2：Apache-2.0；完整版内置模型，最简版/模型版由脚本从上游下载。
- MinerU：MinerU Open Source License；完整版内置 runtime/models，最简版/模型版由脚本安装，安装前需要显式接受许可证。PTP 通过独立的 `mineru-kit parse` CLI 进程调用 MinerU，不把 GPL 代码放入 MinerU 进程。
- 模型文件不适用 PTP 的 GPL；请保留上游模型卡和许可证。
- 如果用于商业分发或在线服务，请重新核查 MinerU 的附加条款。

## 从源码构建便携包

构建说明见仓库 `scripts/windows/README.md`。新版构建流程会先生成完整的 `build\windows-portable`，再拆分为：

- `build\components\core`
- `build\components\hy-model`
- `build\components\mineru`

然后用 `scripts/windows/package_components.ps1` 生成三个发布压缩包。

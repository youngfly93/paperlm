# paperlm

> **面向 LLM 的科研 PDF → Markdown 转换插件。**
> 用 Docling 做版面分析，用 PaddleOCR 处理扫描件，替换掉 MarkItDown 内置的 PDF 转换器。

**状态**：✅ v0.1.0 已发布至 PyPI — 发布检查、wheel 构建、
TestPyPI smoke、PyPI clean-install smoke 均已通过。

English version: [README.md](README.md)

## 为什么做这个

MarkItDown 的 PDF 转换路径主要针对发票、表单类文档；它的源码自己都承认 *"不是为 scientific documents 设计的"*。这个插件就是来补科研场景这个坑的。

### 对比案例 1 — arXiv 表格密集型论文

同一篇 [arXiv:2505.11545](https://arxiv.org/abs/2505.11545)（TARGET 表格检索 benchmark）。
MarkItDown 把**标题块误识别为 GFM 表格**，产出这样一坨：

```markdown
|     | TARGET: |     | Benchmarking |     |     | Table | Retrieval | for Generative |     | Tasks |
| --- | ------- | --- | ------------ | --- | --- | ----- | --------- | -------------- | --- | ----- |
XingyuJi*1,ParkerGlenn2,AdityaG.Parameswaran1,MadelonHulsebos3
|     |     |     |          | 1UCBerkeley |     |     | 2CapitalOne          | 3CWI |         |
| --- | --- | --- | -------- | ----------- | --- | --- | -------------------- | ---- | ------- |
5202 yaM 41  ]RI.sc[  1v54511.5052:viXra Thedatalandscapeisrichwithstructureddata,
```

开启 `paperlm` 后同一页渲染为：

```markdown
## TARGET: Benchmarking Table Retrieval for Generative Tasks

> * Correspondence to madelon.hulsebos@cwi.nl and jixy2012@berkeley.edu

Large Language Models (LLMs) have become an indispensable tool in the
knowledge worker's arsenal, providing a treasure trove of information at
one's fingertips. Retrieval-Augmented Generation (RAG) (Lewis et al., 2020)
further extends the capabilities of these LLMs by grounding generic dialog...

## 1 Introduction

The data landscape is rich with structured data, often of high value to
organizations...
```

虚假表格消失、arXiv 竖排水印（`5202 yaM 41 ]RI.sc[` 倒读 = `51 May 2025 [cs.IR]`）被剥离、段落重新流动、标题给到正确的 `##`。

### 对比案例 2 — 27 页 bioRxiv 论文

| | MarkItDown 原版 | paperlm |
|---|---|---|
| 开头 | `bioRxiv preprint doi:...` 水印文本 | `## A systematic benchmark...` (H2 标题) |
| 作者名 | `AliHamraoui1,2,AudreyOnfroy3,...` 全粘连 | `Ali Hamraoui 1,2 , Audrey Onfroy 3 , ...` |
| 特殊字符 | `(cid:0)` 乱码 | `/a0` 可读 |
| 段落结构 | 硬换行堆字 | 正确段落切分 |

复现两份对比：

```bash
python tests/fixtures/fetch.py          # 下载 corpus
python benchmarks/w4d4_showcase.py      # 输出写到 benchmarks/outputs/
diff benchmarks/outputs/sample_arxiv_table_heavy__{baseline,paperlm}.md
```

### 已知限制——双语文档

中文标题/摘要与英文**紧邻同页**的论文（如《生命科学》fixture），Docling 的版面模型有时会把中英文块交错重排。这个问题留到后续版本处理。

## 安装

```bash
# 从 PyPI
pip install paperlm[docling]            # 默认：Docling 版面解析

pip install paperlm[docling,ocr]        # + 本地 OCR，处理扫描件
pip install paperlm[all]                # 所有安全许可证 extra

# 源码开发
git clone https://github.com/youngfly93/paperlm
cd paperlm
pip install -e ".[docling,dev]"
```

## 使用

```python
from markitdown import MarkItDown

md = MarkItDown(enable_plugins=True)
result = md.convert("paper.pdf")

# MarkItDown 稳定 API
print(result.markdown)

# paperlm 扩展（非稳定 API —— 仅 Python 可见，CLI/MCP 不暴露）
print(result.engine_used)       # "docling" / "paddleocr" / "pdfminer" / "failed"
print(len(result.ir.blocks))    # 结构化 IR，供 RAG/Agent 消费
print(result.ir.warnings)       # 降级链的告警轨迹
```

### 强制指定引擎

```python
md = MarkItDown(enable_plugins=True, paperlm_engine="ocr")        # 强制 OCR
md = MarkItDown(enable_plugins=True, paperlm_engine="docling")    # 跳过扫描检测
md = MarkItDown(enable_plugins=True, paperlm_engine="fallback")   # 只用 pdfminer
md = MarkItDown(enable_plugins=True, paperlm_enable_ocr=False)    # auto 模式下关 OCR
```

### CLI

```bash
markitdown --use-plugins paper.pdf -o paper.md
markitdown --list-plugins        # 应显示 "paperlm"
```

## 路由策略

```
输入 PDF
  │
  ▼
EngineRouter (auto 模式)
  │
  ├─ 抽样检测文本层 (scanned_detector.py)
  │
  ├─ 扫描件（无文本）  →  OCRAdapter（PaddleOCR, Apache-2.0）
  │                       ↓ 空/失败
  │                       DoclingAdapter（MIT）
  │                       ↓ 空/失败
  │                       FallbackAdapter（pdfminer）
  │
  └─ 有文本层       →  DoclingAdapter
                        ↓ 空/失败
                        OCRAdapter（若已安装）
                        ↓ 空/失败
                        FallbackAdapter（pdfminer —— 作为核心依赖随包安装）
  │
  ▼
IR（Block / BlockType / BBox / reading_order）
  │
  ▼
MarkdownSerializer → result.markdown
```

**降级保证**：任何能被解析的 PDF 都一定返回结果——因为 pdfminer.six 是核心依赖、永远排在最后。即便 pdfminer 本身缺失或 PDF 坏了，返回的是空 Markdown + `result.ir.warnings`，**永远不抛异常**。

## 可选引擎的许可证对照

| Extra | 引擎 | 许可证 | 能否商用 |
|---|---|---|---|
| *（核心）* | pdfminer.six / pdfplumber | MIT / MIT | ✅ 安全 |
| `[docling]` **（默认推荐）** | Docling 2.90 | **MIT** | ✅ 安全 |
| `[ocr]` | PaddleOCR + paddlepaddle | Apache-2.0 | ✅ 安全 |
| `[formula]` *（Week 3 预留）* | pix2tex | MIT | ✅ 安全 |
| `[marker]` *（可选）* | Marker | GPL-3 + OpenRAIL-M | ⚠️ copyleft；营收 >$2M 需向 Datalab 申请商业授权 |
| `[mineru]` *（可选）* | MinerU | AGPL | ⚠️ 强 copyleft；网络服务分发触发 |

主包 **Apache-2.0**，默认安装不会引入 GPL/AGPL 传染性依赖。你必须显式 `[marker]` / `[mineru]` 才会被拉进来。

## 开发

```bash
uv venv --python 3.12 ~/.venvs/paperlm
source ~/.venvs/paperlm/bin/activate
export UV_LINK_MODE=copy          # 源码在 exFAT 盘时必需
uv pip install -e ".[docling,ocr,dev]"

# 快速测试（不加载 ML 模型）
pytest tests/test_ir.py tests/test_engine_base.py tests/test_serializer.py \
       tests/test_plugin_registration.py tests/test_fallback_adapter.py \
       tests/test_scanned_detector.py tests/test_router.py

# 慢测试（首次运行会下载 Docling / PaddleOCR 模型）
pytest tests/test_docling_adapter.py
pytest tests/test_ocr_adapter.py
pytest tests/test_pdf_converter_e2e.py
```

**内存提示**：Docling + PaddleOCR 不要在同一个 pytest 进程里跑，两个模型同时驻留 ~2-3GB。分开跑。

### Reviewer 如何自证集成链路

快速测试套件**刻意**把所有需要 ML 模型或缺失核心依赖的测试跳过。**这是预期行为**，被跳过的测试没有实际跑过，不能只凭 0 failed 就断言它们工作。

三种从低到高的自证方式：

1. **信任预录证据**——[`benchmarks/phase4_integration.md`](benchmarks/phase4_integration.md) 记录了 macOS-CPU 上 8 份 fixture × 独立子进程的完整 sweep。8/8 全部产出非空 IR、0 error、所有 peak RSS ≤ 4 GB。

2. **触发 GitHub Actions 的 integration job**——任意 checkout：
   ```bash
   gh workflow run test.yml --field ref=<branch>
   ```
   `integration` job 会在 Linux runner 下载 fixtures、装 `.[docling,ocr]`、跑 Docling/OCR/E2E 测试。

3. **本地复现**：
   ```bash
   python tests/fixtures/fetch.py                # 下载 corpus
   pip install -e '.[docling,ocr,dev]'
   make test-all                                 # 约 3-4 分钟
   # 或跑完整 sweep，per-fixture peak RSS：
   python benchmarks/w4d5_integration_sweep.py
   ```

### 测试 fixture（不入 git，本地重建）

```bash
# 英文双栏 bioRxiv 论文（27p）
curl -sL -o tests/fixtures/sample_en_two_col.pdf \
  https://www.biorxiv.org/content/10.1101/2025.07.21.665920v1.full.pdf

# 中文生信综述（10p）
curl -sL -o tests/fixtures/sample_zh_mixed.pdf \
  https://lifescience.sinh.ac.cn/webadmin/upload/20241121140516_3869_1634.pdf

# 合成扫描件（无文本层）—— 从中文 PDF 栅格化得到
python tests/fixtures/_make_scanned.py
```

## 进度路线图

- ✅ Week 1 —— 骨架 + Docling 接入 + IR + Markdown 序列化器
- ✅ Week 2 —— pdfminer 兜底 + 路由器 + 扫描检测 + PaddleOCR
- 🚧 Week 3 —— 公式 inline/block 识别、表格 GFM 精修、caption 配对、阅读顺序修复
- 📋 Week 4 —— 完整测试覆盖、CI、基准文档
- 📋 Week 5 —— PyPI 发布 + 发布博客

完整规格见 [`../PRD.md`](../PRD.md)。

## 许可证

Apache-2.0。见 [LICENSE](LICENSE)。

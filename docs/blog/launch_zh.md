# paperlm：给 MarkItDown 补一个能读科研 PDF 的插件

_发布日期：<发帖时填写>_

## 一句话 + 一张图的问题

微软的 [MarkItDown](https://github.com/microsoft/markitdown) 本意很好——任何文档扔进去都出 Markdown。发票、表单、简单报告都转得挺顺。但**科研论文 PDF 上翻车**。它自己源码里都写了：

> *"This function is designed for structured tabular data (like invoices),
> **not for multi-column text layouts in scientific documents**"*
> — `markitdown/packages/markitdown/src/markitdown/converters/_pdf_converter.py:403`

拿 [TARGET benchmark 论文 (arXiv:2505.11545)](https://arxiv.org/abs/2505.11545) 跑一下：

```markdown
|     | TARGET: |     | Benchmarking |     |     | Table | Retrieval | for Generative |     | Tasks |
| --- | ------- | --- | ------------ | --- | --- | ----- | --------- | -------------- | --- | ----- |
XingyuJi*1,ParkerGlenn2,AdityaG.Parameswaran1,MadelonHulsebos3
5202 yaM 41  ]RI.sc[  1v54511.5052:viXra Thedatalandscapeisrichwithstructureddata,
```

标题被当作了 GFM 表格、作者名全粘在一起、arXiv 竖排水印（倒读 `51 May 2025 [cs.IR]`）当作正文。喂 LLM 的 RAG pipeline 遇到这种输入，下游全废。

## paperlm 干了什么

`paperlm` 是个**插件**，替换 MarkItDown 内置的 PDF 转换器：

1. **[Docling 2.90](https://github.com/docling-project/docling)** (MIT) 处理有文本层的 PDF —— 版面分析、表格抽取、阅读顺序修复
2. **[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) PP-OCRv5 mobile** (Apache-2.0) 处理扫描件 —— 中文识别强
3. **pdfminer.six** 作为永远可用的兜底

API 零改动：

```python
from markitdown import MarkItDown
md = MarkItDown(enable_plugins=True)
print(md.convert("paper.pdf").markdown)
```

同一页现在变成：

```markdown
## TARGET: Benchmarking Table Retrieval for Generative Tasks

> * Correspondence to madelon.hulsebos@cwi.nl and jixy2012@berkeley.edu

Large Language Models (LLMs) have become an indispensable tool...

## 1 Introduction

The data landscape is rich with structured data...
```

水印剥离、标题给正确的 `##`、段落重新流动。

## 为什么是插件，不是独立项目

MarkItDown 原生就有插件机制（通过 `priority=-1.0` 可以顶替内置 converter）。`markitdown-ocr` 验证过这条路可行，paperlm 只是把路走远一点。

好处：**零迁移成本**。已经在用 MarkItDown？`pip install paperlm[docling]` + 一个 flag（`enable_plugins=True`）就完事。

## 内存预算

Docling + PaddleOCR 听起来 CPU 吃不消？配对之后不会：

| 测试用例 | 引擎 | 耗时 | 峰值 RSS |
|---|---|---|---|
| 10 页中文论文 | Docling | 11 s | 1.4 GB |
| 27 页 bioRxiv | Docling | 92 s | 2.3 GB |
| 1 页扫描件 | PaddleOCR | 16 s | 2.7 GB |

8 份 fixture 都 **≤ 4 GB**。[RSS 探针报告](../../benchmarks/phase4_rss_probe.md) 记录了调优过程——关键 insight：**PP-OCRv5 mobile 在中文生信论文上与 server 模型一样准，内存少 74%**。

## 许可证策略

默认只安装 MIT 和 Apache-2.0 代码。GPL-3（Marker）和 AGPL（MinerU）都是 opt-in extra，有明确警告标注。**商用栈可直接引入**，不会被 copyleft 污染。

## 还没做的（v0.2 roadmap）

- **中英并排的双语文档**：Docling 版面模型偶尔会把中英文块重排——单语论文没这问题
- **公式 LaTeX 识别**：opt-in（`paperlm_enable_formula=True`），加载 500 MB VLM
- **图片导出到磁盘**：目前渲染为 `![](figure)` 占位，下一版支持真导出

## 试试看

- GitHub: `https://github.com/youngfly93/paperlm`
- PyPI: `pip install paperlm[docling]`
- CLI: `markitdown --use-plugins paper.pdf -o paper.md`

欢迎 bug report 和 PR。

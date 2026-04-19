# Day 2 Baseline: MarkItDown vs Docling

_Week 1 Day 2 — Eyeball comparison on 3 representative fixtures._

All runs CPU-only. Times include engine init + conversion.

## Executive Summary (key findings)

| Fixture | Baseline (markitdown) | Docling 2.90 | Winner |
|---|---|---|---|
| **英文双栏论文**（27p） | 11.8s, 结构丢失、作者名粘连、PDF 水印当正文 | 85.4s, 正确 heading、作者名空格分隔、水印剥离 | **Docling (7× 慢但质量显著好)** |
| **中文双栏论文**（10p） | 0.3s, 无 heading 层级 | 5.2s, `##` heading 识别 + 段落切分 | **Docling** |
| **扫描件 PDF**（5p） | **0 chars（完全失败）** | 2.8KB, 英文 OCR 正常 + 中文 OCR 乱码 | **Docling（但中文需 PaddleOCR 补）** |

### 关键洞察

1. **Docling 对英文学术论文质量碾压 markitdown**：heading 正确、作者分词、水印剥离——这验证了 Docling 是默认引擎的正确选择
2. **Docling 自带 OCR 处理扫描件**：markitdown 0 字符完全失败，Docling 能抢救出 2.8KB 文本（内置 EasyOCR）
3. **中文扫描件是 Docling 的软肋**：英文字段识别完美（`Bioinformatics and biomanufacturing...`），但中文被识别成西里尔字母乱码（`ТРТТНТРТ`）→ **验证 Week 2 必须接 PaddleOCR 作中文扫描专路**
4. **Docling 速度代价**：英文 27 页 85 秒，约 3.2 秒/页 CPU；PRD 目标 20 页 ≤90 秒 → **需要 ≤4.5 秒/页，实测 3.2 秒/页 ✅ 达标**
5. **中文非扫描件 5.2 秒 10 页**：约 0.5 秒/页，速度完全够用

### Week 2 路由策略（根据 Day 2 结果调整）

```
输入 PDF
├─ 无文本层？（markitdown 抽出 < 50 字符）
│   ├─ 全页是中文？（用 langdetect 快速判断）→ PaddleOCR
│   └─ 其他 → Docling（内置 OCR 够用）
└─ 有文本层 → Docling
```



## sample_en_two_col.pdf

**EN double-column, bioRxiv 2025 RNA-seq benchmark (27 pages)**

| Engine | Time (s) | Output chars | First 200 chars |
|---|---|---|---|
| MarkItDown (baseline) | 11.8 | 223864 | `bioRxiv preprint doi: https://doi.org/10.1101/2025.07.21.665920; this version posted July 25, 2025. The copyright holder for this preprint (which was not certified by peer review) is the author/funder...` |
| Docling 2.90 | 85.4 | 122153 | `## A systematic benchmark of bioinformatics methods for single-cell and spatial RNA-seq Nanopore long-read data  Ali Hamraoui 1,2 , Audrey Onfroy 3 , Catherine Senamaud-Beaufort 1 , Fanny Coulpier 3 ,...` |

<details><summary>MarkItDown (baseline) — first 800 chars</summary>

```
bioRxiv preprint doi: https://doi.org/10.1101/2025.07.21.665920; this version posted July 25, 2025. The copyright holder for this preprint (which
was not certified by peer review) is the author/funder, who has granted bioRxiv a license to display the preprint in perpetuity. It is made
available under aCC-BY 4.0 International license.
A systematic benchmark of bioinformatics
methods for single-cell and spatial RNA-seq
Nanopore long-read data
AliHamraoui1,2,AudreyOnfroy3,CatherineSenamaud-Beaufort1,FannyCoulpier3,SophieLemoine1,LaurentJourdren1,and
MorganeThomas-Chollier1,2,(cid:0)
1GenomiqueENS,InstitutdeBiologiedel’ENS(IBENS),Départementdebiologie,Écolenormalesupérieure,CNRS,INSERM,UniversitéPSL,75005Paris,France
2GroupBacterialinfection,response&dynamics,Institutdebiologiedel’ENS(IBENS),É
```

</details>

<details><summary>Docling 2.90 — first 800 chars</summary>

```
## A systematic benchmark of bioinformatics methods for single-cell and spatial RNA-seq Nanopore long-read data

Ali Hamraoui 1,2 , Audrey Onfroy 3 , Catherine Senamaud-Beaufort 1 , Fanny Coulpier 3 , Sophie Lemoine 1 , Laurent Jourdren 1 , and Morgane Thomas-Chollier 1,2, /a0

1 GenomiqueENS, Institut de Biologie de l'ENS (IBENS), Département de biologie, École normale supérieure, CNRS, INSERM, Université PSL, 75005 Paris, France 2 Group Bacterial infection, response &amp; dynamics, Institut de biologie de l'ENS (IBENS), École normale supérieure, CNRS, INSERM, Université PSL, 75005 Paris, France 3 Team Neurofibromatosis and Lymphoma oncogenesis, Institut Mondor de Recherche Biomédicale, UPEC, INSERM, 94000 Créteil, France

Alternative splicing plays a crucial role in transcriptomic comple
```

</details>

---

## sample_zh_mixed.pdf

**ZH mixed, 《生命科学》2024 bioinformatics review (10 pages)**

| Engine | Time (s) | Output chars | First 200 chars |
|---|---|---|---|
| MarkItDown (baseline) | 0.3 | 22915 | `第36卷 第11期 生命科学 Vol. 36, No. 11 2024年11月 Chinese Bulletin of Life Sciences Nov., 2024 DOI: 10.13376/j.cbls/20240163 文章编号：1004-0374(2024)11-1339-10 生物信息学与生物制造：论生物大数据及其 数据挖掘在生物制造中的重要性 李玉雪，王 波，宁 康* (华中科技大...` |
| Docling 2.90 | 5.2 | 20579 | `文章编号  ： 1004-0374(2024)11-1339-10  DOI: 10.13376/j.cbls/20240163  ## 生物信息学与生物制造 ： 论生物大数据及其 数据挖掘在生物制造中的重要性  李玉雪 ， 王 波 ， 宁 康 *  ( 华中科技大学生命科学与技术学院，武汉  430074)  摘　要 ：生物信息学在生物制造中发挥着举足轻重的作用，成为推动生物技术发展的关键引擎。...` |

<details><summary>MarkItDown (baseline) — first 800 chars</summary>

```
第36卷 第11期 生命科学 Vol. 36, No. 11
2024年11月 Chinese Bulletin of Life Sciences Nov., 2024
DOI: 10.13376/j.cbls/20240163
文章编号：1004-0374(2024)11-1339-10
生物信息学与生物制造：论生物大数据及其
数据挖掘在生物制造中的重要性
李玉雪，王 波，宁 康*
(华中科技大学生命科学与技术学院，武汉 430074)
摘 要：生物信息学在生物制造中发挥着举足轻重的作用，成为推动生物技术发展的关键引擎。该学科通
过分析海量的生物数据，提供深刻的生物系统解析和精准的数据支撑。在生物制造过程中，这些宝贵的数
据和分析成果被转化为实际应用，推动生物产品的开发和创新。特别是在生物大数据和生物数据挖掘领域，
技术的迅速发展和数据资源的不断增长为生物制造提供了巨大的推动力。通过对生物数据的深入挖掘和分
析，能够更加全面地理解生物系统的复杂性，进而设计出更加高效、精准且可持续的生物制造过程。这不
仅有助于提升生物制造的效率和质量，还能促进新质生产力的形成，为生物经济的发展注入新的活力。展
望未来，生物信息学在生物制造领域的应用将继续拓展和深化，为解决全球性的健康、能源和环境问题提
供有力的科学支持和技术手段。生物信息学与生物制造的紧密结合，将为生物技术产业的可持续发展注入
新的动力。
关键词：生物信息学；生物制造：生物大数据挖掘
中图分类号：Q81；Q93；TP31 文献标志码：A
Bioinformatics and biomanufacturing: the importance of big biodata and
its data mining in biomanufacturing
LI Yu-Xue, WANG Bo, NING Kang*
(Colleg
```

</details>

<details><summary>Docling 2.90 — first 800 chars</summary>

```
文章编号

： 1004-0374(2024)11-1339-10

DOI: 10.13376/j.cbls/20240163

## 生物信息学与生物制造 ： 论生物大数据及其 数据挖掘在生物制造中的重要性

李玉雪 ， 王 波 ， 宁 康 *

( 华中科技大学生命科学与技术学院，武汉

430074)

摘　要 ：生物信息学在生物制造中发挥着举足轻重的作用，成为推动生物技术发展的关键引擎。该学科通 过分析海量的生物数据，提供深刻的生物系统解析和精准的数据支撑。在生物制造过程中，这些宝贵的数 据和分析成果被转化为实际应用，推动生物产品的开发和创新。特别是在生物大数据和生物数据挖掘领域， 技术的迅速发展和数据资源的不断增长为生物制造提供了巨大的推动力。通过对生物数据的深入挖掘和分 析，能够更加全面地理解生物系统的复杂性，进而设计出更加高效、精准且可持续的生物制造过程。这不 仅有助于提升生物制造的效率和质量，还能促进新质生产力的形成，为生物经济的发展注入新的活力。展 望未来，生物信息学在生物制造领域的应用将继续拓展和深化，为解决全球性的健康、能源和环境问题提 供有力的科学支持和技术手段。生物信息学与生物制造的紧密结合，将为生物技术产业的可持续发展注入 新的动力。

关键词 ：生物信息学；生物制造：生物大数据挖掘

中图分类号

： Q81 ； Q93 ； TP31 文献标志码 ： A

## Bioinformatics and biomanufacturing: the importance of big biodata and its data mining in b iomanufacturing

LI Yu-Xue, WANG Bo, NING Kang *

(College of Life Science and Technology, Huazhong U
```

</details>

---

## sample_scanned.pdf

**Scanned, rasterized ZH paper, 5 pages, NO text layer**

| Engine | Time (s) | Output chars | First 200 chars |
|---|---|---|---|
| MarkItDown (baseline) | 0.0 | 0 | `...` |
| Docling 2.90 | 5.3 | 2844 | `DOI: 10.13376/j.cbls/20240163  XHS: 1004-0374(2024)11-1339-10  1Х 430074)  ТРТТНТРТ НОСТТФ ТІНТТТТТСТНТНТК7Ф#ТЕННН. КНОТИЛЕДСАДАЛА ПРЕАЛЕТОЕК ВЕРЕВКОРАЛИВ А  *Ні: 081 : 093 : ТР31 *###79: A  ## Bioinf...` |

<details><summary>MarkItDown (baseline) — first 800 chars</summary>

```

```

</details>

<details><summary>Docling 2.90 — first 800 chars</summary>

```
DOI: 10.13376/j.cbls/20240163

XHS: 1004-0374(2024)11-1339-10

1Х 430074)

ТРТТНТРТ НОСТТФ ТІНТТТТТСТНТНТК7Ф#ТЕННН. КНОТИЛЕДСАДАЛА ПРЕАЛЕТОЕК ВЕРЕВКОРАЛИВ А

*Ні: 081 : 093 : ТР31 *###79: A

## Bioinformatics and biomanufacturing: the importance of big biodata and its data mining in biomanufacturing

LI Yu-Xue, WANG Bo, NING Kang*

(College of Life Science and Technology, Huazhong University of Science and Technology, Wuhan 430074, China)

Abstract: Bioinformatics plays a pivotal role in biomanufacturing and has become a key engine for the development of biotechnology. This discipline provides profound biological system analysis and accurate data support by analyzing massive amounts of biological data. In the process of biomanufacturing, these valuable data and analysis results are transfo
```

</details>

---

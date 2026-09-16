# 珀莱雅消费者洞察 Pipeline — Codex 最终可执行方案

> **版本**
> : v1.0-final
> **市场**
> : 中国市场 |
> **主语言**
> : 中文 (zh-CN)
> **项目阶段**
> : 求职 Demo / PoC
> **目标规模**
> : 约 1000 条（600 Business Core + 400 Benchmark Pipeline Test）
> **执行方式**
> : Codex 按本方案顺序部署，人工仅负责采集录入和冲突审核



***

## 0. 五层架构总览



```
┌─────────────────────────────────────────────────────────────────┐

│                    消费者洞察五层 Pipeline                        │

├─────────────────────────────────────────────────────────────────┤

│                                                                 │

│  L1 Collection Layer    原始数据采集层                            │

│  ├─ Tmall 公开评价 (≈450)  manual\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_public                        │

│  ├─ Xiaohongshu UGC (≈150) manual\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_public                       │

│  └─ Benchmark (≈400)     public\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_dataset                        │

│         │  raw/ 不可覆盖，原文保真                                 │

│         ▼                                                      │

│  L2 Cleaning Layer      清洗规则层                              │

│  ├─ Rule Engine (确定性代码，无LLM)                              │

│  ├─ Semantic Cleaner Agent (KEEP/FILTER)                       │

│  └─ Risk Reviewer Agent (误删风险复核)                           │

│         │  clean\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_dataset.csv / filtered / conflict             │

│         ▼                                                      │

│  L3 Feature Processing  特征加工层                              │

│  ├─ Tagging Agent (Schema v1 多标签抽取)                        │

│  ├─ Schema Validator (代码校验)                                 │

│  ├─ Audit Agent (证据/分类/漏标检查)                            │

│  └─ Topic Discovery (Embedding + KMeans，仅发现Schema盲区)       │

│         │  feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_dataset\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_v1.csv (Long Format)                │

│         ▼                                                      │

│  L4 Decision Output     决策输出层                              │

│  ├─ Eligible Sample Filter (business\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_core 隔离)                │

│  ├─ Metric Engine (unique record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id 统计)                      │

│  ├─ Trend Engine (2个月窗口，N≥30，连续3窗口)                   │

│  ├─ Evidence Binding (3-5条/结论)                              │

│  └─ Snapshot Freeze (版本冻结)                                  │

│         │  优点/痛点排行、产品对比、场景切片、Opportunity List    │

│         ▼                                                      │

│  L5 Data Presentation   数据呈现层                              │

│  ├─ Consumer Insight Dashboard (5区域)                         │

│  ├─ Model Ops Dashboard (QA/指标/版本)                         │

│  ├─ Insight Recommendation Agent (事实→模式→假设→建议)          │

│  └─ Feishu Webhook Bot (Alert + Weekly + NewTopic)            │

│                                                                 │

└─────────────────────────────────────────────────────────────────┘
```

### 跨层核心原则



| 原则                | 说明                                                        |
| ----------------- | --------------------------------------------------------- |
| `record_id` 全流程不变 | Raw → Clean → Feature → Decision → Presentation 永久使用同一 ID |
| Raw 不可覆盖          | 所有加工生成新文件，`data/raw/` 只读                                  |
| 数据角色严格隔离          | `business_core` ≠ `pipeline_test`，Benchmark 不进入业务结论       |
| 采样层严格隔离           | `natural_base` ≠ `scenario_enrichment`，Enrichment 不参与比例统计 |
| 确定性优先             | 技术清洗、统计、排行、趋势由代码计算；LLM 只做语义抽取和判断                          |
| 证据可追溯             | 每个结论可通过 `decision_id → feature_id → record_id → Raw` 回溯   |
| 版本可复现             | Schema / Clean / Prompt / Model / Metric 版本全程记录           |



***

## 1. 项目目录结构

Codex 首次执行时创建以下完整目录：



```
proya-consumer-insight/

├── README.md

├── requirements.txt

├── config/

│   ├── config.yaml              # 全局配置（路径、阈值、API、版本号）

│   ├── schema\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_v1.json           # 特征标签体系（唯一执行依据）

│   └── feishu\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_webhook.yaml      # 飞书推送配置（凭证走环境变量）

│

├── data/

│   ├── raw/                     # 【只读】原始数据，不可覆盖

│   │   ├── tmall\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_raw.csv

│   │   ├── xiaohongshu\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_raw.csv

│   │   └── benchmark\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_reviews\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_raw.csv

│   ├── reference/               # 参考数据，不进入Agent输入

│   │   ├── benchmark\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_gold\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_labels.csv

│   │   └── project\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_gold\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_v1.csv

│   ├── cleaned/

│   │   ├── clean\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_dataset.csv

│   │   ├── filtered\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_records.csv

│   │   └── conflict\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_queue.csv

│   ├── features/

│   │   ├── feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_dataset\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_v1.csv

│   │   ├── feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_review\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_queue.csv

│   │   └── topic\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_candidates.csv

│   ├── decisions/

│   │   ├── decision\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_metrics.csv

│   │   ├── opportunity\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_candidates.csv

│   │   ├── evidence\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_bindings.csv

│   │   └── snapshots/

│   │       └── snapshot\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_YYYYMMDD/

│   └── presentation/

│       ├── dashboard\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_data.json

│       └── alerts/

│

├── src/

│   ├── collection/

│   │   ├── schema.py            # Raw Schema 定义与校验

│   │   ├── id\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_generator.py      # record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id 生成

│   │   ├── qa\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_checker.py        # Collection QA Report

│   │   └── exporter.py          # Excel → CSV 导出

│   ├── cleaning/

│   │   ├── rule\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_engine.py       # 确定性技术清洗（无LLM）

│   │   ├── cleaner\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent.py     # Semantic Cleaner Agent

│   │   ├── reviewer\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent.py    # Risk Reviewer Agent

│   │   ├── merge\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_results.py     # Cleaner+Reviewer 结果合并

│   │   └── qa\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_report.py         # Cleaning QA Report

│   ├── features/

│   │   ├── tagging\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent.py     # Tagging Agent

│   │   ├── schema\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_validator.py  # Schema 代码校验

│   │   ├── audit\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent.py       # Audit Agent

│   │   ├── topic\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_discovery.py   # Embedding + KMeans

│   │   ├── gold\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_builder.py      # Project Gold 抽样与冻结

│   │   └── evaluator.py         # Precision/Recall/F1 评测

│   ├── decisions/

│   │   ├── sample\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_filter.py     # Eligible Sample Filter

│   │   ├── metric\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_engine.py     # mention\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_count/rate 计算

│   │   ├── trend\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_engine.py      # 2个月窗口趋势

│   │   ├── evidence\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_binder.py   # 证据绑定

│   │   ├── opportunity.py       # Opportunity Candidate List

│   │   ├── consistency.py       # 跨层一致性校验

│   │   └── snapshot.py          # Snapshot 冻结

│   ├── presentation/

│   │   ├── dashboard\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_builder.py # Dashboard 数据组装

│   │   ├── insight\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent.py     # Insight Recommendation Agent

│   │   ├── alert\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_engine.py      # 告警触发规则

│   │   └── feishu\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_bot.py        # Feishu Webhook 发送

│   └── common/

│       ├── llm\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_client.py        # LLM 调用封装（Batch、重试、校验）

│       ├── id\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_utils.py          # feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id / decision\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id / alert\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id 生成

│       ├── version.py           # 版本元数据管理

│       └── io\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_utils.py          # CSV 读写、缺失值规范

│

├── scripts/

│   ├── 01\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_collection.py     # L1 入口

│   ├── 02\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_cleaning.py       # L2 入口

│   ├── 03\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_features.py       # L3 入口

│   ├── 04\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_decisions.py      # L4 入口

│   └── 05\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_presentation.py   # L5 入口

│

├── templates/

│   └── proya\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_collection\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_raw.xlsx  # 人工采集模板（4个Sheet）

│

└── reports/

\\\\\\\\\\\\\\\&#x20;   ├── collection\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_qa\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_report.json

\\\\\\\\\\\\\\\&#x20;   ├── cleaning\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_qa\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_report.json

\\\\\\\\\\\\\\\&#x20;   ├── feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_evaluation.json

\\\\\\\\\\\\\\\&#x20;   ├── feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_error\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_analysis.csv

\\\\\\\\\\\\\\\&#x20;   └── decision\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_consistency\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_report.json
```



***

## 2. 技术栈与依赖

### 核心依赖 (`requirements.txt`)



```
\\\\\\\\\\\\\\\\# 数据处理

pandas>=2.0

numpy>=1.24

openpyxl>=3.1          # Excel 读写

\\\\\\\\\\\\\\\\# LLM

openai>=1.0            # 或兼容 OpenAI API 的客户端

tiktoken>=0.5          # Token 计数，动态调整 Batch Size

\\\\\\\\\\\\\\\\# Embedding & 聚类

sentence-transformers>=2.2   # 中文 Embedding（如 paraphrase-multilingual-MiniLM）

scikit-learn>=1.3            # KMeans

\\\\\\\\\\\\\\\\# 配置与工具

pyyaml>=6.0

python-dotenv>=1.0

\\\\\\\\\\\\\\\\# 飞书

requests>=2.31

\\\\\\\\\\\\\\\\# 可视化（Dashboard 数据层，前端另行）

\\\\\\\\\\\\\\\\# Dashboard 建议用 Streamlit 或纯 HTML+ECharts，本方案输出 JSON 数据
```

### LLM 调用规范 (`src/common/llm_client.py`)



```
\\\\\\\\\\\\\\\\- 统一封装：batch\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_call(messages\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_list, max\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_retries=3)

\\\\\\\\\\\\\\\\- Batch Size 默认 20-30 条，长文本自动降低

\\\\\\\\\\\\\\\\- 输出必须为 JSON，代码层解析校验

\\\\\\\\\\\\\\\\- 校验失败：Retry → 仍失败 → AGENT\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_ERROR 队列，禁止静默丢数据

\\\\\\\\\\\\\\\\- 每次调用记录：model\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_identifier, prompt\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_version, run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id, token\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_usage
```



***

## 3. 全局配置 (`config/config.yaml`)



```
project:

\\\\\\\\\\\\\\\&#x20; name: "proya-consumer-insight"

\\\\\\\\\\\\\\\&#x20; market: "CN"

\\\\\\\\\\\\\\\&#x20; language: "zh-CN"

\\\\\\\\\\\\\\\&#x20; stage: "PoC"

versions:

\\\\\\\\\\\\\\\&#x20; schema\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_version: "v1"

\\\\\\\\\\\\\\\&#x20; clean\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_version: "v1"

\\\\\\\\\\\\\\\&#x20; tagging\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_prompt\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_version: "v1"

\\\\\\\\\\\\\\\&#x20; model\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_identifier: "待填写"      # 如 gpt-4o / doubao-pro

\\\\\\\\\\\\\\\&#x20; metric\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_version: "v1"

data:

\\\\\\\\\\\\\\\&#x20; target\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_total: 1000

\\\\\\\\\\\\\\\&#x20; tolerance\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_pct: 5

\\\\\\\\\\\\\\\&#x20; tmall\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_target: 450

\\\\\\\\\\\\\\\&#x20; xiaohongshu\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_target: 150

\\\\\\\\\\\\\\\&#x20; benchmark\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_target: 400

products:

\\\\\\\\\\\\\\\&#x20; - id: "P001"

\\\\\\\\\\\\\\\&#x20;   name: "珀莱雅红宝石面霜"

\\\\\\\\\\\\\\\&#x20; - id: "P002"

\\\\\\\\\\\\\\\&#x20;   name: "珀莱雅双抗精华"

\\\\\\\\\\\\\\\&#x20; - id: "P003"

\\\\\\\\\\\\\\\&#x20;   name: "珀莱雅源力面霜"

cleaning:

\\\\\\\\\\\\\\\&#x20; batch\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_size: 25

\\\\\\\\\\\\\\\&#x20; human\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_review\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_sample\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_pct: 5

features:

\\\\\\\\\\\\\\\&#x20; batch\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_size: 25

\\\\\\\\\\\\\\\&#x20; gold\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_total: 100

\\\\\\\\\\\\\\\&#x20; gold\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_stratified: 80

\\\\\\\\\\\\\\\&#x20; gold\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_hard\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_cases: 20

\\\\\\\\\\\\\\\&#x20; target\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_f1: 0.8                  # 参考目标，非硬验收线

decisions:

\\\\\\\\\\\\\\\&#x20; low\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_support\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_threshold: 3        # mention\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_count < 3 → LOW\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_SUPPORT

\\\\\\\\\\\\\\\&#x20; trend\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_window\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_months: 2

\\\\\\\\\\\\\\\&#x20; trend\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_min\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_window\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_n: 30

\\\\\\\\\\\\\\\&#x20; trend\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_min\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_topic\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_mentions: 5

\\\\\\\\\\\\\\\&#x20; trend\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_min\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_consecutive\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_windows: 3

\\\\\\\\\\\\\\\&#x20; evidence\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_per\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_conclusion: \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\[3, 5] # 每条结论绑定3-5条证据

presentation:

\\\\\\\\\\\\\\\&#x20; dashboard\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_name: "Consumer Insight Dashboard"

\\\\\\\\\\\\\\\&#x20; feishu\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_alert\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_types: \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\["Alert", "Weekly Digest", "New Topic Alert"]

paths:

\\\\\\\\\\\\\\\&#x20; raw\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_dir: "data/raw"

\\\\\\\\\\\\\\\&#x20; reference\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_dir: "data/reference"

\\\\\\\\\\\\\\\&#x20; cleaned\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_dir: "data/cleaned"

\\\\\\\\\\\\\\\&#x20; features\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_dir: "data/features"

\\\\\\\\\\\\\\\&#x20; decisions\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_dir: "data/decisions"

\\\\\\\\\\\\\\\&#x20; presentation\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_dir: "data/presentation"

\\\\\\\\\\\\\\\&#x20; reports\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_dir: "reports"
```



***

## 4. 第一层：原始数据采集层 (Collection Layer)

### 4.1 数据组成



| 数据源               | 目标数量      | `dataset_role`  | `collection_method` | 用途                   |
| ----------------- | --------- | --------------- | ------------------- | -------------------- |
| 珀莱雅天猫公开评价         | ≈450      | `business_core` | `manual_public`     | 交易场景公开购买评价           |
| 珀莱雅小红书公开 UGC      | ≈150      | `business_core` | `manual_public`     | 场景、体验、口碑补充           |
| 中文化妆品评论 Benchmark | ≈400      | `pipeline_test` | `public_dataset`    | Pipeline/Agent/ 标签测试 |
| **合计**            | **≈1000** | —               | —                   | PoC 工程验证             |



* 允许整体浮动 ±5%，但不作为主动减少采集量的理由

* 1000 条为 PoC 规模，不得外推为珀莱雅整体消费者比例

### 4.2 产品锁定

固定 3 款产品，不得自行增加或替换：



| `target_product_id` | 产品       |
| ------------------- | -------- |
| `P001`              | 珀莱雅红宝石面霜 |
| `P002`              | 珀莱雅双抗精华  |
| `P003`              | 珀莱雅源力面霜  |



* 优先采集天猫官方旗舰店主商品页

* `product_variant` 记录版本 / SKU / 规格，无法确认则留空

* 不得自行推断产品版本

### 4.3 天猫采集规则



```
collection\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_method = manual\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_public

3款产品 × ≈150条 = ≈450条
```

**Sampling Frame：**



```
珀莱雅天猫官方旗舰店 → 对应产品主商品页 → 按"最新/时间"排序

→ 从第一条开始连续采样 → 达到目标数量
```

**时间范围：** 优先最近 6 个月 → 不足则扩展至 12 个月 → 仍不足保留实际数量，不随意更换数据源

**禁止事项：** 人工挑选好 / 差评论、按观点正负选择、修改错别字、删除表情、摘要评论、AI 重写原文、猜测页面不可见字段

### 4.4 小红书采集规则



```
每款 ≈50条，3款 ≈150条

采集 note + comment，comment 记录 parent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_content\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id
```

**采样分层：**



| `sampling_stratum`    | 每产品 | 三产品 | 用途         |
| --------------------- | --- | --- | ---------- |
| `natural_base`        | 40  | 120 | 相对自然的消费者讨论 |
| `scenario_enrichment` | 10  | 30  | 补充场景及长尾问题  |

**Natural Base：** 搜索词只用 "珀莱雅 + 产品名" 或 "产品完整名称"，禁止加入搓泥 / 过敏 / 敏感肌 / 闷痘等倾向词。每款 20 note + 20 comment = 40 条

**Scenario Enrichment：** 每款 10 条，固定覆盖 5 类维度（肤质适配 / 核心功效 / 耐受性 / 使用体验 / 购买决策），每维度 1 note + 1 comment



| 产品    | 肤质  | 核心功效 | 耐受  | 使用体验 | 购买决策 |
| ----- | --- | ---- | --- | ---- | ---- |
| 红宝石面霜 | 油皮  | 抗老   | 敏感肌 | 闷痘   | 好用吗  |
| 双抗精华  | 油皮  | 提亮   | 刺激  | 搓泥   | 好用吗  |
| 源力面霜  | 敏感肌 | 修护   | 刺痛  | 闷痘   | 好用吗  |



* 搜索格式：`产品名 + 关键词`，实际搜索词原样记录到 `query_keyword`

* 候补规则：主关键词无数据时只能在同一维度内更换候补词，禁止跨维度补数据

**防聚集规则：** 一个原始笔记最多采集 1 条评论（1 note + 最多 1 comment），禁止单篇笔记采集大量评论伪装成独立场景

**统计限制：** `scenario_enrichment` 可用于标签覆盖 / 长尾发现 / 定性案例，但禁止与 `natural_base` 混合计算问题发生率、情感比例、市场占比

### 4.5 Benchmark 规则



* 定义：中文化妆品电商评论 Benchmark（优先参考 2019 之江杯 / 天池 "电商评论观点挖掘"）

* 数量：**400 个唯一&#x20;**`review_id`，禁止将 400 行标签误认为 400 条评论

* 用途：仅用于 Pipeline 测试、Agent 标注测试、标签覆盖测试、Ground Truth 对照

* 禁止：将 Benchmark 消费者观点用于珀莱雅真实业务结论

* 统一标记：`dataset_role = pipeline_test`

**Raw 与 Gold Label 强制物理分离：**



```
data/raw/benchmark\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_reviews\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_raw.csv       ← 考试题（供Agent输入）

data/reference/benchmark\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_gold\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_labels.csv ← 标准答案（绝不进入Agent输入）
```



* 通过 `original_record_id` 关联

* 禁止将 Gold Label 写入 Raw 输入文件（label leakage）

* 若许可不允许公开再分发，仅本地测试，不上传 GitHub

### 4.6 Raw 统一字段 Schema



| 字段                    | 规则                                         | 必填               |
| --------------------- | ------------------------------------------ | ---------------- |
| `record_id`           | 项目内部唯一 ID                                  | ✅                |
| `target_product_id`   | P001/P002/P003；Benchmark 为空                | ✅                |
| `source_origin`       | `platform_public` / `benchmark_dataset`    | ✅                |
| `source_platform`     | `tmall` / `xiaohongshu` / 空                | ✅                |
| `source_type`         | `purchase_review` / `note` / `comment`     | ✅                |
| `dataset_role`        | `business_core` / `pipeline_test`          | ✅                |
| `brand`               | 原始品牌信息                                     | ✅                |
| `product_name`        | 产品名称                                       | ✅                |
| `product_variant`     | SKU / 版本；无法确认则空                            | ❌                |
| `review_text`         | 完整原始文本                                     | ✅(Business Core) |
| `publish_time_raw`    | 页面显示的原始时间文本                                | ❌                |
| `collection_time`     | 实际采集日期                                     | ✅                |
| `collection_method`   | `manual_public` / `public_dataset`         | ✅                |
| `sampling_strategy`   | 实际采样规则                                     | ✅                |
| `sampling_stratum`    | `natural_base` / `scenario_enrichment` / 空 | ❌                |
| `collection_batch_id` | 当前采集批次 ID                                  | ✅                |
| `query_keyword`       | 小红书实际搜索词；其他为空                              | ❌                |
| `search_rank`         | 可确认时记录页面位置 / 顺序                            | ❌                |
| `source_content_id`   | 平台原始内容 ID，可确认时填写                           | ❌                |
| `source_url`          | 页面来源链接，可确认时填写                              | ❌                |
| `original_dataset`    | Benchmark 数据集名称                            | ❌                |
| `original_record_id`  | Benchmark 原始 ID                            | ❌                |
| `original_split`      | Benchmark 原始 train/dev/test                | ❌                |
| `parent_content_id`   | 小红书评论所属笔记 ID                               | ❌                |
| `language`            | 中文填写 `zh-CN`                               | ✅                |

允许增加：星级、是否追评、明确公开 SKU 等可靠原始字段。不得自行推断。

### 4.7 缺失值标准



| 环境     | 缺失值           |
| ------ | ------------- |
| Excel  | 空单元格          |
| CSV    | 空字段           |
| Python | `None` / `NA` |

禁止人为写入 `NULL`/`null`/`N/A`/`未知`/`-` 作为普通字符串。

### 4.8 Raw 层禁止生成的字段

采集层禁止提前生成：`sentiment`、肤质、用户画像、使用场景、功效、需求、痛点、问题类型、购买动机、优点、缺点、改进建议、业务结论。以上由后续层处理。

### 4.9 原文保真原则

Raw 层：不修错别字、不删 emoji、不统一标点、不纠正语法、不做摘要、不做文本切分、不做 AI 重写、不提前判断正负、不判断是否广告、不判断用户肤质、不解释消费者意图。

### 4.10 隐私规则

> Consumer Voice，而非 Consumer Identity。

不主动采集：用户名、用户 ID、头像、个人主页、联系方式。公开作品集不得默认上传完整原始评论库、用户身份信息、完整 source\_url 表。

### 4.11 Codex 在 L1 的职责

**允许执行：** 创建 Excel 模板 → 建立 Schema → 生成 record\_id → Schema 校验 → 枚举值校验 → 数量检查 → 重复记录预警 → 数据角色检查 → Benchmark Raw/Gold 隔离 → Raw 备份 → CSV 导出 → Collection QA Report

**禁止执行：** 自动抓取天猫 / 小红书、模拟登录、绕过验证码、获取非公开数据、自动扩展新平台、修改人工采集原文、为凑数量自动生成评论、推断页面不可见信息

### 4.12 L1 处理流程



```
确定3款产品 → 确定天猫官方旗舰店主Listing → 确定Sampling Frame

→ 人工采集Tmall + 人工采集XHS Natural Base + 人工采集XHS Scenario Enrichment + 导入Benchmark

→ 统一Raw Schema → Benchmark Raw/Gold Label分离 → Collection QA

→ Immutable Raw保存 → 导出CSV → 交付 Cleaning Layer
```

### 4.13 L1 验收标准



| 验收项              | 标准                      |
| ---------------- | ----------------------- |
| 总规模              | 目标约 1000，允许 ±5%         |
| Tmall            | 约 450                   |
| Xiaohongshu      | 约 150                   |
| Benchmark        | 400 个唯一 review\_id      |
| Business Core    | 珀莱雅数据全部正确标记             |
| Pipeline Test    | Benchmark 全部正确标记        |
| record\_id       | 100% 唯一                 |
| 产品白名单            | 不得出现第 4 款产品             |
| review\_text     | Business Core 不得为空      |
| Schema 枚举值       | 100% 合法                 |
| 来源可追溯            | 每条数据能定位采集来源 / 规则        |
| Sampling Stratum | Natural/Enrichment 正确区分 |
| Gold Label 泄漏    | 0 条                     |
| 人工猜测字段           | 0 条                     |
| Raw 被覆盖          | 0 次                     |
| 非必要身份字段          | 0 个                     |
| 原文被 AI 改写        | 0 条                     |
| Benchmark 许可     | 已确认或明确限制                |
| 下游兼容             | 可直接进入 Raw→Clean         |



***

## 5. 第二层：清洗规则层 (Cleaning Layer)

### 5.1 目标

将 Raw Data 清洗为可进入特征加工层的数据，保证：不修改 Raw 原文、不误删真实消费者信息、每条数据可追溯、Benchmark 与业务数据严格分离、Agent 只处理语义判断，确定性问题优先由代码解决。

### 5.2 整体架构



```
Raw Data

\\\\\\\\\\\\\\\&#x20;  ↓

Rule Engine（确定性技术清洗，无LLM）

\\\\\\\\\\\\\\\&#x20;  ↓

Semantic Cleaner Agent（第一次语义判断）

\\\\\\\\\\\\\\\&#x20;  ↓

\\\\\\\\\\\\\\\&#x20;┌───────────────┐

\\\\\\\\\\\\\\\&#x20;│               │

低风险KEEP     高风险结果

\\\\\\\\\\\\\\\&#x20;│               │

进入Clean     Risk Reviewer Agent

\\\\\\\\\\\\\\\&#x20;                ↓

\\\\\\\\\\\\\\\&#x20;         ┌────────────┐

\\\\\\\\\\\\\\\&#x20;         │            │

\\\\\\\\\\\\\\\&#x20;       AGREED      CONFLICT

\\\\\\\\\\\\\\\&#x20;         │            │

\\\\\\\\\\\\\\\&#x20;      执行结果      Human Review
```

本层只有两个 Agent，不设 Judge Agent：



| Agent                    | 职责                |
| ------------------------ | ----------------- |
| `Semantic Cleaner Agent` | 判断评论是否包含有效消费者信息   |
| `Risk Reviewer Agent`    | 复核可能误删、混合内容及不确定结果 |

### 5.3 数据分流

首先读取 `dataset_role`，分两条路径：

**Business Core (**`dataset_role = business_core`**)：**



```
Rule Engine → Cleaner → 必要时Reviewer
```

**Benchmark (**`dataset_role = pipeline_test`**)：**



```
Rule Engine → 保守技术清洗（不执行普通消费者语义过滤）
```



* Benchmark 的困难样本不能因为 Cleaner 认为 "没价值" 而被提前删除

* `benchmark_gold_labels` 永远不得进入 Cleaner 或 Reviewer 输入

### 5.4 Rule Engine（纯代码，无 LLM）



| 问题          | 动作                                |
| ----------- | --------------------------------- |
| 首尾空格        | 生成标准化文本                           |
| 多余换行        | 标准化                               |
| HTML / 采集残留 | 清理                                |
| 日期格式        | 生成标准化字段 `publish_time_normalized` |
| 非法枚举        | 标记技术异常                            |
| 必填字段缺失      | 技术隔离                              |
| 明确重复采集      | 标记重复                              |
| 乱码 / 采集失败   | 技术隔离                              |

**Raw 保护：** 禁止覆盖 `review_text` 和 `publish_time_raw`，必须生成新字段 `clean_text`。Raw Data 永久不修改。

### 5.5 重复数据规则（硬规则）

**可以自动去重：** 只有确认属于同一来源记录重复采集时（相同 `source_content_id` 或 Benchmark 相同 `original_record_id`）

**不允许自动去重：** 仅因为 `review_text` 完全一样不得删除（如 "好用"" 回购 ""太油" 可能来自不同消费者）。处理：`KEEP + quality_flag = DUPLICATE_TEXT`

**语义相似：** 如 "很油"" 太油了 ""用起来比较油" 全部保留。语义相似不得作为清洗删除依据。

### 5.6 Semantic Cleaner Agent

**核心问题：** 这条文本是否包含值得进入消费者分析的有效产品信息？

**KEEP（原则上保留）：** 产品评价、功效体验、使用体验、产品问题、购买意向、产品比较、使用场景、明确产品询问、极端好评 / 差评、情绪强烈但含有效信息、很短但有明确语义的评论（如 "好用"" 回购 ""太油"" 搓泥 ""有点刺痛"" 敏感肌能用吗 "）

**FILTER（只过滤明确类型）：**



| Code            | 定义           |
| --------------- | ------------ |
| `PURE_AD`       | 纯广告，无产品体验    |
| `PURE_REDIRECT` | 纯引流 / 联系方式   |
| `OFF_TOPIC`     | 与目标产品明显无关    |
| `NO_MEANING`    | 完全没有可解释消费者信息 |



* 禁止因为 "看起来像刷单" 直接删除

* 不得输出 `FAKE_REVIEW`/`刷单`，只能根据文本本身判断

### 5.7 混合内容

如果一条评论同时包含广告 / 促销 + 真实产品体验，不得整条 FILTER：



```
action = KEEP

quality\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_flag = MIXED\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_PROMOTIONAL\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_CONTENT

review\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_required = true
```

### 5.8 上下文依赖评论

小红书 Comment 出现 "我也是"" 一样 ""确实"" 真的 " 等：



* 若 `source_type = comment` 且文本明显依赖上下文，通过 `parent_content_id` 读取所属 Note 辅助判断

* Parent Note 只用于辅助判断，不得拼接或覆盖 comment 原文

* 仍无法判断：`quality_flag = CONTEXT_DEPENDENT, review_required = true`，不得直接删除

### 5.9 Cleaner 输出格式

每条数据必须输出：



```
{

\\\\\\\\\\\\\\\&#x20; "record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id": "",

\\\\\\\\\\\\\\\&#x20; "cleaner\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_action": "KEEP | FILTER",

\\\\\\\\\\\\\\\&#x20; "reason\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_codes": \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\[],

\\\\\\\\\\\\\\\&#x20; "quality\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_flags": \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\[],

\\\\\\\\\\\\\\\&#x20; "review\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_required": true

}
```

禁止输出长篇解释。

### 5.10 必须进入 Reviewer 的情况

Reviewer 不全量运行。以下情况必须调用：



* `Cleaner = FILTER`

* `review_required = true`（广告 + 真实体验、上下文依赖、Agent 不确定、疑似模板化低信息、其他可能误删情况）

普通明确 `KEEP` 不调用 Reviewer。

### 5.11 Risk Reviewer Agent

**核心问题：** 如果按照 Cleaner 结果处理，是否可能错误删除真实消费者信息？

输出：



```
{

\\\\\\\\\\\\\\\&#x20; "record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id": "",

\\\\\\\\\\\\\\\&#x20; "reviewer\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_action": "KEEP | FILTER | UNSURE"

}
```



* 采用保守原则，无法明确确认应删除时输出 `UNSURE`，不得强制 FILTER

### 5.12 结果合并规则



| 场景                               | `final_action` | `review_status` |
| -------------------------------- | -------------- | --------------- |
| Cleaner KEEP 且无需 Reviewer        | KEEP           | NOT\_REQUIRED   |
| Cleaner FILTER + Reviewer FILTER | FILTER         | AGREED          |
| Cleaner KEEP + Reviewer KEEP     | KEEP           | AGREED          |
| 两者不同 或 Reviewer UNSURE           | PENDING\_HUMAN | CONFLICT        |



* 禁止 Agent 投票、Reviewer 强制覆盖 Cleaner、冲突状态自动删除

### 5.13 状态字段设计



| 字段              | 值                                                   |
| --------------- | --------------------------------------------------- |
| `final_action`  | KEEP / FILTER / PENDING\_HUMAN                      |
| `quality_flags` | 多值                                                  |
| `reason_codes`  | 多值                                                  |
| `review_status` | NOT\_REQUIRED / AGREED / CONFLICT / HUMAN\_RESOLVED |

**Reason Codes（第一版精简）：** `PURE_AD`, `PURE_REDIRECT`, `OFF_TOPIC`, `NO_MEANING`, `TECHNICAL_ERROR`, `SOURCE_DUPLICATE`

**Quality Flags：** `DUPLICATE_TEXT`, `MIXED_PROMOTIONAL_CONTENT`, `CONTEXT_DEPENDENT`, `SUSPECTED_TEMPLATE`, `LOW_CONFIDENCE`

### 5.14 核心输出字段



```
record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id, clean\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_text, technical\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_status, cleaner\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_action, reason\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_codes,

quality\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_flags, review\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_required, reviewer\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_action, review\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_status,

final\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_action, clean\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_version, run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id
```



* `record_id` 必须从 Collection Layer 继承，禁止重新生成新的 clean\_id

* 同时保留：`dataset_role`, `source_platform`, `source_type`, `sampling_stratum`, `target_product_id`

### 5.15 Agent 调用方式



* Batch 处理，默认 20-30 条 / 批，长文本自动降低 Batch Size（Token 安全优先）

* Agent 只返回 JSON，不输出 Chain-of-Thought 或长篇解释

* 每批返回后代码校验：输入 record\_id 集合 = 输出 record\_id 集合（无缺失 / 新增 / 重复）、JSON 合法、枚举值合法

* 失败 Retry，多次失败后 → AGENT\_ERROR 异常队列，禁止静默丢数据

### 5.16 Human Review



* 人工只处理 `final_action = PENDING_HUMAN`

* 从 Agent 已一致处理的数据中随机抽取约 5% 进行质量检查（验证系统性误删）

* 第一版用 Excel/CSV 审核即可

### 5.17 输出文件



```
data/cleaned/

├── clean\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_dataset.csv       # final\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_action = KEEP

├── filtered\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_records.csv    # final\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_action = FILTER

└── conflict\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_queue.csv      # final\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_action = PENDING\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_HUMAN

reports/cleaning\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_qa\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_report.json
```

### 5.18 Cleaning QA Report 统计项



```
Raw总数, Rule Engine技术异常数, KEEP数量, FILTER数量, CONFLICT数量,

Reviewer调用数量, Agent Error数量, Business Core数量变化, Benchmark数量变化
```



* Benchmark 出现大量样本被 FILTER 视为异常，停止流程并检查规则

### 5.19 L2 验收标准



* Raw Data 未被覆盖；`record_id`全流程不变

* Business Core 完成 Cleaner 判断；FILTER 及高风险结果完成 Reviewer 复核

* Agent 冲突全部进入 Human Review

* 短文本没有因字数被删除；极端评论没有因情绪被删除

* 文本相似没有被当成重复删除；不同消费者相同文本仍然保留

* Benchmark 未被普通语义清洗破坏；Benchmark Gold Label 未进入 Agent

* Agent 返回数据没有缺失 record\_id；所有 FILTER 均存在 reason\_code

* 数据可直接进入 Feature Processing Layer



***

## 6. 第三层：特征加工层 (Feature Processing Layer)

### 6.1 目标

将 Clean Dataset 加工为可统计、可追溯、可评测的结构化特征数据。核心原则：`record_id`全流程不变、一条评论可生成多个`feature_id`、LLM 只负责抽取不生成业务结论、所有标签必须有原文依据、Schema 固定版本运行、Topic Discovery 只负责发现 Schema 漏洞。

### 6.2 整体架构

本层使用两个 Agent + 一个算法模块：



| 组件                   | 职责                                      |
| -------------------- | --------------------------------------- |
| `Tagging Agent`      | 按 Schema v1 从评论中抽取结构化特征                 |
| `Audit Agent`        | 检查抽取结果是否有证据、分类是否合理、是否漏标                 |
| `Embedding + KMeans` | Topic Discovery，发现 Schema 盲区（不属于 Agent） |

### 6.3 主流程



```
Clean Dataset (final\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_action=KEEP)

\\\\\\\\\\\\\\\&#x20;     ↓

继承 Metadata（record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id, dataset\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_role, source\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_platform, source\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_type,

\\\\\\\\\\\\\\\&#x20;             sampling\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_stratum, target\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_product\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id, product\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_name,

\\\\\\\\\\\\\\\&#x20;             clean\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_text, quality\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_flags）

\\\\\\\\\\\\\\\&#x20;     ↓

Tagging Agent（Schema v1 多标签抽取）

\\\\\\\\\\\\\\\&#x20;     ↓

Feature Long Table

\\\\\\\\\\\\\\\&#x20;     ↓

Schema Validator（代码校验）

\\\\\\\\\\\\\\\&#x20;     ↓

Audit Agent

\\\\\\\\\\\\\\\&#x20;     ↓

PASS → Feature Dataset v1

REVIEW → Human Review Queue

\\\\\\\\\\\\\\\&#x20;     ↓

Decision Layer
```

并行运行 Topic Discovery：



```
OTHER / UNKNOWN / 未映射内容 → Embedding → KMeans → NEW\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_TOPIC\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_CANDIDATE

→ Human Review → Schema v2候选
```

### 6.4 输入范围



* 只处理 `final_action = KEEP` 的数据

* 必须从上游继承 Metadata，禁止让 Tagging Agent 重新判断产品名 / 产品 ID / 平台信息

### 6.5 数据结构：Long Format

一条评论包含多个独立消费者观点时，每个观点生成一个 `feature_id`：



```
record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id

\\\\\\\\\\\\\\\&#x20;  ├── feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_1

\\\\\\\\\\\\\\\&#x20;  ├── feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_2

\\\\\\\\\\\\\\\&#x20;  └── feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_n
```

示例："保湿不错，但是有点厚，油皮夏天用会闷。"



| record\_id | feature\_id | aspect          | opinion | polarity |
| ---------- | ----------- | --------------- | ------- | -------- |
| R001       | F001        | MOISTURIZING    | 保湿不错    | POSITIVE |
| R001       | F002        | TEXTURE\_HEAVY  | 有点厚     | NEGATIVE |
| R001       | F003        | STUFFY\_FEELING | 会闷      | NEGATIVE |

禁止将多个标签无结构地塞入同一个字符串字段。

### 6.6 Schema v1（`config/schema_v1.json`）

Schema 必须保存为独立版本文件，第一版保持 "小而稳定"。Agent 不得自行创造新正式标签。

**核心维度（aspect\_category）：**



```
EFFICACY, TEXTURE, SKIN\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_FEEL, PACKAGING, PRICE, FRAGRANCE,

INGREDIENT, USAGE, PURCHASE, SKIN\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_TYPE, USAGE\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_SCENE, OTHER, UNKNOWN
```

**示例子标签（aspect\_label）：**



```
EFFICACY → MOISTURIZING, BRIGHTENING, REPAIR, ANTI\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_AGING

SKIN\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_FEEL → GREASY, STICKY, HEAVY, PILLING, ABSORPTION

SKIN\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_TYPE → OILY, DRY, SENSITIVE, COMBINATION, NORMAL

USAGE\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_SCENE → SUMMER, WINTER, DAY, NIGHT, BEFORE\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_MAKEUP, AFTER\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_SUN
```

> 具体完整 Schema 以
> `schema_v1.json`
> 为唯一执行依据。Codex 需根据上述维度和子标签构建完整 JSON 文件。

### 6.7 OTHER / UNKNOWN / NEW\_TOPIC\_CANDIDATE 区分



| 类型                    | 定义                                                                          |
| --------------------- | --------------------------------------------------------------------------- |
| `OTHER`               | 文本有明确语义，但当前 Schema 没有合适标签                                                   |
| `UNKNOWN`             | 文本信息不足，无法判断具体类别                                                             |
| `NEW_TOPIC_CANDIDATE` | 只能由 Topic Discovery 从 OTHER/UNKNOWN/unmapped evidence 中发现，经人工审核后才能升级 Schema |

### 6.8 Tagging Agent 职责

只负责从 `clean_text` 中提取明确出现的消费者观点。每个 Feature 至少输出：



```
feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id, record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id, aspect\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_category, aspect\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_label, opinion\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_type,

opinion\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_text, polarity, evidence\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_text, schema\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_version
```

**Opinion Type：** `PRAISE`, `COMPLAINT`, `QUESTION`, `SUGGESTION`, `NEUTRAL`

**Polarity：** `POSITIVE`, `NEGATIVE`, `NEUTRAL`, `MIXED`



* 禁止在本层直接生成 `PAIN_POINT`/`OPPORTUNITY`/`BUSINESS_PRIORITY`（属于下一层业务结论）

### 6.9 Evidence 约束



* 所有 Feature 必须包含 `evidence_text`

* `evidence_text` 必须来自 `clean_text` 中实际存在的原文片段

* 禁止 AI 自己总结成不存在的句子、根据常识补充、推断用户未明确表达的信息

* 没有证据时不得生成该标签

### 6.10 缺失值规则

严格区分：



* **未提及** → `null`

* **明确负面结果**（如 "用了一个月完全没有提亮"）→ 保留对应 `BRIGHTENING + NEGATIVE`，不能写 `effect = null`

> Missing ≠ Negative ≠ Zero

### 6.11 严重程度评分

第一版取消主观严重程度评分，不允许 Agent 输出 `severity = 1~5`。消费者明确表达的严重后果保留证据，是否构成严重问题由 Decision Layer 判断。

### 6.12 Schema Validator（代码校验）

Tagging Agent 输出后必须先使用普通代码进行结构校验：



* `record_id` 是否存在

* `feature_id` 是否唯一

* 标签是否属于 Schema

* polarity 是否合法

* evidence\_text 是否为空

* schema\_version 是否一致

* JSON 结构是否合法

失败记录不得静默进入 Feature Dataset。

### 6.13 Audit Agent

不是重新完整 Tagging。输入：`clean_text + Tagging Result + Schema定义`，只检查：



1. evidence 是否真实存在

2. evidence 是否支持标签

3. aspect 分类是否合理

4. polarity 是否与原文一致

5. 是否存在明显漏掉的重要观点

输出：`PASS` / `REVIEW`

**错误类型（固定）：** `UNSUPPORTED_EVIDENCE`, `WRONG_ASPECT`, `WRONG_POLARITY`, `POSSIBLE_MISSING_TAG`, `SCHEMA_VIOLATION`



* `PASS` → Feature Dataset v1

* `REVIEW` → Human Review Queue

* 第一版禁止无限循环（Tagging→Audit→Retag→Audit...），Human Review 完成后形成最终结果

### 6.14 Topic Discovery



* 第一版固定采用 `Embedding + KMeans`，不使用 BERTopic 作为主流程

* 重点输入：`OTHER`, `UNKNOWN`, `unmapped evidence`（不是重新对全部评论进行业务分类）

* 目的：发现当前 Schema 没有覆盖的新问题

**采样限制：**



* `natural_base`：可用于主要新 Topic 发现

* `scenario_enrichment`：只能作为候选 Topic 补充证据，不得根据其频率推断某 Topic 在消费者中很流行

**升级规则：** 发现新 Cluster → `NEW_TOPIC_CANDIDATE` → 人工审核（是否真正新主题 / 是否已有 Schema 可覆盖 / 是否值得新增）→ 确认后升级 `schema_v1 → schema_v2`

### 6.15 Schema 版本硬规则



* 一次完整 Feature Run 中 `schema_version` 必须固定

* 禁止前 300 条用 schema\_v1、后 300 条用 schema\_v2 后直接混合统计

* 升级到 schema\_v2 后，所有需要横向比较的数据必须重新执行 Tagging

### 6.16 Batch Tagging



* 初始 20-30 条 / 批，不作为硬编码

* 根据 Token 长度、输出完整率、漏标率、JSON 稳定性、成本动态调整

* 长文本自动降低单批数量

* 每批校验：输入 record\_id 集合 = 输出 record\_id 覆盖集合，无未知 record\_id、无非法 Schema 标签、无非法 polarity、无缺失必要字段、JSON 可解析

* 失败 Retry → 仍失败 → AGENT\_ERROR Queue，禁止静默丢数据

### 6.17 Project Gold Dataset

从 Business Core Clean Dataset 中建立约 100 条人工 Gold：



```
80条分层随机样本 + 20条Hard Cases
```



* 80 条覆盖：3 款产品、Tmall/Xiaohongshu、natural\_base/scenario\_enrichment、长短文本、单观点 / 多观点

* 20 条 Hard Cases 覆盖：OTHER、UNKNOWN、多 Aspect、Mixed Polarity、复杂上下文

**建立顺序（硬规则）：**



```
抽样 → 人工依据Schema独立标注 → 冻结Gold Dataset → 运行Tagging Agent → Prediction vs Gold
```

禁止先查看模型预测再按照模型结果制作 Gold。

### 6.18 评测指标

Project Gold 至少报告：



```
Micro Precision, Micro Recall, Micro F1
```

补充：`Per-label F1`, `Error Analysis`



* `F1 > 0.8` 仅作为第一版参考目标，不作为未经实测的硬验收线

**Benchmark 评测分离：** `Project Gold Evaluation` 与 `Benchmark Evaluation` 不得混算一个 F1。Benchmark 只有当原始 Gold 标签能明确映射到当前 Schema 时才参与对照。Benchmark Gold Label 不得进入 Tagging Agent 输入。

### 6.19 核心输出字段（Feature Long Table）



```
feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id, record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id, dataset\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_role, source\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_platform, source\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_type,

sampling\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_stratum, target\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_product\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id, product\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_name,

aspect\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_category, aspect\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_label, opinion\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_type, opinion\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_text, polarity,

evidence\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_text, schema\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_version, audit\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_status, error\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_type, run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id
```

### 6.20 输出文件



```
data/features/

├── feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_dataset\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_v1.csv

├── feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_review\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_queue.csv

└── topic\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_candidates.csv

data/reference/project\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_gold\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_v1.csv

reports/

├── feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_evaluation.json

└── feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_error\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_analysis.csv
```

### 6.21 L3 验收标准



* `record_id`未改变；每个`feature_id`唯一；一条评论允许生成多个 Feature

* 产品及来源 Metadata 全部继承，不由 LLM 重生成

* 所有 Feature 都有原文 Evidence；Schema 标签全部合法

* OTHER/UNKNOWN/NEW\_TOPIC\_CANDIDATE 含义明确

* Topic Discovery 不直接生成最终业务标签

* natural\_base 与 scenario\_enrichment 没有混淆

* Audit REVIEW 全部进入人工队列

* 一个 Run 只使用一个 Schema 版本

* Gold Dataset 建立顺序正确；Project Gold 与 Benchmark 评测分开

* 数据可直接进入 Decision Layer



***

## 7. 第四层：决策输出层 (Decision Output Layer)

### 7.1 目标

将 Feature Dataset 转化为可比较、可追溯、可持续更新的决策结果，用于展示产品优点、消费者问题、产品差异、场景切片、新兴主题和机会候选。

### 7.2 核心约束（14 条）



| #  | 约束                                                                          |
| -- | --------------------------------------------------------------------------- |
| 1  | 所有业务频率默认按 **unique&#x20;**`record_id` 统计，禁止直接按 `feature_id` 数量计数            |
| 2  | `pipeline_test` 不得进入珀莱雅业务结论                                                 |
| 3  | Xiaohongshu `scenario_enrichment` 不参与比例、排行、趋势统计，只用于定性证据和场景补充                |
| 4  | 痛点排行默认按 `negative_mention_rate`；优点排行默认按 `positive_mention_rate`             |
| 5  | `mention_count < 3` 的 Topic 标记 `LOW_SUPPORT`，不进入正式排行                        |
| 6  | 不同渠道默认分别统计（Tmall 内部比较 3 款、XHS Natural Base 内部比较 3 款），不直接合并推断市场总体            |
| 7  | 只允许使用原文明确表达的 `SKIN_TYPE / USAGE_SCENE`，禁止推断年龄、性别、职业等人口属性                    |
| 8  | 趋势必须基于 `publish_time_normalized`，Snapshot 不得作为趋势时间单位                        |
| 9  | 第一版采用连续非重叠 2 个月窗口；N≥30、主题 mention\_count≥5、连续 3 个合格窗口后才能定义趋势                |
| 10 | Opportunity 只生成 Candidate List，不计算未经验证的综合 Opportunity Score                 |
| 11 | 每个重要结论绑定 3-5 条真实证据，通过 `feature_id → record_id` 回溯原始评论                       |
| 12 | Schema、清洗规则、Prompt、Model 或 Metric 版本变化时，历史窗口必须重跑或标记 `COMPARABILITY_WARNING` |
| 13 | 指标异常时先检查：重复采集、scenario\_enrichment 误混入、时间错位、record 重复计数、Schema 变化           |
| 14 | 所有比例、排行、趋势由确定性代码计算，LLM 不得自行修改数值或排序                                          |

### 7.3 推荐数据流



```
Feature Dataset

\\\\\\\\\\\\\\\&#x20;     ↓

Eligible Sample Filter（business\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_core + 合法sampling\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_stratum）

\\\\\\\\\\\\\\\&#x20;     ↓

Record-level Aggregation（unique record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id）

\\\\\\\\\\\\\\\&#x20;     ↓

Metric Engine（mention / positive / negative / context）

\\\\\\\\\\\\\\\&#x20;     ↓

Consistency Validator

\\\\\\\\\\\\\\\&#x20;     ↓

Trend Eligibility Check

\\\\\\\\\\\\\\\&#x20;     ↓

Evidence Binding

\\\\\\\\\\\\\\\&#x20;     ↓

Decision Output（优点/痛点/产品对比/场景切片/趋势/新Topic/Opportunity Candidate）

\\\\\\\\\\\\\\\&#x20;     ↓

Snapshot Freeze
```

### 7.4 核心指标



```
mention\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_count = 包含目标Topic的 unique record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id 数

mention\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_rate = mention\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_count / 当前切片有效 unique record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id 总数

negative\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_mention\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_rate = NEGATIVE主题 unique record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id / 当前切片有效评论总数

positive\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_mention\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_rate = POSITIVE主题 unique record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id / 当前切片有效评论总数
```



* `MIXED` 单独统计，不强行归入正面或负面

### 7.5 排行规则



* 痛点排行：默认按 `negative_mention_rate` 降序

* 优点排行：默认按 `positive_mention_rate` 降序

* `mention_count < 3` → 标记 `LOW_SUPPORT`，不进入正式排行

* 所有排行同时展示 `mention_count`、样本量 `n`、`support_status`

### 7.6 产品与渠道比较



* 不同渠道默认独立统计：Tmall 内部比较 3 款产品、XHS Natural Base 内部比较 3 款产品

* 不得因人为采样比例不同直接合并推断总体市场

* 渠道展示用 Small Multiples / 并列图，不用 450 vs 150 绝对量直接比较

### 7.7 场景切片



* 只使用第三层显式抽取的 `SKIN_TYPE / USAGE_SCENE`（如油皮、敏感肌、夏季、妆前）

* 禁止根据评论内容推断年龄、性别、职业、收入等人口属性

* "人群" 统一改为 "显式肤质 / 使用场景"

### 7.8 趋势规则



```
publish\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_time\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_normalized

\\\\\\\\\\\\\\\&#x20;     ↓

连续非重叠2个月窗口

\\\\\\\\\\\\\\\&#x20;     ↓

每窗口：有效评论 N ≥ 30 + 目标主题 mention\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_count ≥ 5

\\\\\\\\\\\\\\\&#x20;     ↓

连续3个合格窗口

\\\\\\\\\\\\\\\&#x20;     ↓

允许输出：UP / DOWN / STABLE
```



* 只有 2 个合格窗口：仅输出 period-over-period change（如 8%→12% = +4 percentage points），不得定义为长期趋势

* 数据不足：`INSUFFICIENT_DATA`

* `NEW_TOPIC_CANDIDATE` 在完成历史回标前不得展示趋势

### 7.9 Opportunity Candidate List

候选来源：



```
高频负面Topic OR 明显增长的负面Topic OR 人工确认的NEW\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_TOPIC\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_CANDIDATE
```

输出字段：



```
topic, product, channel, mention\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_count, mention\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_rate, negative\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_mention\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_rate,

trend\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_status, explicit\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_context, evidence\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_count, support\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_status, ranking\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_basis
```



* 允许按单一指标排序（按 negative\_mention\_rate / 按 mention\_rate / 按 trend change）

* **禁止自行生成综合加权分 / Opportunity Score**

* 第一版不生成 `priority` / `confidence百分比` / `owner自动映射`

### 7.10 Evidence Binding



* 每个重要痛点 / 优点 / 机会候选绑定 3-5 条真实评论证据

* 通过 `metric → feature_id → record_id → Raw` 追溯

* evidence 必须支持当前 Topic；不重复 record\_id；不只挑最极端评论

* 证据不足标记 `INSUFFICIENT_EVIDENCE`

### 7.11 Snapshot



* Snapshot 只负责结果冻结和版本追踪

* 新数据追加后重新计算并生成新 Snapshot，不静默修改历史结果

* 历史错误需生成修正版

* 每个 Snapshot 记录：`snapshot_id`, `snapshot_date`, `schema_version`, `clean_version`, `tagging_prompt_version`, `model_identifier`, `metric_version`, `data_cutoff`

### 7.12 一致性校验

检查 Raw → Clean → Feature → Decision 的：



* 数量链路（各层记录数变化可解释）

* 重复率

* 时间字段完整性

* Schema 版本一致性

* 采样范围正确性

* 指标异常突增时必须先排查数据和版本问题

### 7.13 第三层必要补丁

Feature Schema v1 增加 `SKIN_TYPE` 和 `USAGE_SCENE` 维度：



* 只允许抽取消费者原文明确表达的信息（如 "我是油皮"→SKIN\_TYPE=OILY；"夏天用有点厚"→USAGE\_SCENE=SUMMER）

* 禁止从 "感觉很油" 推断 SKIN\_TYPE=OILY

### 7.14 输出文件



```
data/decisions/

├── decision\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_metrics.csv          # 所有指标计算结果

├── opportunity\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_candidates.csv    # 机会候选清单

├── evidence\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_bindings.csv         # 证据绑定关系

└── snapshots/

\\\\\\\\\\\\\\\&#x20;   └── snapshot\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_YYYYMMDD/        # 每次运行的完整快照

reports/decision\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_consistency\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_report.json
```

### 7.15 L4 验收标准



* 所有统计按 unique record\_id，无 feature\_id 重复计数

* pipeline\_test 未进入业务结论

* scenario\_enrichment 未参与比例 / 排行 / 趋势

* 痛点 / 优点排行口径正确，LOW\_SUPPORT 已标记

* 渠道独立统计，未直接合并

* 趋势满足窗口 / 样本量 / 连续性条件

* Opportunity 只有 Candidate List，无综合 Score

* 每个重要结论有 3-5 条证据且可回溯

* 版本元数据完整，跨版本比较有警告

* 一致性校验通过



***

## 8. 第五层：数据呈现层 (Data Presentation Layer)

### 8.1 目标

将 Decision Output 以 "总览 → 发现 → 下钻 → 证据 → 建议 → 推送" 的方式呈现，保证指标、证据、版本和飞书消息全链路可追溯。

### 8.2 核心模块（10 个）



| # | 模块                           | 方案                                                                                                                  |
| - | ---------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| ① | 消费者洞察总览                      | 有效评论数、Top 痛点、Top 优点、Opportunity Candidate、新兴主题、最新 Snapshot。不得称为 "经营总览"（无销量 / GMV / 库存数据）                            |
| ② | 痛点 / 优点排行                    | 直接读取第四层结果，痛点按 negative\_mention\_rate，优点按 positive\_mention\_rate。展示 mention\_count、n、support\_status。第五层不得重新计算排名   |
| ③ | 产品 ×Topic 对比                 | 三款产品按 mention\_rate/negative\_mention\_rate/positive\_mention\_rate 展示热力图或分组条形图                                     |
| ④ | 显式肤质 / 使用场景切片                | 仅展示第三层明确抽取的 SKIN\_TYPE/USAGE\_SCENE，不得推断人口画像                                                                        |
| ⑤ | 渠道内部结构                       | Tmall 与 XHS Natural Base 分别统计并并列展示；不得因采样机制不同直接推断真实平台总体差异                                                            |
| ⑥ | 趋势与新主题                       | 趋势只读取第四层已满足条件的 trend\_status；NEW\_TOPIC\_CANDIDATE 在完成历史回标前不得展示趋势                                                   |
| ⑦ | Evidence Drill-down          | 每个关键指标可下钻至 3-5 条真实证据，通过 decision\_id→feature\_id→record\_id→Raw 回溯                                                  |
| ⑧ | Insight Recommendation Agent | 仅将已计算指标转成 "事实→模式→待验证假设→建议动作"，不得重新计算指标、改变排序或推断因果                                                                     |
| ⑨ | Model Ops Dashboard          | 独立展示 Cleaning/Feature QA、UNKNOWN 率、OTHER 率、Audit REVIEW 率、Project Gold F1、Benchmark F1、Schema / 模型版本和数据新鲜度。不得混入业务首页 |
| ⑩ | 飞书推送                         | Demo 固定使用 Feishu Custom Webhook Bot + Message Card；只做 Alert、Weekly Digest、New Topic Alert。飞书只负责提醒和回流，不替代 Dashboard  |

### 8.3 展示规则



| 场景        | 推荐方式                  | 禁止                   |
| --------- | --------------------- | -------------------- |
| 排名        | 横向条形图                 | 大量类别饼图               |
| 产品 ×Topic | 热力图 / 分组条形图           | 复杂 3D 图              |
| 趋势        | 折线图                   | 样本不足时强行画趋势           |
| 渠道        | Small Multiples / 并列图 | 用 450 vs 150 绝对量直接比较 |
| 证据        | 明细表 + Drill-down      | 只展示 AI 总结            |
| 新主题       | Candidate List        | 未历史回标就展示增长趋势         |

**统一规则：**



1. 所有图表同时显示指标值 + 样本量 n

2. `LOW_SUPPORT` / `INSUFFICIENT_EVIDENCE` / `COMPARABILITY_WARNING` 必须显式展示

3. 正向、负向、Mixed 不是互斥比例，不强制合计 100%，默认不用 100% 堆叠图

4. `pipeline_test` 不进入珀莱雅业务 Dashboard

5. Xiaohongshu `scenario_enrichment` 不进入比例、排行、趋势图，只能作为定性补充证据

### 8.4 页面结构

**A. Consumer Insight Dashboard（第一版 5 个区域）：**



```
① Overview：有效评论数 / Top 3 Pain / Top 3 Advantage / Opportunity Candidates / Latest Snapshot

② Product × Topic：三产品主题热力图

③ Context：SKIN\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_TYPE × USAGE\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_SCENE × Topic

④ Trend / New Topic：仅展示第四层已满足条件的趋势和新Topic

⑤ Evidence Drill-down：Metric → Evidence → feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id → record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id
```

**B. Model Ops Dashboard（直接读取前三层 QA 结果）：**



```
Cleaning KEEP/FILTER/CONFLICT, Agent Error, Feature Audit REVIEW Rate,

UNKNOWN Rate, OTHER Rate, Project Gold Micro F1, Benchmark F1,

Schema Version, Clean Version, Model Identifier, Latest Data Cutoff
```



* `Project Gold F1` 与 `Benchmark F1` 必须分开显示

### 8.5 Insight Recommendation Agent

**唯一职责：** 基于已经计算完成的 Decision Output 和 Evidence，生成 "待验证业务建议"。

**输入：** `decision_id, metric/result, evidence, support_status, version metadata`

**输出：**



```
fact, pattern, hypothesis, recommendation, validation\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_next\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_step,

support\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_status, trace\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id
```

**示例逻辑：**



```
FACT：油腻负向提及率较高，n=XX

PATTERN：显式油皮 + 夏季场景中更集中

HYPOTHESIS：可能存在特定肤质/季节下的使用体验问题

RECOMMENDATION：建议进一步验证油皮夏季使用体验，并检查产品使用指引

VALIDATION：补充定向用户测试 / 产品测试
```

**禁止：** `priority`、`confidence百分比`、`owner自动映射`、`Opportunity Score`、未经证据支持的因果判断

### 8.6 Evidence 与追溯

第四层需生成稳定 `decision_id`。完整链路：



```
Dashboard / Feishu Message → alert\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id → decision\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id → snapshot\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id

→ feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id → record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id → Raw Record → source\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_url / source\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_content\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id
```

每个重要痛点 / 优点 / Opportunity Candidate：



* 绑定 3-5 条真实命中记录

* evidence 必须支持当前 Topic；不重复 record\_id；不只挑最极端评论

* 证据不足时显示 `INSUFFICIENT_EVIDENCE`

* 公开作品集不得默认展示完整 source\_url、用户身份信息或可重新定位用户的信息

### 8.7 飞书 Demo 方案



```
Decision Output → Alert Engine（确定性触发规则）→ alert\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_record

→ Feishu Custom Webhook Bot → Message Card → 查看详情/查看证据

→ Dashboard对应筛选页
```

**推送类型：**



| 类型                | Demo 规则                                                       |
| ----------------- | ------------------------------------------------------------- |
| `Alert`           | 消费第四层已满足条件的 `trend_status=UP` 且无 `COMPARABILITY_WARNING` 的结果  |
| `Weekly Digest`   | 汇总 Top Pain、Top Advantage、Trend Change、Opportunity Candidates |
| `New Topic Alert` | `NEW_TOPIC_CANDIDATE` 经人工确认需关注后触发                             |



* 第一版不做 Daily Digest

* 飞书不得自行重新计算指标或发明新阈值

### 8.8 飞书追溯字段

**用户可见：**



```
标题, 统计窗口/snapshot\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_date, 产品/Topic, 当前指标+变化, sample\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_size,

channel, support\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_status, 更新时间, 查看详情, 查看证据
```

**后台记录：**



```
alert\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id, decision\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id, trace\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id, snapshot\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id, run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id, schema\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_version,

clean\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_version, tagging\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_prompt\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_version, model\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_identifier, metric\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_version,

generated\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_at, sent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_at, message\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id, send\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_status, retry\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_count,

dashboard\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_deep\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_link, evidence\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_deep\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_link
```

**防重复：** 同一 `snapshot_id + alert_rule + product + topic` 不得重复推送

**安全：** Webhook Secret 等凭证只能通过环境变量 / Secret 管理，不得写入日志、Dashboard 或公开仓库

### 8.9 推荐数据流



```
Decision Output

\\\\\\\\\\\\\\\&#x20;     ↓

Presentation Validator（检查support/version/warning）

\\\\\\\\\\\\\\\&#x20;     ↓

Consumer Insight Dashboard

\\\\\\\\\\\\\\\&#x20;     ↓

Evidence Drill-down

\\\\\\\\\\\\\\\&#x20;     ↓

Insight Recommendation Agent

\\\\\\\\\\\\\\\&#x20;     ↓

Alert Engine

\\\\\\\\\\\\\\\&#x20;     ↓

Feishu Webhook Bot
```

并行：



```
Cleaning / Feature QA Reports → Model Ops Dashboard
```

### 8.10 L5 验收标准



* 可从总览下钻到产品、Topic、肤质 / 场景和原始证据

* 所有关键指标同时展示样本量 n

* `LOW_SUPPORT` / `INSUFFICIENT_EVIDENCE` / `COMPARABILITY_WARNING` 可见

* Dashboard 不重新计算第四层指标

* 业务 Dashboard 与 Model Ops Dashboard 分离

* NEW\_TOPIC 未历史回标时不展示趋势

* AI 建议明确区分事实、模式、假设和建议

* 每条飞书消息拥有唯一 `alert_id / decision_id / trace_id`

* 飞书可回链 Dashboard 与 Evidence

* 历史结果可通过 Snapshot+Schema+Clean+Prompt+Model+Metric Version 还原

* 不公开非必要用户身份和可重新定位用户的信息



***

## 9. 跨层硬约束汇总

### 9.1 数据血缘（全流程不变字段）

以下字段从 Raw 层产生后，所有后续层必须保留，不得因加工丢失：



```
record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id, dataset\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_role, source\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_platform, source\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_type,

sampling\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_stratum, target\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_product\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id
```

关系：



```
Raw (record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id)

\\\\\\\\\\\\\\\&#x20; ↓ Cleaning (record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id 不变，新增 clean\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_text/final\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_action)

\\\\\\\\\\\\\\\&#x20; ↓ Feature (record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id 不变，新增 feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id，一对多)

\\\\\\\\\\\\\\\&#x20; ↓ Decision (record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id 不变，聚合为 decision\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id)

\\\\\\\\\\\\\\\&#x20; ↓ Presentation (decision\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id → feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id → record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id 可回溯)
```



* 禁止重新生成 `clean_id` / `raw_id` / `source_ref`，全链路统一使用 `record_id`

* `business_core` ≠ `pipeline_test`，不得在业务统计时无差别混合

* `natural_base` ≠ `scenario_enrichment`，不得在比例统计时无差别混合

### 9.2 版本管理

每次完整 Pipeline 运行必须记录并传递：



```
schema\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_version, clean\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_version, tagging\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_prompt\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_version,

model\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_identifier, metric\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_version, run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id
```



* 跨时间比较必须保持上述版本一致

* 版本变化时需重跑历史窗口或标记 `COMPARABILITY_WARNING`

### 9.3 LLM 使用边界



| 层级              | LLM 用途                        | LLM 禁止                       |
| --------------- | ----------------------------- | ---------------------------- |
| L1 Collection   | 无（纯人工 + 代码校验）                 | 自动抓取、生成评论、改写原文               |
| L2 Cleaning     | Cleaner 语义判断、Reviewer 误删复核    | 技术清洗、修改原文、自动删除冲突             |
| L3 Feature      | Tagging 抽取、Audit 审核           | 生成业务结论、主观严重度评分、创造 Schema 外标签 |
| L4 Decision     | 无（纯确定性代码计算）                   | 修改数值、改变排序、生成未经数据支持的结论        |
| L5 Presentation | Insight Recommendation（事实→建议） | 重新计算指标、推断因果、生成综合 Score       |

### 9.4 人工介入点



```
L1：人工采集录入（Tmall/XHS/Benchmark导入）

L2：PENDING\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_HUMAN 冲突审核 + 5%随机质量抽检

L3：Audit REVIEW 审核 + NEW\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_TOPIC\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_CANDIDATE 审核 + Project Gold 标注

L4：NEW\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_TOPIC\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_CANDIDATE 确认（影响Opportunity和趋势）

L5：New Topic Alert 触发前确认
```



***

## 10. Codex 执行顺序清单

Codex 按以下顺序逐步部署执行，每步完成后验证再进入下一步：

### Phase 0：项目初始化



```
□ 1. 创建项目目录结构（第1节）

□ 2. 编写 requirements.txt 并安装依赖

□ 3. 编写 config/config.yaml（第3节）

□ 4. 编写 config/schema\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_v1.json（第6.6节，完整维度+子标签）

□ 5. 实现 src/common/ 下的通用模块（llm\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_client, id\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_utils, version, io\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_utils）

□ 6. 创建 templates/proya\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_collection\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_raw.xlsx 采集模板（4个Sheet）
```

### Phase 1：L1 Collection Layer



```
□ 7. 实现 src/collection/schema.py（Raw Schema定义与校验）

□ 8. 实现 src/collection/id\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_generator.py（record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id生成规则）

□ 9. 实现 src/collection/qa\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_checker.py（Collection QA Report）

□ 10. 实现 src/collection/exporter.py（Excel→CSV导出，Raw只读保护）

□ 11. 编写 scripts/01\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_collection.py

□ 12. 【人工】使用模板采集Tmall≈450 + XHS≈150 + 导入Benchmark≈400

□ 13. 运行Collection QA，验证第4.13节全部验收项

□ 14. 导出 data/raw/ 下三个CSV + data/reference/benchmark\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_gold\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_labels.csv
```

### Phase 2：L2 Cleaning Layer



```
□ 15. 实现 src/cleaning/rule\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_engine.py（确定性技术清洗，无LLM）

□ 16. 实现 src/cleaning/cleaner\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent.py（Semantic Cleaner，JSON输出）

□ 17. 实现 src/cleaning/reviewer\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent.py（Risk Reviewer）

□ 18. 实现 src/cleaning/merge\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_results.py（结果合并逻辑）

□ 19. 实现 src/cleaning/qa\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_report.py

□ 20. 编写 scripts/02\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_cleaning.py

□ 21. 运行Cleaning Pipeline（Business Core全量，Benchmark仅技术清洗）

□ 22. 【人工】处理 conflict\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_queue.csv 中的 PENDING\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_HUMAN

□ 23. 验证第5.19节全部验收项，生成 clean\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_dataset.csv
```

### Phase 3：L3 Feature Processing Layer



```
□ 24. 实现 src/features/tagging\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent.py（Schema v1多标签抽取，Long Format）

□ 25. 实现 src/features/schema\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_validator.py（代码结构校验）

□ 26. 实现 src/features/audit\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent.py（PASS/REVIEW审核）

□ 27. 实现 src/features/topic\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_discovery.py（Embedding+KMeans）

□ 28. 实现 src/features/gold\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_builder.py（100条Gold抽样+冻结）

□ 29. 实现 src/features/evaluator.py（Precision/Recall/F1）

□ 30. 编写 scripts/03\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_features.py

□ 31. 【人工】标注Project Gold（80分层+20 Hard Cases），冻结后再运行Agent

□ 32. 运行Tagging → Schema Validator → Audit

□ 33. 【人工】处理 feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_review\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_queue.csv + 审核 topic\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_candidates.csv

□ 34. 运行评测，生成 feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_evaluation.json + feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_error\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_analysis.csv

□ 35. 验证第6.21节全部验收项
```

### Phase 4：L4 Decision Output Layer



```
□ 36. 实现 src/decisions/sample\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_filter.py（business\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_core隔离）

□ 37. 实现 src/decisions/metric\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_engine.py（unique record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id统计）

□ 38. 实现 src/decisions/trend\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_engine.py（2个月窗口趋势）

□ 39. 实现 src/decisions/evidence\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_binder.py（3-5条证据绑定）

□ 40. 实现 src/decisions/opportunity.py（Candidate List，无综合Score）

□ 41. 实现 src/decisions/consistency.py（跨层一致性校验）

□ 42. 实现 src/decisions/snapshot.py（版本冻结）

□ 43. 编写 scripts/04\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_decisions.py

□ 44. 运行Decision Pipeline，生成 decision\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_metrics.csv + opportunity\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_candidates.csv

□ 45. 验证第7.15节全部验收项，生成第一个Snapshot
```

### Phase 5：L5 Data Presentation Layer



```
□ 46. 实现 src/presentation/dashboard\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_builder.py（Dashboard数据组装，输出JSON）

□ 47. 实现 src/presentation/insight\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent.py（事实→模式→假设→建议）

□ 48. 实现 src/presentation/alert\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_engine.py（确定性触发规则）

□ 49. 实现 src/presentation/feishu\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_bot.py（Webhook发送+追溯字段）

□ 50. 编写 scripts/05\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_presentation.py

□ 51. 【配置】设置飞书Webhook环境变量

□ 52. 运行Presentation，生成Dashboard数据 + 测试飞书推送

□ 53. 验证第8.10节全部验收项
```

### Phase 6：端到端验证



```
□ 54. 全链路数量一致性检查（Raw→Clean→Feature→Decision记录数可解释）

□ 55. 随机抽取5条结论，验证 decision\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id→feature\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id→record\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id→Raw 可回溯

□ 56. 验证 pipeline\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_test 未出现在任何业务Dashboard/排行/趋势中

□ 57. 验证 scenario\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_enrichment 未参与比例/排行/趋势统计

□ 58. 验证所有版本元数据（schema/clean/prompt/model/metric）完整记录

□ 59. 生成最终项目 README.md（含架构图、运行说明、验收结果）
```



***

## 11. 全局验收标准总表



| 层级                  | 核心验收项        | 通过标准                                                            |
| ------------------- | ------------ | --------------------------------------------------------------- |
| **L1 Collection**   | 数据规模         | 约 1000 条（±5%），Tmall≈450、XHS≈150、Benchmark=400 唯一 review\_id     |
|                     | 数据质量         | record\_id 100% 唯一，Schema 枚举 100% 合法，原文 0 条被改写                  |
|                     | 隔离合规         | Gold Label 泄漏 0 条，非必要身份字段 0 个，Raw 被覆盖 0 次                       |
| **L2 Cleaning**     | 清洗完整         | Business Core 全部完成 Cleaner 判断，FILTER / 高风险完成 Reviewer           |
|                     | 不误删          | 短文本 / 极端评论 / 相似文本均保留，冲突全部进入 Human Review                        |
|                     | Benchmark 保护 | Benchmark 未被语义清洗破坏，Gold Label 未进入 Agent                         |
| **L3 Feature**      | 结构化          | 每个 feature\_id 唯一，一条评论允许多 Feature，全部有原文 Evidence                |
|                     | Schema 合规    | 标签全部合法，一个 Run 一个 Schema 版本，Metadata 不由 LLM 重生成                  |
|                     | 评测           | Gold 建立顺序正确，Project Gold 与 Benchmark F1 分开报告                    |
| **L4 Decision**     | 统计口径         | 全部按 unique record\_id，无 feature\_id 重复计数                        |
|                     | 隔离合规         | pipeline\_test 不进入业务，scenario\_enrichment 不参与比例 / 排行 / 趋势       |
|                     | 趋势合规         | 满足 2 月窗口 / N≥30 / 连续 3 窗口条件才输出趋势                                |
|                     | 证据可溯         | 每个重要结论绑定 3-5 条证据，可回溯至 Raw                                       |
| **L5 Presentation** | 展示合规         | 不重新计算第四层指标，所有图表显示样本量 n                                          |
|                     | 警告可见         | LOW\_SUPPORT/INSUFFICIENT\_EVIDENCE/COMPARABILITY\_WARNING 显式展示 |
|                     | 追溯完整         | alert\_id→decision\_id→feature\_id→record\_id 全链路可追溯            |
|                     | Dashboard 分离 | 业务 Dashboard 与 Model Ops Dashboard 严格分离                         |
| **跨层**              | 数据血缘         | record\_id 全流程不变，6 个关键字段全程保留                                    |
|                     | 版本管理         | schema/clean/prompt/model/metric 版本全程记录，跨版本有警告                  |
|                     | 隐私保护         | 不公开非必要用户身份和可重新定位用户的信息                                           |



***

## 12. 核心原则总结



```
L1 Collection：来源可追溯、原文不修改、用途严格隔离、采样方法可解释、

\\\\\\\\\\\\\\\&#x20;             Raw不可覆盖、个人信息最小化

L2 Cleaning：确定性问题→Rule Engine；语义有效性→Cleaner；

\\\\\\\\\\\\\\\&#x20;           误删风险→Reviewer；真正冲突→Human

L3 Feature：固定Schema保证统计稳定 + Tagging Agent负责结构化抽取

\\\\\\\\\\\\\\\&#x20;          \\\\\\\\\\\\\\\\+ Audit Agent负责质量审核 + Embedding+KMeans发现Schema盲区

\\\\\\\\\\\\\\\&#x20;          \\\\\\\\\\\\\\\\+ Gold Dataset负责量化评测

L4 Decision：先保证统计口径正确，再讨论业务意义；

\\\\\\\\\\\\\\\&#x20;           先展示事实，再形成机会判断；

\\\\\\\\\\\\\\\&#x20;           所有指标由确定性代码计算，LLM不碰数值

L5 Presentation：展示事实，不重算事实；建议必须有证据；推送必须能回源
```

> **本方案为 Codex 直接部署执行的最终版。Codex 应严格按照第 10 节执行顺序清单逐步实现，每步完成后对照对应层级的验收标准验证，通过后再进入下一步。所有硬约束（数据隔离、record_id 血缘、版本管理、LLM 边界、证据追溯）为不可妥协项。**
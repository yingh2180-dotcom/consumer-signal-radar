# 消费者洞察 Demo 2.0

## 变更定位

- **正式版本目录**：GitHub `main` 根目录；开发审核分支为 `codex/v2-rebuild`
- **本次范围**：全新四页面前端、本机五层后端、1000 条合成样本、Supabase 五层存储草案、测试与截图
- **旧版关系**：`main` 是当前正式 2.0；1.0 由 `v1.0.0` 标签和 `release/1.x` 维护分支保留
- **数据身份**：全部为原创合成演示样本，真实业务样本为 0

## 1. 2.0 能看到什么

公开洞察台按“先看价值，再核对证据”的顺序呈现：

1. **总览与洞察**：产品、肤质、场景筛选；问题线索、正向反馈和研究候选。
2. **证据追溯**：从指标进入 feature_id、record_id 和高亮原文证据。
3. **方法与边界**：五层真实输入输出、Schema/证据/数量校验，以及未启用能力。
4. **内部运行台**：本机一键重跑、历史运行、人工 KEEP/FILTER 复核和 Supabase 同步状态。

数据库表、Secret 密钥和内部异常日志不放进普通访客页面。公开页面持续显示 `synthetic_demo`、`pipeline_test` 和 `business_count=0`。

## 2. 五层后端实际做什么

| 层 | 实际行为 | 当前输出 |
|---|---|---|
| L1 | 校验 1000 条输入、编号和演示隔离字段 | 不可变 Raw 与哈希 |
| L2 | 清洗空白/模板文本，保留原因与重复关系 | KEEP 960、FILTER 40 |
| L3 | 用原创固定规则抽取多观点与原文证据 | 980 条观点特征 |
| L4 | 按不同 record_id 去重，预计算 140 个切片 | 指标、证据绑定、研究候选 |
| L5 | 组装页面快照并执行质量检查 | 可追溯 Snapshot 与 QA |

本版为 `rules_demo / app 2.0 / schema demo-v1`。它证明工程流程闭环，不证明真实评论上的 AI 泛化能力。AI 模型、独立人工 Gold F1、聚类和真实时间趋势均未启用。

## 3. 文件位置

```text
consumer-signal-radar/
├─ frontend/          四页面 React 前端源码与独立依赖锁文件
├─ backend/           五层 Pipeline 与本机 API
├─ data/              合成样本、生成器、独立期望与验证报告
├─ supabase/          五层表结构、权限检查、同步适配器
├─ docs/              整体方案、当前进度与后续执行计划（MD + DOCX）
├─ design/            设计概念图
├─ outputs/           电脑/手机验收截图与浏览器检查
├─ runtime/           分运行存档、当前快照和验证报告
├─ tests/             端到端、接口与浏览器验收
├─ 启动MVP.cmd        双击启动入口
└─ launch.py          安全启动器，仅绑定 127.0.0.1:18523
```

## 4. 本机启动

首次克隆后先按 `requirements-2.0.txt` 创建根目录 `.venv`，再进入 `frontend` 安装依赖并执行生产构建。随后双击 `启动MVP.cmd`，访问 `http://127.0.0.1:18523`。

启动器只绑定本机回环地址，不会自动公开到互联网。它优先使用仓库根目录 `.venv`，也兼容旧的父目录虚拟环境。

## 5. 验证命令

在本目录运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\.venv\Scripts\python.exe -m unittest discover -s supabase/tests -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

首次从 GitHub 克隆后需在 `frontend/` 执行 `npm ci` 和 `npm run build`。生成的 `frontend/dist/` 属于本机构建产物，不提交到 GitHub；完成构建后，普通启动不再需要重新安装依赖。

## 6. Supabase 状态

本地五层映射 dry-run 已通过，记录见 `runtime/supabase_dry_run.json`。当前没有连接、建表或写入任何 Supabase 项目，也没有公开发布。真正接入需要用户指定项目、授权建表与写入，并按 `supabase/README.md` 先做权限检查。

## 7. 回退边界

1.0 固定基线为提交 `33f5ecfd5f8c5b576de05001e77f1ec77bae8188`、标签 `v1.0.0` 和分支 `release/1.x`。2.0 发布后可通过标签或维护分支读取、修复和恢复 1.0。

## 8. 交接文档

当前完成情况、所处阶段、前后端职责、后续五阶段操作步骤和 AI 接手约束，统一见：

- `docs/20_Demo_2.0当前完成情况与后续执行计划.md`
- `docs/20_Demo_2.0当前完成情况与后续执行计划.docx`

# Demo 2.0 数据与执行契约

状态：依据用户 2026-09-15 要求执行整体 MVP 工作流建立；云端目标/账号仍待提供。GitHub 的 2.0 源码位于仓库根目录和 `codex/v2-rebuild` 分支，1.0 由 `v1.0.0` 标签及 `release/1.x` 分支保留。

## 硬约束

- 输入 `data/synthetic_reviews.csv`，禁止读取 synthetic_expected.csv 作为规则或模型输入。
- 全部 data_kind=synthetic_demo、dataset_role=pipeline_test；context=demo，业务样本=0，target_product_id 为空。不得伪造平台、时间或真实产品绑定。
- 原文和编号永久保留；每次运行建立新 run_id。原始文件摘要存档，拒绝覆盖不同内容。
- 本版实际处理模式为 rules_demo；AI、人工Gold评测、聚类、趋势未启用。页面明确显示，不冒充 Agent、Embedding 或 F1。
- 13个演示类别：包装、成分、尺寸、服务、功效、价格、气味、使用体验、物流、新鲜度、真伪、整体、其他。无法识别观点时使用处理状态 NO_FEATURE，不伪造特征。
- 特征sentiment=positive/negative/neutral；必须有真实子串evidence。一记录允许多特征。filter动作=KEEP/FILTER/PENDING/ERROR，互斥穷尽。空白RULE_EMPTY、模板RULE_TEMPLATE可过滤；同文只标记duplicate_of，不自动删除。
- 指标按unique record_id。正/负可同时提及，分母为切片KEEP记录。少于3条不同记录LOW_SUPPORT，3条证据不足INSUFFICIENT_EVIDENCE。不得综合评分或growth。模式用固定模板输出研究候选，明确不是LLM建议。

## 文件和负责范围

- backend/：Python处理、FastAPI、本机审核与运行API、tests。处理产物放runtime/runs/<run_id>/，runtime不可公开。
- frontend/：React/Vite 四页面，以青绿浅色既有系统为基础。依赖通过本目录的 `package.json` 与 `package-lock.json` 独立安装，不读取 1.0 的依赖目录。
- supabase/：SQL预览、权限设计、云端同步适配器与测试。不能在无目标和授权时连接外部项目。
- frontend/public/snapshot.json：生成的合成演示快照；可公开但必须由后端构建，禁止手写假指标。

## 快照JSON：snapshot-v1

顶层：snapshot_id,run_id,generated_at,context='demo',mode='rules_demo',dataset_id,versions,summary,filter_options,records,stages,qa,warnings,slices。

summary：raw_count,kept_count,filtered_count,pending_count,error_count,feature_count,business_count=0。
versions：schema_version='demo-v1',clean_version='v1',prompt_version=null,model_identifier=null,metric_version='v1',generator_version='v1'。
filter_options：products['全部','演示产品 A','演示产品 B','演示产品 C'],skins['全部','干皮','油皮','混合皮','未说明'],scenes['全部','早间','晚间','出差','日常','初次尝试','未说明']。
slice键=product+'|'+skin+'|'+scene，所有支持组合预计算；每个slice={summary,metrics,record_ids,opportunities}。不支持的组合返回空结果/错误，不临时在浏览器聚合。
metrics每行={decision_id,product,category,sentiment,mention_count,sample_size,mention_rate(0..1),support_status,evidence_ids}；evidence_ids是feature_id列表，最多5条不同record_id的特征。
records每行保留全部raw字段，另加{clean_text,final_action,reason,duplicate_of,skin,scene,features}。features每项={feature_id,record_id,category,sentiment,evidence,audit_status='RULE_VALIDATED'}。
opportunities每项={decision_id,title,fact,pattern,hypothesis,recommendation,validation_action,evidence_ids,method='deterministic_template'}，只从符合证据支持的负向指标形成。
stages每项={layer,name,input_count,output_count,status,mode,duration_ms,artifact}；qa含counts_consistent,evidence_valid,schema_valid,raw_hash,business_count,model_evaluation_status='NOT_EVALUATED',trend_status='NO_REAL_TIMESTAMPS',clustering_status='NOT_ENABLED'。

## 本机API

- GET /api/health：模式、版本、是否有快照；不读取/返回凭据。
- GET /api/snapshot：返回完整快照，含预计算slices。
- POST /api/runs：只执行本批固定输入，不接受远程网址/路径/模型配置；后台运行，重复正在运行的请求返回当前任务；创建新不可变产物。
- GET /api/runs：近期运行状态，不含私密配置。
- POST /api/reviews：{record_id,action:'KEEP'|'FILTER',note}；append-only审核记录，审核后需新运行生成快照，不回写旧快照。
- GET /api/reviews：本机审核日志。
- API仅绑定127.0.0.1，写接口校验Origin/Host本机同源，不允许跨站修改或公网远程管理。
- 公网构建只读snapshot.json（或后续Supabase已发布快照）；静态模式隐藏运行/审核写操作并说明只读。前端请求本机/api/health确认可管理，否则静态模式。

## 验收

先写有意义的失败测试再实现：稳定编号、输入拒绝业务污染、计数一致、标签行不重复计数、证据子串、空白/模板留痕、同文保留、无时间无趋势、规则不冒充模型、不可变快照、审核作用域及同源写接口。

1.0 回退基线：提交 `33f5ecfd5f8c5b576de05001e77f1ec77bae8188`、标签 `v1.0.0`、分支 `release/1.x`。2.0 在 `codex/v2-rebuild` 审核后进入 `main`；不得删除或改写 1.0 标签及维护分支。只有经过分支、路径和运行服务核对后才执行回退。

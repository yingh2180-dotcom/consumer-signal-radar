# v1 接口合同与并行开发边界

## 变更定位
新建 production 正式实现目录；保留上级 Streamlit Demo 作为变更前基线，不修改上级代码。用户目标为个人面试作品，非团队 SaaS，不公网发布。

## 约定
- 前端 React/Vite，后端 FastAPI；API 路径统一 /api，JSON 错误 detail 文本；内部 ID 均为字符串 UUID。
- 单用户管理员，首次在本机配置 RADAR_ADMIN_PASSWORD，首次密码本机生成并写 .env（不得输出聊天）；登录 POST /api/auth/login {password}，cookie 会话；GET /api/auth/me {authenticated:true}；POST /api/auth/logout。
- 默认本地 SQLite 持久化，Docker 单实例持久卷，后台 worker 独立进程。单人面试版不引入未验证的多租户或数据库集群。
- GET /api/settings 返回 {model,embedding_model,configured,paid_enabled,max_rows}；密钥只取服务端 .env 环境，绝不返回。
- GET/POST /api/projects；POST {name,description?}；项目 {id,name,description,created_at}。
- POST /api/projects/{id}/imports/preview multipart file: CSV/XLSX；返回 {preview_id,columns,sheets,rows:[dict],total_rows}。可传 sheet 表单字段选择工作表。
- POST /api/projects/{id}/imports {preview_id,mapping:{text,brand?,product?,date?,platform?,source_url?,id?},source_name,data_kind}；返回批次 {id,name,row_count,quality,created_at,data_kind}。mapping 值为原始列名。
- GET /api/projects/{id}/imports -> 批次数组；POST /api/projects/{id}/demo 导入现有明确合成样本；GET /api/projects/{id}/reviews?batch_id=&q=&offset=0&limit=50 -> {items,total}。
- POST /api/projects/{id}/jobs {batch_ids:[str],mode:'offline'|'llm',clusters:8,consent:false}；GET /api/projects/{id}/jobs -> 数组；GET /api/jobs/{id}；POST /api/jobs/{id}/cancel；POST /api/jobs/{id}/retry。任务 {id,project_id,status,stage,processed,total,error,mode,created_at,updated_at}，status queued/running/succeeded/failed/cancelled。
- GET /api/jobs/{id}/result -> {reviews:[...],topics:[...],cards:[...],method,quality}。review 包含 id,text,brand,product,date,platform,source_url,data_kind,topic,sentiment,dimension,severity,need,scene,ingredients,cluster_name。
- card {id,topic,count,negative_rate,priority,score,growth,hypothesis,evidence:[{id,text,brand,product,date,platform,source_url}],reviewed:false}。
- PATCH /api/jobs/{id}/cards/{card_id} {hypothesis,reviewed}，必须证据至少三条规范化去重原文才可 reviewed=true，原文不可修改。
- POST /api/jobs/{id}/reports {title,draft:true|false} 保存不可变 JSON/Markdown 快照；正式报告只取 reviewed 卡；GET /api/projects/{id}/reports -> [{id,title,created_at,draft,job_id}]；GET /api/reports/{id} -> {id,title,markdown,...}；GET /api/reports/{id}/download。
- GET /api/jobs/{id}/export.csv；GET /api/jobs/{id}/annotation.csv 输出100条原文及空标签；POST /api/jobs/{id}/evaluate multipart file -> {scores:{field:number},count,supports:{field:{label:count}},qualified,note}。
- 前端所有导出走鉴权 URL；危险字符按文本展示；未配置模型时不能伪装AI成功；演示模式明显标注。

## 文件所有权
- 后端 agent：backend/server.py、backend/db.py、backend/worker.py、backend/test_server.py、backend/requirements.txt。不得修改 engine.py。
- 分析 agent：backend/engine.py、backend/test_engine.py、docs/DATA_EVALUATION.md。engine 接口见下。
- 前端 agent：frontend 内全部文件。
- 主 agent：部署、启动、配置、总文档、集成测试；冲突先消息协调。

## 分析引擎合同
backend/engine.py 提供 analyze_reviews(rows:list[dict], mode:str='offline', clusters:int=8, progress=None, checkpoint=None)->dict，返回 result 如上；progress(stage,processed,total) 可用于取消；checkpoint 可选 dict 用于保存抽取/向量结果（实现方式和后端协商）。提供 evaluate_reviews(rows,gold_rows)->{scores,count}。离线规范化去重包括移除合成场景后缀；不足3种独立文本不生成卡；真实LLM失败显式抛 ValueError。

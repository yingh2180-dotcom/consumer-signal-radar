# 变更定位

- **正式位置**：仓库根目录 `supabase/`
- **新增内容**：五层数据表草案、权限自检脚本、离线同步适配器
- **当前状态**：本地 dry-run 已通过；尚未连接或写入任何 Supabase 项目

# Supabase 在 Demo 中负责什么

Supabase 保存完整、可追溯的五层结果：

1. 原始合成样本与数据集身份；
2. 清洗动作、原因和人工复核动作；
3. 观点特征、证据原文及规则校验；
4. 分群指标、研究候选和证据绑定；
5. 质量报告、版本快照及已审核的公开副本。

浏览器只能读取 `public.published_demo_snapshots` 中 `approved=true` 的演示快照。原始记录、过程表和 Gold 参考区不向浏览器开放。服务端密钥只能保存在后端环境变量中，不能写进前端或 Git。

# 文件

- `schema_preview.sql`：一次性建表草案。它故意在重名对象存在时失败，避免误覆盖。
- `permission_checks.sql`：建表后执行的回滚式权限检查，不保留测试数据。
- `sync_adapter.py`：本地先校验全部五层，再按明确授权的项目地址同步；默认只 dry-run。
- `tests/test_adapter.py`：同步边界、不可变数据、证据关系和密钥保护测试。

# 已完成的本地验证

当前快照的 dry-run 结果保存在 `../runtime/supabase_dry_run.json`。验证覆盖：1 个数据集、1 次运行、1000 条 Raw、1000 条清洗结果、980 条特征、980 条特征校验、1840 条分群决策、5033 条证据绑定、1 份 QA 和 1 个快照。结果明确标记 `connected=false`、`public_write=false`、`gold_upload=false`。

# 真正接入时的受控步骤

1. 用户明确指定 Supabase 项目，并确认允许对该项目建表和写入。
2. 在该项目 SQL Editor 审阅并运行 `schema_preview.sql`。
3. 因适配器使用 Supabase REST Data API，需要在项目 **Data API → Exposed schemas** 中加入 `demo_private`。表权限仍只授予 `service_role`；不得向 `anon` 或 `authenticated` 授予私有表权限。
4. 运行 `permission_checks.sql`，确认私有表、Gold 区、公开快照和 Storage 策略符合预期。
5. 只在本机后端设置 `SUPABASE_URL` 与 `SUPABASE_SECRET_KEY`。`SUPABASE_SECRET_KEY` 必须是 `sb_secret_` 新式密钥；不要粘贴到聊天、前端或仓库。
6. 先再次 dry-run，再使用 `--execute --authorized-url https://<project-ref>.supabase.co` 写入私有五层数据。
7. 只有经过业务审核后，才额外使用 `--approve-publication` 创建公开副本。

官方安全依据：Supabase 的 Data API 需要同时使用数据库授权与 RLS；自定义 schema 必须明确配置为 exposed schema；Secret/Service Role 密钥只能放在后端。参考 [Securing your API](https://supabase.com/docs/guides/api/securing-your-api)、[Using Custom Schemas](https://supabase.com/docs/guides/api/using-custom-schemas) 和 [Securing your data](https://supabase.com/docs/guides/database/secure-data)。

# 当前未验证项

由于还没有用户指定并授权的 Supabase 项目，SQL 尚未在真实 Postgres 上执行，云端权限检查和实际同步也尚未发生。本目录中的 SQL 是可审阅草案，不应描述为“已部署”。

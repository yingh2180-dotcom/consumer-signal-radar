# 消费者洞察 GitHub 与飞书协作规范

## 变更定位

- **新增文档**：`docs/21_GitHub与飞书协作规范.md`
- **适用项目**：消费者洞察 Demo 1.0 / 2.0
- **GitHub 仓库**：`yingh2180-dotcom/consumer-signal-radar`
- **飞书固定位置**：`云盘 / 学习笔记 / 简历项目 / 项目二消费者洞察`
- **飞书项目链接**：<https://my.feishu.cn/drive/folder/GdsxfK8ryl257Wd9DlmcVvWtneg>

## 1. 版本结构

```text
main               当前正式主版本，2.0 审核通过后进入
release/1.x        1.0 维护分支
codex/v2-rebuild   2.0 重构审核分支
v1.0.0             1.0 固定版本标签
v2.0.0             2.0 正式发布后创建
```

1.0 与 2.0 代码结构不同，但属于同一产品的重大版本升级，因此共用一个仓库。旧版本通过标签和维护分支保留，不在 2.0 主分支中复制一套旧代码。

## 2. 文件职责

- GitHub 保存代码、测试、数据结构、正式 Markdown、版本标签和发布包。
- 飞书保存协作中的项目方案、当前完成情况、后续执行计划、聊天归档、评审评论和决策记录。
- 飞书文档通过评审后，由项目负责人把定稿内容同步到 GitHub Markdown；不得让两边同时各自形成不同的正式版本。

## 3. 飞书固定归档位置

以后本项目的讨论文档、计划文档和聊天归档统一放入：

```text
云盘 / 学习笔记 / 简历项目 / 项目二消费者洞察
```

当前优先归档：

1. [Demo 2.0 当前完成情况与后续执行计划](https://my.feishu.cn/docx/CdHEd9r86oAHPRxzyoFcalBgnlg)，已导入为飞书在线文档。
2. [2026-09-15-Codex-消费者洞察五层Demo](https://my.feishu.cn/docx/Fl2CdGSjUoS2JcxeXrncX21qnPb)，已按参考手册从 Markdown 导入为飞书在线文档。
3. [引用文档与附件](https://my.feishu.cn/drive/folder/TLKKfHca2l9UgFdHT8Lc6noqnOh)，保存聊天中使用和生成的正式材料。

## 4. 协作流程

1. 在飞书使用评论或修订模式讨论。
2. 由用户确认最终内容和页面版本。
3. 将确认后的内容同步回 GitHub。
4. 通过 Pull Request 审核代码和正式 Markdown。
5. 合并后创建版本标签和 GitHub Release。

## 5. 权限边界

- 飞书文件夹默认仅向明确协作者开放。
- 需要外部分享、公开链接或新增协作者时，先确认具体人员和权限档位。
- GitHub 密钥、Supabase Secret、数据库密码和模型密钥不得写入仓库、文档或聊天归档。

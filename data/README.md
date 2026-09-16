# 公开美妆数据参照与合成演示样本

## 变更定位

- 第 1 节：记录公开数据来源及本次许可核查结果。
- 第 2 节：提供独立合成样本及明确的使用边界。
- 第 3 节：说明字段、生成方法和验证结果。
- 本批数据已归档到 2.0 的 `data/`，没有修改旧应用、上传云端或部署网页。

## 1. 来源核查（2026-09-15）

### 首选参照：2019 之江杯电商评论观点挖掘

- [第三方参赛仓库](https://github.com/xmxoxo/Text-Opinion-Mining/tree/master/TRAIN)：化妆品评论及观点、属性类别、情感标签。品牌被匿名为 `**`，不可推定为珀莱雅。
- [评论文件](https://raw.githubusercontent.com/xmxoxo/Text-Opinion-Mining/master/TRAIN/Train_reviews.csv)与[标签文件](https://raw.githubusercontent.com/xmxoxo/Text-Opinion-Mining/master/TRAIN/Train_labels.csv)分别提供题目和答案。一条评论可能有多个标签，不能把标签行数当评论数。
- 已核实 GitHub 文件目录及数据说明；本目录不保存或再分发镜像评论。
- 没有核实到独立数据再分发许可。[天池官方数据说明](https://tianchi.aliyun.com/specials/promotion/about)不能替代具体数据协议。第三方镜像也不等于官方授权。
- 参照的分类包括包装、成分、尺寸、服务、功效、价格、气味、使用体验、物流、新鲜度、真伪、整体、其他；这些主题用于独立创作，不复制原始评论。

### 备选：Amazon Reviews 2023 美妆分类

- [研究团队发布的数据卡](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023)与[项目主页](https://amazon-reviews-2023.github.io/)提供英文评论、评分、时间戳和商品元数据。
- 官方数据卡提供 All_Beauty 和 Beauty_and_Personal_Care 分类。它不代表中国市场，不对应本项目三款产品。
- 本次没有核实独立再分发许可，不采用第三方上传者相互矛盾的 CC0/CC BY-SA 声明作为依据；暂不下载或公开原文。

### 备选：Sephora Products and Skincare Reviews

- [上传者的数据页面](https://www.kaggle.com/datasets/nadyinky/sephora-products-and-skincare-reviews)。本次可定位页面，但网页读取工具未返回正文，字段与许可未完成核实，暂不采用。

## 2. 本次生成的数据

`synthetic_reviews.csv` 含 1000 条独立合成测试记录。评论由固定种子、原创句段和显式测试场景组合生成，不复制公开评论、不调用外部模型，也不构成自然消费者采样。

公开数据与合成数据不是同一类：本批是“公开美妆分类启发的合成样本”，不是下载的真实评论、翻译评论或人工采集数据。不能声称本批证明业务结论、真实模型准确率、时间收益或消费者比例。

所有记录为 `dataset_role=pipeline_test`，`data_kind=synthetic_demo`；产品显示为演示产品 A/B/C，真实 `target_product_id` 留空。不得为了点亮珀莱雅图表，将这些记录改成 `business_core`，或将匿名评论强行绑定真实产品。

包含 20 条空白、20 条模板评价、20 条与指定样本完全同文的重复记录、20 条混合观点，其余为组合场景。重复原文使用不同记录编号，以验证“同文不自动等于同一记录”；预期动作为抽查提示，不构成人工 Gold。

没有混入 Gold；期望结果独立保存到 `synthetic_expected.csv`，不得进入 Agent 输入。这些期望结果只能用于工程测试，不能据此宣称独立人工评测 F1 达标。

## 3. 字段与复现

这是独立演示数据契约，不冒充方案中的平台采集 Raw Schema。`source_origin=synthetic_generated`、`collection_method=synthetic_demo` 是显式演示扩展；正式导入器必须识别演示模式，不能悄悄转换成平台采集来源。

保留 `record_id`、`dataset_role`、`source_platform`、`source_type`、`sampling_stratum`、`target_product_id` 以及原文和来源信息。平台、发布时间、采样层为空；缺少真实时间，所以不能用于真实时间趋势。生成日期为固定复现元数据，不是用户采集日期。

运行本目录 `generate.py` 可复现相同结果；`validation.json` 记录条数、唯一编号、隔离和文件摘要检查。生成器拒绝覆盖已存在的不同内容。

生成样本仅为流程输入准备。目前尚未执行五层分析、连接 Supabase 或发布网页。

# 前端实现与设计核对

## 变更定位

- 实现文件：`frontend/src/App.jsx`、`frontend/src/styles.css`、`frontend/src/data-model.js`
- 本机构建产物：`frontend/dist/`（由 `npm run build` 生成，不提交 GitHub）
- 验收截图：`outputs/dashboard-desktop.png`、`outputs/evidence-desktop.png`、`outputs/method-desktop.png`、`outputs/admin-desktop.png`、`outputs/dashboard-mobile.png`

## 第一性原理调整

设计概念图原本以四个功能页平行展开。2.0 实现进一步明确了主次：公开页面先证明洞察价值，再给出证据与方法；运行控制、人工复核和云端同步状态放进独立内部运行台。

## 与概念图一致的部分

1. 浅色分析工作台、深绿色侧栏和青绿色强调色。
2. 合成样本与规则演示身份持续可见。
3. 产品、肤质、场景三类筛选。
4. 指标、样本量、证据与研究候选分区。
5. 五层状态、质量说明和未启用能力明确展示。

## 实现阶段的改进

1. 首屏从“五层流程”调整为“先看洞察，再核对证据”。
2. 所有指标读取后端预计算的 140 个切片，浏览器不重新计算业务口径。
3. 增加指标 → feature_id → record_id → 高亮原文的可点击证据链。
4. 增加独立内部运行台，动态后端不可用时自动降级为只读快照。
5. 增加 390px 手机布局和固定底部导航。

浏览器验收使用本机已安装 Microsoft Edge 完成；应用内置浏览器当时不可用，因此使用 Playwright 驱动 Edge 作为等价自动化验证。

# Model API Configuration Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [x]) syntax for tracking.

**Goal:** 在登录后页面顶部增加可打开、缩小、还原和关闭的模型 API 配置面板。

**Architecture:** 新建独立 ModelConfigPanel React 组件，由 App 管理 closed、open、minimized 三态。组件只读取现有 GET /api/settings 返回的非敏感状态，不接收或保存 API Key；样式追加到现有 styles.css，并保留原设置页。

**Tech Stack:** React 18、Vite、lucide-react、现有 FastAPI settings 接口、原生 CSS。

## Global Constraints

- API Key 只在本机服务端环境变量中保存，前端不得读取、缓存或显示。
- 顶部入口在所有登录后页面可见。
- 面板必须支持关闭、缩小、还原和 Escape 关闭。
- 桌面端与 390 像素宽页面不得横向溢出。
- 不新增依赖，不改变模型调用、预算和后端接口。
- 模型状态完全来自 GET /api/settings。

---

### Task 1: ModelConfigPanel 组件

**Files:**
- Create: frontend/src/ModelConfigPanel.jsx

**Interfaces:**
- Consumes: settings 对象，包含 model、embedding_model、configured、paid_enabled、max_rows。
- Produces: ModelConfigLauncher 与 ModelConfigPanel；通过 view、setView 管理 closed、open、minimized。

- [x] **Step 1: 定义状态标签函数**

实现 configured 与 paid_enabled 到“待配置、已配置、已启用”的映射，并处理 settings 为空的“状态未知”。

- [x] **Step 2: 实现顶部入口**

入口显示 Cpu 图标、模型配置文字和状态点；点击后调用 setView('open')。

- [x] **Step 3: 实现完整面板**

面板展示文本模型、向量模型、配置状态、付费状态、20 元预算说明、必需与可选模型清单、本机配置步骤及阿里云官方链接。

- [x] **Step 4: 实现交互**

缩小按钮调用 setView('minimized')，关闭按钮调用 setView('closed')，遮罩与 Escape 关闭；缩小浮窗调用 setView('open')。

- [x] **Step 5: 做无障碍标记**

面板使用 role="dialog"、aria-modal、aria-labelledby；图标按钮带中文 aria-label。

---

### Task 2: 接入 App 与响应式样式

**Files:**
- Modify: frontend/src/App.jsx
- Modify: frontend/src/styles.css

**Interfaces:**
- Consumes: Task 1 导出的两个组件。
- Produces: 登录后全局可见入口和三态面板。

- [x] **Step 1: App 添加状态**

增加 modelPanelView，初始为 closed；退出登录时仍由页面卸载清除。

- [x] **Step 2: 顶部栏接入入口**

把当前项目选择器和模型配置入口放入 topbar-actions 容器，保持现有项目选择功能。

- [x] **Step 3: 页面根部挂载面板**

把 ModelConfigPanel 放到 App 根部，使所有登录后页面共享。

- [x] **Step 4: 添加桌面样式**

实现右侧固定面板、遮罩、模型清单、状态点、标题栏按钮和右下角缩小浮窗。

- [x] **Step 5: 添加移动端样式**

在 720 像素以下隐藏入口的辅助文字但保留图标和状态；面板宽度限制在视口内，浮窗避开底部导航。

---

### Task 3: 构建与浏览器验收

**Files:**
- Verify: frontend/src/ModelConfigPanel.jsx
- Verify: frontend/src/App.jsx
- Verify: frontend/src/styles.css

**Interfaces:**
- Consumes: 完成后的前端生产构建与本机服务。
- Produces: 可复核的构建结果和浏览器交互证据。

- [x] **Step 1: 运行生产构建**

Run: npm.cmd run build

Expected: Vite build 成功，dist 更新；允许保留已知的大分块警告。

- [x] **Step 2: 启动并检查页面**

Run: ..\\.venv\\Scripts\\python.exe launch.py

Expected: /api/health 返回 consumer-signal-radar。

- [x] **Step 3: 桌面交互验证**

登录后点击顶部模型配置，确认对话框出现；点击缩小出现右下角浮窗；点击浮窗恢复；Escape 和关闭按钮可关闭；原项目选择器仍可用。

- [x] **Step 4: 安全与内容验证**

确认 DOM 中没有真实 API Key；状态与 /api/settings 一致；官方链接指向阿里云帮助中心。

- [x] **Step 5: 移动端验证**

以 390×844 检查顶部入口、完整面板和缩小浮窗，无横向溢出且不遮挡底部导航。

- [x] **Step 6: 更新实施记录**

在本计划勾选实际完成项，并如实记录任何未验证内容。

## Self-review

- 规格中的入口、三态、模型清单、安全边界、错误状态、移动端和验证均有对应任务。
- 未使用 TBD、TODO 或未定义接口。
- 组件输入字段与当前 /api/settings 返回值一致。

# CodexUU

当前版本：`1.3.0`。

CodexUU 是一个面向 Windows 的高性能、本地优先 AI 编程控制台，采用 **Tauri 2 + Rust + React 19 + TypeScript + Tailwind CSS** 架构构建。

它统一聚合本机 **Codex** 与 **Antigravity** 双核心渠道用量，集中展示额度窗口、Token 用量拆分、API 等效价值、四列任务看板、趋势热力图、项目排行、Skill 与真实工具调用。数据完全在本地解析与计算，绝不上报代码正文、Transcript 提示词或敏感凭证。

> CodexUU 是独立开源项目，与 OpenAI、Anthropic、Google 及上游 codexU 无隶属关系。

---

## 核心功能与亮点

1. **双渠道与全部聚合**：
   - **Codex 官方**：接入 `codex app-server --stdio` 实时查询官方 5h/7d 额度，流式解析 `~/.codex` 本机会话、分支去重与真实工具调用。
   - **Antigravity**：接入 `~/.gemini/antigravity` 会话数据库与 Brain 轨迹，统计 Gemini 2.5/3.7 模型、子 Agent 轨迹与工具执行。
   - **全部聚合**：一站式合并本机两大 AI 助手的总 Token 消耗、每日热力图与等效估算。

2. **方案 C 双层/单层额度罗盘**：
   - 7D 紫色外环、5H 蓝色内环，已用从底向左增长、剩余从底向右增长；
   - 点击圆心即可无缝切换已用/剩余口径并即时同步；
   - 缺失 5H 窗口时自动收敛放大单环，不留空白与占位字符。

3. **四卡片 Token 精细拆分**：
   - 今日、本周、本月、累计 Token 指标；
   - 未缓存输入（蓝）、缓存输入（紫）、输出（橙）三色比例横条与具体数值。

4. **今日任务四列看板**：
   - 按项目聚合，分为 **进行中**、**待处理**、**定时任务**、**已完成** 四列；
   - 包含项目名、线程数、渠道标识与最近活跃时间。

5. **用量趋势与 0 基线图表**：
   - 方案 B 日期范围条与自然日热力图；
   - 0 基线连续平滑折线图，支持 Token / API 等效价值 ($) 切换；
   - 官方单价精确匹配估算；未知或网关别名模型标明未计价，并显示覆盖率。

6. **项目用量排行与导出**：
   - 真实有效目录用量榜单与相对占比条；
   - 支持一键导出 JSON、CSV 与 Markdown 格式文件；
   - 右侧实时活动概览（活跃数、Top 1/Top 3 集中度）。

7. **Skill 与真实工具调用**：
   - 统计显式 `function_call` / `tool_call` 与 Skill 加载，按物理调用次数记录。

8. **Windows 原生集成**：
   - 单实例互斥防重开；
   - 系统托盘动态图标与一键唤醒菜单；
   - 5 种桌面悬浮窗形态（极简圆环、状态胶囊、双轨卡片、信息圆盘、双环仪表），支持 20%~300% 任意平滑缩放与拖拽定位；
   - 原生全局快捷键（默认 `Ctrl+U`）。

---

## 技术架构

```text
CodexUU (Windows x64)
├─ Tauri 2 (Native Windows Shell, Tray, Global Shortcut, Multi-Window)
├─ Rust Backend Engine (Core Data & Business Logic Owner)
│  ├─ Providers (Codex stdio/JSONL, Antigravity SQLite/Brain)
│  ├─ Engine (Pricing Catalog, Aggregator, Timezone Safe Periods)
│  └─ Storage (Settings Migration & Diagnostic Bundle)
└─ React 19 Frontend (Modern Responsive UI)
   ├─ TypeScript + Tailwind CSS
   ├─ TopNav Segmented Channel Switcher
   ├─ Scheme C Quota Compass & Metric Cards
   └─ TaskBoard, Trends, Projects, Skills & Settings
```

---

## 本地开发与测试

```powershell
# 1. 安装前端依赖
pnpm install

# 2. 运行 Tauri 测试版（推荐，不生成 EXE/MSI/NSIS）
pnpm tauri dev --config src-tauri/tauri.dev.conf.json
# 或
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1

# 3. 仅运行前端开发服务器
pnpm dev

# 4. 运行前端 Vitest 测试
pnpm test

# 5. 运行 Rust 后端测试
cd src-tauri
cargo test
```

测试版运行时，设置中心的“数据源诊断”会显示实际扫描路径、文件/会话计数、最近成功时间与错误码；首次运行未发现会话时，主界面会给出明确提示。缓存、历史摘要和设置写入 `%APPDATA%/CodexUU`，不会上传会话正文。

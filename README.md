# CodexUU

当前预览版本：`0.2.02`。版本从 `0.0.1` 起步，每段累计 10 轮后进一位：`0.0.10` 的下一版为 `0.1.01`，`0.1.10` 的下一版为 `0.2.01`。每完成一轮可验收的代码更新都必须同步更新 `VERSION`、README、`AGENTS.md` 和 `agents/changelog.md`。

CodexUU 是一个面向 Windows 的本机 Codex / Claude Code 用量仪表盘，参考 [shanggqm/codexU](https://github.com/shanggqm/codexU) 的信息架构重新实现。

它读取本机 Codex 与 Claude Code 数据，集中展示额度窗口、Token 用量、API 等效价值、任务、趋势、项目排行、Skill 与工具调用。数据默认只在本机处理，不上传线程内容、项目路径或使用记录。

> CodexUU 是非官方项目，与 OpenAI、Anthropic 及上游 codexU 无隶属关系。

## 当前功能

- Codex 5 小时 / 7 天额度窗口，缺失窗口按需隐藏，不伪造占位额度。
- 额度支持“剩余 / 已用”口径切换，并使用相反的环形进度方向表达。
- 今日、本周、本月、累计 Token，细分未缓存输入、缓存输入和输出。
- 按日志实际模型和公开单价估算 API 等效价值，未知模型显示计价覆盖率。
- 今日项目看板：将同一 Runtime、同一项目的今日线程聚合为一张卡，展示进行中、待处理、定时和完成项目，避免按对话重复计数。
- 每日、每周、每月、累计趋势；每日视图包含半年 Token 活动热力图。
- 用量趋势内提供“概览 / 模型”二级视图，按真实日志中的模型与推理强度组合统计 Token、会话、回合、时间趋势和计价覆盖；日志未提供强度时明确显示“未提供”。
- 项目用量排行与项目活动概览，支持本周、本月、累计口径。
- 点击项目可查看模型拆分、会话列表、筛选，并导出当前项目的 JSON / CSV 或复制 Markdown 摘要。
- Skill 使用与明确工具调用事件统计。
- Codex / Claude Code 数据源在设置页切换。
- 自动、浅色、深色主题和中英文界面。
- Windows 原生全局快捷键、主窗口置顶、关闭行为配置。
- Windows 11 动态托盘额度环与详细状态 tooltip；通知区图标会按当前 Runtime 和额度已用/剩余口径更新，单击直接恢复主窗口。
- 桌面状态悬浮窗：默认显示当前 Runtime 的可验证额度状态；提供信息圆盘、5h/7d 双环仪表、极简圆环、状态胶囊和双轨卡片五种样式。已用从底部沿左侧增长，剩余从顶部沿右侧增长；缺失窗口按需退化，支持小/中/大尺寸、主题同步、拖动和右键设置。单击额度中心切换口径并同步主页面，单击其他区域恢复主窗口。
- 轻量模式默认开启：主窗口只隐藏 Windows 任务栏入口，仍保留标准最小化 / 最大化 / 关闭标题栏按钮，并可通过通知区、全局快捷键和桌面状态窗唤回。
- 顶部今日 / 本周 / 本月 / 累计卡片可点击，直接跳转到对应口径的 Token 趋势；羊毛进度使用稳定的分段进度条，不运行额外高光循环动画。
- 可配置低额度提醒阈值；每个 5h / 7d 窗口在同一重置周期内只提示一次。
- GitHub Release 自动检查、手动检查、Release 页面和 Windows 安装包下载入口。
- 数据源诊断：Codex app-server、SQLite、session 精细事件和 Claude transcript。
- Claude transcript 增量索引：首次扫描后只重建变化文件；索引仅保存 Token、模型、工具和 Skill 等派生统计，不复制对话正文。
- 设置页提供本机索引维护：只清除可自动重建的派生索引及其 SQLite 辅助文件，原始日志不会被删除。
- 统计时区支持跟随系统、UTC 和固定 IANA 时区。
- 刷新防重复执行，并提供刷新中、完成和失败反馈。

## 数据来源与口径

| 数据 | 来源 |
|---|---|
| Codex 额度 | 可执行的独立 CLI 优先调用 `codex app-server`；Windows Store 桌面版受进程启动限制时，读取最新 session 中官方写入的 `rate_limit` 快照（最多检查最近 32 个、14 天内的 rollout 文件） |
| 累计 Token | `~/.codex/state_5.sqlite` 或新版 `~/.codex/sqlite/state_5.sqlite` 线程索引 |
| Token 拆分与趋势 | `~/.codex/sessions/**/rollout-*.jsonl`、`archived_sessions` 中的 `token_count` |
| 模型与推理强度 | Codex rollout 的 `turn_context` / `thread_settings_applied` 与后续 `token_count` 增量关联；Claude 索引使用消息模型字段且不虚构推理强度 |
| 今日任务 | Codex SQLite 线程、启用中的 automation 与 Claude task |
| 项目排行 | session 中的工作目录与精细 Token 增量，只保留仍存在的真实项目目录 |
| Skill 数据 | 明确的 Skill 加载，以及关联的 `function_call`、`custom_tool_call` 或对应 Runtime 显式事件 |
| Claude Code | `~/.claude/projects/**/*.jsonl`、tasks 与可选 statusline snapshot |

Claude Code 的本机索引位于 `~/.codexU/analytics.sqlite`。它只保存文件指纹和可统计字段（时间、模型、Token、工具、Skill），不保存消息正文、提示词或项目文件内容；删除该文件只会触发下次读取时重建索引，不会影响原始日志。

“本周”固定按所选统计时区的周一 00:00 到周日 23:59 计算。所有累计、趋势和项目数字均为本机记录，不代表跨设备账号活动页统计。

任务看板先按 Runtime 与项目名聚合，再决定项目状态：“进行中”优先于“待处理 / 定时 / 完成”，所以同一项目既有已归档线程又有活跃线程时只显示为进行中；只有本期项目线程都落入完成口径时才显示为完成。Codex 的完成来源仍是今天明确归档，模型停止输出不算完成；“定时”仅统计本机 `~/.codex/automations` 中当前启用的任务。

## 运行要求

- Windows 10/11
- Python 3.11 或更高版本
- 本机至少运行过一次 Codex；Claude Code 数据为可选

## 本地运行

```powershell
git clone https://github.com/CiaoBye/codexUU.git
cd codexUU
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

程序关闭主窗口后默认保留在系统托盘。默认全局快捷键为 `Ctrl+U`，可在设置中点击录制并修改；新组合键只有在 Windows 全局注册成功后才会保存。

Windows 11 的通知区不允许第三方应用像 macOS 菜单栏一样常驻任意文本，因此 CodexUU 使用动态额度环图标、悬停详情和点击浮窗提供等价状态。若图标被收入 `^` 隐藏区，可在“设置 > 个性化 > 任务栏 > 其他系统托盘图标”中固定 CodexUU。

轻量模式下，托盘单击、全局快捷键和桌面悬浮窗非中心区域单击都会恢复并前置主窗口；主窗口从最小化状态恢复时会同时调用 Qt 与 Windows 原生窗口恢复路径。

## 设置说明

- 通用：语言、Runtime、更新偏好、全局快捷键、置顶、桌面悬浮窗样式与尺寸、轻量模式和关闭行为。内容超出可用高度时会在 Tab 内滚动，底部保存操作始终可见。
- 外观：主题、额度已用/剩余口径、减少动态效果。
- 系统：GitHub 更新、统计时区和数据源诊断。

更新检查访问本仓库公开的 GitHub Releases API。若 Release 附带 `.msi`、`.exe` 或 Windows `.zip`，设置页会启用“下载更新”；应用不会静默安装。

自动数据刷新固定为 60 秒，并使用 Windows/Qt 粗粒度定时器与刷新互斥。该周期优先控制 session 扫描和托盘重绘成本；手动刷新按钮仍可立即更新，但主界面不常驻显示自动刷新状态。设置页的语言、主题、Runtime、提醒阈值、快捷键和窗口行为均采用“选择后保存”机制；下拉框忽略鼠标滚轮，避免误触修改；关闭含草稿修改的设置窗口会先请求确认。

## Windows 发布

日常开发只推送代码和标签，不会自动构建或发布 Release。只有在 GitHub Actions 中手动运行 `Windows Release` 工作流时才会构建；仅构建时会保留 14 天的安装包与 SHA-256 Artifact，明确填写 Release 标签后才发布安装包。工作流使用 PyInstaller 打包应用、使用 Inno Setup 生成当前用户范围的 Windows 安装器，并在发布时附带 `.exe` 与 SHA-256 校验文件。可在 Windows 本机执行：

```powershell
python -m pip install pyinstaller
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -Installer
```

## 开发与验证

```powershell
python -m compileall -q app main.py
$env:PYTHONPATH='.'
python -m pytest -q
powershell -ExecutionPolicy Bypass -File scripts\restart.ps1
```

Qt 界面修改还应使用 `QT_QPA_PLATFORM=offscreen` 完成窗口、主题、Tab 和真实数据 smoke test。

## 已知边界

- Codex 本地额度接口只提供百分比与重置时间，不提供绝对配额。
- Codex App 账号活动页可能包含跨设备、云端任务及已清理历史，因此不会与本机统计完全一致。
- Claude Code 额度依赖可选本地 statusline snapshot；缺失时只展示可验证的本机历史用量。
- API 等效价值是按公开 API 单价计算的估算值，不代表实际账单或返现。

## 致谢

界面信息架构、额度窗口和本地优先思路参考了 [shanggqm/codexU](https://github.com/shanggqm/codexU)。CodexUU 针对 Windows、Qt 与本机数据源做了独立实现和扩展。

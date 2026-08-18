# CodexUU 1.0 Complete Rewrite Plan

> **Target stack:** Tauri 2 + React 19 + TypeScript + Rust  
> **Target platform for 1.0:** Windows 10/11 x64  
> **Document purpose:** This is the execution blueprint for Codex. It defines what to build, what to preserve, what to abandon, architecture boundaries, UI structure, migration gates, and release acceptance criteria.  
> **Baseline:** `CiaoBye/codexUU` legacy PySide6 preview `0.3.16` (2026-07-31).

![CodexUU 1.0 prototype](./CodexUU_1.0_Prototype.png)

---

## 0. Codex execution directive

### 0.1 Mission

Rebuild CodexUU as a stable, local-first Windows desktop application for monitoring and analyzing AI coding activity.

The new application must combine:

1. Official Codex quota windows and reset times.
2. Local Codex token, model, session, project, task, Skill, and tool-call analysis.
3. CC Switch current relay provider usage, request statistics, cost, and balance.
4. Windows tray, global shortcut, native notifications, and a compact floating status widget.
5. Clear source health, diagnostics, export, update, and migration behavior.

The rewrite is **not** a line-by-line port of the existing Python code and **not** a visual replica of `codexU`.

### 0.2 Hard constraints

Codex must follow these rules:

- Rust is the sole owner of business logic, data access, indexing, scheduling, credentials, and system integration.
- React must never read Codex files, CC Switch files, SQLite databases, API keys, or local paths directly.
- The frontend must not calculate token periods, project status, quota validity, pricing, or source freshness.
- Every data source must fail independently. A CC Switch balance failure must not block Codex usage updates.
- The application must be single-instance.
- The main window, tray popup, and floating widget must have separate capability scopes.
- No prompt body, model response body, tool arguments, source file contents, or raw credentials may be stored in CodexUU's database.
- The new app must use standard Semantic Versioning.
- The existing PySide6 release must remain recoverable through a Git tag and archive branch until 1.0 is stable.
- Do not add Claude, Gemini, OpenCode, Pi, Cursor, or other providers during the 1.0 rewrite.
- Do not optimize for macOS or Linux during 1.0; only avoid architecture choices that make future support impossible.
- Do not proceed to the next milestone until the current milestone acceptance gate passes.

### 0.3 Definition of complete

The rewrite is complete only when:

- New and legacy snapshots match on approved fixtures for retained metrics.
- The packaged Windows app runs without Python.
- The application remains in the tray after the main window closes.
- Reopening, hiding, minimizing, restarting, updating, and quitting do not create zombie processes or duplicate instances.
- Empty, degraded, stale, permission-denied, malformed-log, and unavailable-runtime states are all visible and testable.
- Real local data has been tested on Windows at 100%, 125%, 150%, and 200% display scaling.
- The release pipeline produces a versioned installer, portable build if retained, checksums, updater metadata, and signed updater artifacts.

---

# 1. Product decision

## 1.1 New product definition

**CodexUU is a Windows local AI coding activity and usage console.**

It helps a user answer:

- How much official Codex quota remains?
- When will each quota window reset?
- How many tokens were used today, this week, this month, and all time?
- Which models, projects, and sessions consumed that usage?
- What tasks are active, waiting, scheduled, or completed?
- Which Skills and tools were actually invoked?
- Which CC Switch relay is active, how much local traffic passed through it, and what balance remains?
- Are the underlying data sources healthy and fresh?

## 1.2 Competitive position

CodexUU should not compete with CodexBar on provider count.

Its differentiation is:

> **Deep local Codex analysis + Windows-native status access + CC Switch relay accounting.**

Provider breadth is postponed. Data depth, stability, explainability, and Windows usability are the priorities.

## 1.3 Primary users

- Heavy Codex CLI or Codex desktop users on Windows.
- Users who run Codex through CC Switch or third-party relay services.
- Users who want local project/session analysis without uploading transcripts.
- Vibe Coding users who need visible progress and cost context but do not want to inspect raw logs.

---

# 2. What to preserve, rewrite, and abandon

## 2.1 Preserve as product behavior

The following behaviors remain part of CodexUU 1.0:

### Official quota

- Dynamically render only quota windows actually returned by the source.
- Preserve actual reset times.
- Support used/remaining display modes.
- Do not invent placeholder quota percentages or reset times.
- Distinguish available, exhausted, stale, and unavailable states.
- Keep quota alerts once per reset cycle.

### Token accounting

- Today, this week, this month, and all-time totals.
- Uncached input, cached input, and output breakdown.
- Model attribution from actual local events.
- Reasoning-effort attribution only when logs explicitly provide it.
- Unknown models remain unpriced.
- Pricing coverage must be shown when API-equivalent value is displayed.
- “This week” is Monday 00:00 through Sunday 23:59 in the selected statistics timezone.
- Local records must never be presented as cloud account totals.

### Projects and sessions

- Only real, existing project directories are ranked.
- Project details include model split and session list.
- Project export supports JSON, CSV, and Markdown.
- Export must exclude transcript text, prompts, tool parameters, and project file contents.
- Task cards aggregate by runtime + project instead of counting every conversation separately.
- Status priority remains: running → pending → scheduled → completed.
- Completion remains based on explicit archive/completion evidence, not “model stopped outputting.”

### Skill and tool usage

- Count only explicit Skill load events.
- Count only explicit tool-call events.
- Do not infer usage from ordinary text mentions.
- Do not distribute tokens or money across tools by call count.

### CC Switch

- Read the current Codex provider.
- Read proxy request logs and daily rollups in read-only mode.
- Show provider name, request count, success/failure count, token usage, and local relay cost.
- Query provider balance through a constrained, declarative request definition.
- Keep relay balance/cost separate from official Codex quota and API-equivalent value.

### Windows behavior

- System tray.
- Global shortcut.
- Main-window always-on-top option.
- Close-to-tray option.
- Start-at-login option.
- Native notifications.
- A compact floating status widget.
- Update check and user-controlled installation.
- Data-source diagnostics.

## 2.2 Rewrite from scratch

The following must be reimplemented in Rust/React rather than copied structurally:

- Codex app-server supervisor.
- JSONL parser and incremental indexer.
- Local SQLite index.
- Period aggregation.
- Project/session/task derivation.
- Model pricing layer.
- CC Switch database reader.
- CC Switch balance request parser.
- Refresh scheduler.
- Source health model.
- Settings storage.
- Tray manager.
- Shortcut manager.
- Window lifecycle.
- Floating widget.
- Updater.
- Export pipeline.
- All UI components and layout.

Existing Python code may be used as a behavioral reference and fixture oracle during parity testing only.

## 2.3 Explicitly abandon

The rewrite must abandon the following:

### Architecture

- PySide6 and Python runtime in the packaged app.
- A Python sidecar as the permanent backend.
- Monolithic `DashboardWidget` ownership of data and UI.
- One refresh job that succeeds or fails as a whole.
- Fixed 60-second full refresh of all sources.
- Business calculations inside UI components.
- Direct database or file access from the frontend.
- Large global QSS strings as the design system.
- Scattered `ctypes` Win32 lifecycle fixes.

### Product and UI

- The claim that CodexUU is merely a Windows port of `codexU`.
- A fixed 1060×720 minimum window.
- Forced window aspect ratio.
- Four large tabs as the only information architecture.
- Theme and language toggles permanently occupying the top bar.
- The “GPT / all / relay” toggle presented without a clear data-scope model.
- Five equally supported floating-widget designs.
- Constant display of all metrics on the overview page.
- “羊毛进度” as a primary product concept or headline metric.
- Decorative animation that runs continuously.
- Screenshot-driven fixed dimensions.

### Data and security

- Interpreting arbitrary CC Switch JavaScript as executable configuration.
- Cross-domain balance requests without explicit user authorization.
- Logging full request URLs, authorization headers, API keys, or raw provider responses.
- Persisting raw rollout events after they have been reduced to approved metadata.
- Using modified time alone as a source of truth for parser freshness.
- Silent fallback that makes unreliable data look authoritative.

### Process

- The custom ten-round version progression such as `0.1.01`.
- Updating multiple version files manually.
- Mixing feature development and release publication in one step.
- Treating visual screenshots as sufficient acceptance evidence.
- Adding more providers before the Codex and CC Switch paths are stable.

---

# 3. Target technology stack

## 3.1 Desktop shell and backend

- Tauri 2.
- Rust stable, pinned by `rust-toolchain.toml`.
- Tokio for asynchronous tasks.
- Serde and `serde_json` for serialization.
- `rusqlite` with bundled SQLite unless build analysis proves system SQLite is preferable.
- `notify` for bounded filesystem watching.
- `reqwest` with Rustls for provider balance and update-related HTTP.
- `tracing`, `tracing-subscriber`, and rolling log files.
- `thiserror` for typed errors.
- `time` or `chrono` for timezone-safe timestamps.
- `tokio-util::sync::CancellationToken` for shutdown and task cancellation.
- Tauri plugins for single instance, global shortcut, notifications, store/window state where appropriate, updater, and opener.

## 3.2 Frontend

- React 19.
- TypeScript strict mode.
- Vite.
- Tailwind CSS 4.
- CSS variables as the source of design tokens.
- Radix primitives only where they reduce accessibility risk; avoid importing a full visual theme.
- Zustand only for local interaction/window state.
- TanStack Query only for paginated command queries and invalidation; do not mirror the entire Rust state graph in the frontend.
- ECharts for trends, heatmaps, and model stacks.
- TanStack Table for projects and sessions.
- i18next for Simplified Chinese and English.
- Vitest and Testing Library.
- Playwright for mock-mode UI flows and visual regression.

## 3.3 Type contract generation

- Rust structs are the canonical API contract.
- Derive Serde serialization and generate TypeScript definitions into `frontend/src/bindings/generated.ts`.
- Generated TypeScript files must not be edited manually.
- Use a single generator selected at scaffold time (`ts-rs` is the default recommendation).
- CI must fail when generated bindings are out of date.

## 3.4 Dependency rule

- Pin the Tauri CLI, Tauri Rust crate, and JavaScript API to compatible patch versions.
- Commit `Cargo.lock` and the chosen JavaScript package-manager lockfile.
- Do not use wildcard dependency versions.
- Do not adopt a package merely to save a small amount of code.
- Every nontrivial dependency must be listed in `docs/dependencies.md` with purpose and security surface.

---

# 4. Repository strategy

## 4.1 Branch and archive

Before changing production code:

1. Tag the current main branch:
   - `legacy-pyside-v0.3.16`
2. Create an archive branch:
   - `archive/pyside6`
3. Create the rewrite branch:
   - `rewrite/tauri`
4. Keep the current release downloadable until the Tauri beta passes migration and stability gates.

## 4.2 Proposed repository layout

```text
codexUU/
├─ Cargo.toml                       # Rust workspace
├─ Cargo.lock
├─ rust-toolchain.toml
├─ package.json                     # workspace scripts
├─ pnpm-lock.yaml
├─ VERSION                          # optional display mirror generated from Cargo package
├─ README.md
├─ LICENSE
├─ THIRD_PARTY_NOTICES.md
├─ AGENTS.md
│
├─ apps/
│  └─ desktop/
│     ├─ package.json
│     ├─ vite.config.ts
│     ├─ index.html
│     ├─ src/
│     │  ├─ app/
│     │  ├─ bindings/
│     │  ├─ components/
│     │  ├─ design-system/
│     │  ├─ features/
│     │  │  ├─ overview/
│     │  │  ├─ usage/
│     │  │  ├─ projects/
│     │  │  ├─ sessions/
│     │  │  ├─ skills-tools/
│     │  │  ├─ providers/
│     │  │  ├─ sources/
│     │  │  └─ settings/
│     │  ├─ windows/
│     │  │  ├─ main/
│     │  │  ├─ tray-popup/
│     │  │  └─ floating-widget/
│     │  ├─ mocks/
│     │  └─ tests/
│     │
│     └─ src-tauri/
│        ├─ tauri.conf.json
│        ├─ capabilities/
│        │  ├─ main.json
│        │  ├─ tray-popup.json
│        │  └─ floating-widget.json
│        ├─ icons/
│        ├─ src/
│        │  ├─ main.rs
│        │  ├─ app_state.rs
│        │  ├─ commands/
│        │  ├─ events/
│        │  ├─ windows/
│        │  └─ platform/
│        └─ build.rs
│
├─ crates/
│  ├─ domain/
│  ├─ core-engine/
│  ├─ codex-provider/
│  ├─ ccswitch-provider/
│  ├─ local-index/
│  ├─ pricing/
│  ├─ scheduler/
│  ├─ diagnostics/
│  ├─ export/
│  └─ windows-platform/
│
├─ fixtures/
│  ├─ codex/
│  ├─ ccswitch/
│  ├─ expected/
│  └─ privacy-audit/
│
├─ scripts/
│  ├─ bootstrap.ps1
│  ├─ dev.ps1
│  ├─ test.ps1
│  ├─ build.ps1
│  ├─ verify-package.ps1
│  └─ generate-bindings.ps1
│
├─ docs/
│  ├─ architecture.md
│  ├─ data-contract.md
│  ├─ privacy.md
│  ├─ source-semantics.md
│  ├─ design-system.md
│  ├─ migration.md
│  ├─ release.md
│  └─ dependencies.md
│
└─ .github/
   └─ workflows/
      ├─ ci.yml
      ├─ windows-build.yml
      └─ release.yml
```

## 4.3 Legacy source handling

During parity work, the Python implementation may be placed under `legacy/pyside6/` or accessed through the archive branch.

Before stable 1.0:

- Do not package legacy Python.
- Do not run Python at application startup.
- Remove the legacy folder from the active branch after all retained behavior has fixtures and parity tests.
- Keep the archive branch and tag permanently.

---

# 5. Runtime architecture

## 5.1 Process model

CodexUU 1.0 uses one application process:

```text
CodexUU.exe
├─ Tauri event loop
├─ Rust AppState
├─ background supervisors
│  ├─ Codex app-server supervisor
│  ├─ session indexer
│  ├─ CC Switch watcher
│  ├─ quota scheduler
│  ├─ balance scheduler
│  └─ updater scheduler
├─ local SQLite index
└─ WebView windows
   ├─ main
   ├─ tray-popup
   └─ floating-widget
```

No Python process and no permanent localhost HTTP server.

## 5.2 AppState

`AppState` owns long-lived services:

```rust
pub struct AppState {
    pub settings: Arc<SettingsService>,
    pub engine: Arc<CoreEngine>,
    pub index: Arc<LocalIndex>,
    pub codex: Arc<CodexProvider>,
    pub ccswitch: Arc<CcSwitchProvider>,
    pub scheduler: Arc<Scheduler>,
    pub diagnostics: Arc<DiagnosticsService>,
    pub windows: Arc<WindowCoordinator>,
    pub shutdown: CancellationToken,
}
```

Rules:

- Services are created once during application setup.
- All background tasks receive a child cancellation token.
- Shutdown first blocks new work, then cancels supervisors, flushes index writes, closes app-server, and finally exits the event loop.
- No Tauri command creates an unmanaged thread.

## 5.3 Single instance

A second launch must:

- Send its arguments to the existing instance.
- Restore and focus the main window.
- Never start a second indexer or app-server.
- Log a structured `second_instance` event without user data.

## 5.4 Window responsibilities

### Main window

May:

- Query dashboards, usage, projects, sessions, Skills/tools, providers, sources, and settings.
- Trigger bounded refresh.
- Export approved data.
- Open safe external links.

May not:

- Access arbitrary filesystem paths.
- Access secrets.
- Execute shell commands.
- Read databases directly.

### Tray popup

May:

- Read a compact status snapshot.
- Trigger refresh.
- Open main window/settings.
- Quit.

May not:

- Query session lists.
- Export.
- Change provider credentials.

### Floating widget

May:

- Read compact quota and today-token snapshot.
- Toggle used/remaining display.
- Open or hide main window.
- Open widget settings through the main app.

May not:

- Query project/session data.
- Execute network requests.
- Write files.

---

# 6. Domain model

## 6.1 Source health

```rust
pub enum SourceHealth {
    Available,
    Degraded,
    Stale,
    Unavailable,
    Disabled,
}

pub struct SourceState {
    pub id: SourceId,
    pub label: String,
    pub health: SourceHealth,
    pub last_attempt_at: Option<OffsetDateTime>,
    pub last_success_at: Option<OffsetDateTime>,
    pub data_timestamp: Option<OffsetDateTime>,
    pub next_retry_at: Option<OffsetDateTime>,
    pub error_code: Option<String>,
    pub user_message: Option<String>,
    pub technical_message: Option<String>,
    pub retryable: bool,
}
```

Requirements:

- `technical_message` must be scrubbed before crossing to the frontend.
- `Available` means the latest successful data is within the source's freshness budget.
- `Stale` means valid cached data exists but is older than the freshness budget.
- `Degraded` means partial data is available.
- `Unavailable` means there is no usable data.
- UI must never convert `Unavailable` to zero.

## 6.2 Snapshot envelope

```rust
pub struct SnapshotEnvelope<T> {
    pub revision: u64,
    pub generated_at: OffsetDateTime,
    pub timezone: String,
    pub source_states: Vec<SourceState>,
    pub data: T,
}
```

The revision increments after an accepted state change.

## 6.3 Quota

```rust
pub struct QuotaWindow {
    pub kind: QuotaKind,
    pub label: String,
    pub used_ratio: Option<f64>,
    pub remaining_ratio: Option<f64>,
    pub reset_at: Option<OffsetDateTime>,
    pub status: QuotaWindowStatus,
    pub source: QuotaSource,
    pub observed_at: OffsetDateTime,
}

pub enum QuotaKind {
    FiveHour,
    SevenDay,
    Monthly,
    Other { minutes: u64 },
}
```

Rules:

- Do not identify a quota solely by its position in a response.
- Use protocol window metadata when available.
- Missing ratio is not zero.
- Missing reset time is not fabricated.
- Unknown windows may be shown in detail but must not be mislabeled.

## 6.4 Token periods

```rust
pub struct TokenBreakdown {
    pub uncached_input: u64,
    pub cached_input: u64,
    pub output: u64,
}

pub struct TokenPeriods {
    pub today: TokenBreakdown,
    pub week: TokenBreakdown,
    pub month: TokenBreakdown,
    pub all_time: TokenBreakdown,
}
```

## 6.5 Model usage

```rust
pub struct ModelUsage {
    pub model_id: String,
    pub provider_family: Option<String>,
    pub reasoning_effort: Option<String>,
    pub tokens: TokenBreakdown,
    pub sessions: u64,
    pub turns: u64,
    pub first_seen_at: Option<OffsetDateTime>,
    pub last_seen_at: Option<OffsetDateTime>,
    pub pricing: PricingResult,
}
```

`PricingResult`:

- `Exact`
- `UnpricedUnknownModel`
- `UnpricedAlias`
- `UnpricedMissingBreakdown`
- `NotApplicable`

No nearest-model guessing.

## 6.6 Project and session

```rust
pub struct ProjectSummary {
    pub id: ProjectId,
    pub display_name: String,
    pub normalized_path_hash: String,
    pub path_display: Option<String>,
    pub tokens: TokenBreakdown,
    pub session_count: u64,
    pub last_active_at: OffsetDateTime,
    pub status: ProjectStatus,
}

pub struct SessionSummary {
    pub id: SessionId,
    pub project_id: Option<ProjectId>,
    pub title: Option<String>,
    pub model_ids: Vec<String>,
    pub tokens: TokenBreakdown,
    pub started_at: Option<OffsetDateTime>,
    pub last_active_at: Option<OffsetDateTime>,
    pub archived_at: Option<OffsetDateTime>,
    pub source_kind: SessionSourceKind,
}
```

Path privacy:

- Full paths stay inside Rust.
- UI receives a display path only when enabled by the user.
- Diagnostics and exports use a stable hash by default.
- User may choose to include the display path in an export.

## 6.7 Task status

```rust
pub enum ProjectTaskStatus {
    Running,
    Pending,
    Scheduled,
    Completed,
}
```

Priority:

1. Running.
2. Pending.
3. Scheduled.
4. Completed.

The status derivation must be documented in `docs/source-semantics.md` and covered by fixtures.

## 6.8 Relay provider

```rust
pub struct RelaySnapshot {
    pub provider_id: String,
    pub provider_name: String,
    pub plan_name: Option<String>,
    pub balance: Option<Balance>,
    pub request_count: u64,
    pub success_count: u64,
    pub failure_count: u64,
    pub tokens: TokenPeriods,
    pub current_month_cost_usd: Option<f64>,
    pub last_request_at: Option<OffsetDateTime>,
}
```

Relay metrics and official quota are separate domains.

---

# 7. Local index

## 7.1 Storage paths

Use standard Windows application directories:

```text
Settings:
%APPDATA%\CodexUU\settings.json

Index:
%LOCALAPPDATA%\CodexUU\data\codexuu.db

Logs:
%LOCALAPPDATA%\CodexUU\logs\

Cache:
%LOCALAPPDATA%\CodexUU\cache\

Crash-safe diagnostic bundle staging:
%LOCALAPPDATA%\CodexUU\diagnostics\
```

Do not store new mutable application state under `~/.codexU`.

## 7.2 Database mode

- CodexUU's own SQLite database uses WAL.
- One writer task serializes writes.
- Read queries use separate connections or a managed pool.
- Schema migrations are explicit, ordered, reversible where practical, and tested.
- Back up the database before a destructive migration.
- Derived index data may be rebuilt from source files.
- Source files are always opened read-only.

## 7.3 Proposed tables

```text
schema_migrations
app_meta
source_cursors
sessions
session_models
token_events_daily
tool_events
skill_events
projects
project_sessions
task_facts
quota_observations
relay_daily_usage
provider_balance_observations
pricing_catalog
source_errors
```

Avoid storing every raw JSONL record.

## 7.4 Cursor model

For each indexed file store:

- normalized path hash
- source kind
- file identity if available
- file size
- modified time
- last byte offset
- parser version
- last indexed event timestamp
- last successful scan
- content prefix/suffix fingerprint for replacement detection

Behavior:

- Appended file: parse only new bytes.
- Truncated or replaced file: invalidate and rescan that file.
- Unchanged file: do not parse.
- Malformed line: record bounded error, continue.
- Oversized line: skip and report degraded source.
- Deleted source: retain derived history unless user chooses rebuild/cleanup.

## 7.5 Privacy filtering during parse

The parser may read source lines in memory, but before persistence it must reduce events to approved fields.

Never persist:

- prompt text
- assistant text
- tool arguments
- tool output
- environment variable values
- file patch contents
- shell command contents
- API keys
- access tokens
- cookies

A privacy-audit test must scan the index and diagnostic bundle for fixture secrets.

---

# 8. Provider architecture

## 8.1 Provider trait

```rust
#[async_trait]
pub trait UsageProvider: Send + Sync {
    fn id(&self) -> ProviderId;
    fn capabilities(&self) -> ProviderCapabilities;

    async fn discover(
        &self,
        context: &DiscoveryContext,
    ) -> Result<DiscoveryResult, ProviderError>;

    async fn refresh(
        &self,
        request: RefreshRequest,
        context: &RefreshContext,
    ) -> ProviderRefreshResult;

    async fn health(&self) -> SourceState;

    async fn shutdown(&self);
}
```

## 8.2 Initial providers

Only:

- `CodexProvider`
- `CcSwitchProvider`

The provider interface must allow future additions, but no generic credential UI is required in 1.0.

## 8.3 CodexProvider responsibilities

- Discover Codex home.
- Discover native and supported runtime executables.
- Read official state SQLite in read-only mode.
- Index `sessions` and `archived_sessions`.
- Read automations.
- Supervise app-server.
- Produce quota, usage, model, project, session, task, Skill, and tool facts.
- Expose source states separately for:
  - app-server
  - state SQLite
  - sessions
  - archived sessions
  - automations

## 8.4 CC Switch provider responsibilities

- Discover `~/.cc-switch`.
- Open `cc-switch.db` read-only with query-only mode.
- Resolve current Codex provider.
- Read request logs and rollups incrementally.
- Produce relay usage.
- Resolve a declarative balance endpoint.
- Keep balance health separate from proxy-log health.

## 8.5 Declarative balance endpoint

Do not execute arbitrary script code.

Use an internal normalized structure:

```rust
pub struct BalanceEndpoint {
    pub method: HttpMethod,
    pub url: UrlTemplate,
    pub allowed_host: String,
    pub auth: AuthPlacement,
    pub headers: Vec<HeaderTemplate>,
    pub response_limit_bytes: usize,
    pub timeout_ms: u64,
    pub redirect_limit: u8,
    pub value_paths: BalanceValuePaths,
}
```

Rules:

- Default allowed host is the current provider base host.
- Cross-host requests require an explicit confirmation stored by provider ID + host.
- HTTP is rejected unless the user explicitly permits a local/private endpoint.
- Redirects cannot escape the allowed host without confirmation.
- Request and response bodies have strict size limits.
- Credentials never cross to the frontend.
- Logs show host and status code, not full sensitive URLs or headers.
- Parsed balance fields are stored; raw response is not persisted.

---

# 9. Codex app-server supervisor

## 9.1 State machine

```text
Stopped
  → Starting
  → Initializing
  → Ready
  → Disconnected
  → Backoff
  → Starting

Any state
  → ShuttingDown
  → Stopped
```

## 9.2 Requirements

- Only one supervised child process.
- Ignore Windows Store execution aliases that cannot serve stdio reliably.
- Use bounded stdout line size.
- Correlate request IDs.
- Keep unmatched notifications in a bounded channel.
- Per-request timeout.
- Automatic restart after disconnect.
- Exponential backoff with jitter and maximum delay.
- Reset backoff after sustained success.
- Cancel pending requests during shutdown.
- Do not repeatedly spawn the runtime on every dashboard refresh.
- Quota cache freshness is independent of token-index freshness.
- Diagnostics expose executable path in the UI only when “show local paths” is enabled.

## 9.3 Failure behavior

- If app-server fails, continue showing the latest valid quota as stale.
- Fall back to recent trustworthy session quota observations only if the source semantics approve it.
- Clearly label the fallback channel.
- Never transform “no data” into “quota exhausted.”

---

# 10. Scheduler and refresh model

## 10.1 Independent jobs

```text
Codex runtime health
Official quota
Session watcher/indexer
State SQLite refresh
Automation refresh
CC Switch log refresh
Provider balance refresh
Pricing catalog refresh
Update check
```

## 10.2 Suggested default cadence

Cadence is configuration, not UI logic:

- Quota: adaptive; fast after user activity, slower when idle.
- Session index: filesystem events plus bounded debounce; periodic reconciliation.
- State SQLite: on change event plus periodic reconciliation.
- CC Switch logs: database file event plus low-frequency reconciliation.
- Provider balance: respect configured provider interval, with a safe minimum and backoff.
- Pricing catalog: bundled catalog first; remote refresh no more than daily.
- Update check: startup delay plus periodic low-frequency check.

Do not expose sub-minute advanced cadence settings in 1.0.

## 10.3 Refresh scopes

The UI may request:

- `RefreshScope::VisiblePage`
- `RefreshScope::Quota`
- `RefreshScope::CodexLocal`
- `RefreshScope::Relay`
- `RefreshScope::All`

Manual refresh starts relevant jobs but does not cancel healthy unrelated data.

## 10.4 Concurrency

- Deduplicate refresh requests per source.
- A second request joins the in-flight task.
- Use cancellation tokens.
- Limit concurrent file parsing and HTTP calls.
- Database writes are serialized.
- UI receives progress only for work expected to be user-visible.

---

# 11. Tauri commands and events

## 11.1 Commands

```text
app_get_bootstrap()
dashboard_get_snapshot(scope)
usage_query(request)
projects_query(request)
project_get_detail(project_id, range)
sessions_query(request)
session_get_detail(session_id)
skills_tools_query(request)
providers_get_status()
sources_get_status()
source_refresh(source_id)
settings_get()
settings_update(patch)
export_project(request)
export_usage(request)
diagnostics_create_bundle(options)
window_show_main()
window_show_settings()
widget_set_display_mode(mode)
app_check_update()
app_install_update()
app_quit()
```

## 11.2 Events

```text
snapshot://overview-changed
source://state-changed
index://progress
quota://alert
settings://changed
widget://snapshot-changed
update://available
update://progress
app://fatal-error
```

## 11.3 Error envelope

```typescript
export type AppError = {
  code: string
  message: string
  retryable: boolean
  sourceId?: string
  correlationId: string
  details?: Record<string, string | number | boolean | null>
}
```

Rules:

- User-facing message is localized in the frontend from `code` where possible.
- `message` is safe fallback text.
- `details` may not contain secrets or transcript content.
- Every unexpected error receives a correlation ID and structured log event.

## 11.4 Snapshot versus query

- Overview and tray use compact complete snapshots.
- Projects, sessions, and model histories use paginated queries.
- Large arrays are never broadcast to every window.
- Chart queries specify date range, granularity, and scope.
- Frontend caches may be invalidated by revision, not by guessing freshness.

---

# 12. Frontend information architecture

## 12.1 Main navigation

Use a collapsible left rail:

1. Overview
2. Usage
3. Projects
4. Sessions
5. Skills & Tools
6. Providers
7. Data Sources
8. Settings

Default rail:

- 64 px collapsed.
- 216 px expanded.
- Remember user preference.
- Support keyboard navigation and tooltips.

## 12.2 Top bar

Keep only:

- current page title
- data scope selector
- date/range selector where relevant
- source freshness indicator
- refresh button
- command/search button
- settings entry when rail is collapsed

Move theme and language into Settings.

## 12.3 Data scope selector

Replace ambiguous toggles with a clear model:

```text
Scope:
- Codex official/local
- Current relay: <provider name>
- Combined local activity
```

Rules:

- Official quota remains in its own card and is never recomputed from relay data.
- “Combined” is allowed only for compatible local token activity.
- The UI must show which cards respond to the scope.
- Persist the last selected scope per page, not globally if that creates misleading pages.

## 12.4 Overview page

The overview page answers five questions:

1. What is my current quota state?
2. When is the next reset?
3. How much local activity occurred today?
4. Which project/task requires attention?
5. Are data sources healthy?

Layout:

```text
Row 1:
Quota card | Today activity | Current relay | Source health

Row 2:
30-day usage trend (wide) | Active tasks

Row 3:
Top projects | Recent sessions
```

Do not show all model details on Overview.

## 12.5 Usage page

Contains:

- period selector: day / week / month / all / custom
- metric selector: tokens / API-equivalent value
- token composition
- daily heatmap
- stacked model trend
- model ranking
- pricing coverage and unpriced-model explanation
- scope explanation

Rename “羊毛进度” to:

- Chinese: `API 等效价值`
- English: `API-equivalent value`

It is an analytical metric, not a progress game.

## 12.6 Projects page

- Search.
- Period selector.
- Sort by tokens, recent activity, sessions, or value.
- Table/list with project, status, tokens, sessions, models, and last activity.
- Project detail drawer or page.
- Export.
- Optional path display.

## 12.7 Sessions page

- Virtualized/paginated list.
- Filters: date, project, model, archived/active, runtime.
- Session detail contains metadata and token facts only.
- No transcript viewer in 1.0.
- Deep link only when a trustworthy local/session URI exists.

## 12.8 Skills & Tools page

Two sections:

- Explicit Skill loads.
- Explicit tool calls.

Metrics:

- count
- active days
- projects
- last used
- trend

Do not show estimated money per tool.

## 12.9 Providers page

1.0 providers:

- Codex.
- Current CC Switch relay.

Show:

- discovery status
- source channels
- current provider
- balance endpoint authorization
- local request usage
- last success/error
- refresh action

Do not implement a provider marketplace.

## 12.10 Data Sources page

A diagnostics-oriented page:

- Codex app-server
- Codex state SQLite
- sessions
- archived sessions
- automations
- CC Switch database
- CC Switch balance endpoint
- pricing catalog
- update service

Each row shows:

- health
- data freshness
- last success
- next retry
- safe error
- actions: refresh, reveal approved path, copy safe diagnostics

## 12.11 Settings

Sections:

### General

- language
- start at login
- close behavior
- global shortcut
- statistics timezone
- update channel
- telemetry: absent; explain that no analytics are collected

### Appearance

- system/light/dark
- density: comfortable/compact
- reduced motion
- number formatting
- used/remaining quota display

### Tray and widget

- tray click behavior
- tray visible metrics
- floating widget enabled
- widget style
- widget size
- always on top
- monitor and edge behavior

### Privacy

- show/hide project paths
- diagnostic bundle contents
- export path policy
- rebuild derived index
- clear derived cache

### Advanced

- Codex home override
- Codex executable override
- source limits
- logging level
- open logs
- migration status

---

# 13. Window designs

## 13.1 Main window

- Default content size: 1280×800.
- Minimum content size: 980×680.
- No fixed aspect ratio.
- Support maximize and arbitrary resize.
- At widths below 1120 px, summary cards reflow.
- At high DPI, rely on CSS logical pixels and WebView scaling.
- Persist size, position, and maximized state.
- Correct off-screen positions after monitor changes.

## 13.2 Tray popup

A compact 360–400 px wide frameless window:

- official quota windows
- reset countdown
- today tokens
- current relay/balance if available
- source freshness
- refresh
- open main
- settings
- quit

Behavior:

- Position near tray using Tauri positioner or Windows placement logic.
- Close on focus loss and Escape.
- Do not reopen from the same click event.
- Keyboard accessible.
- No charts heavier than a small sparkline.

## 13.3 Floating widget

Retain only three styles:

1. **Minimal Ring**
   - one or two quota rings
   - today token number
   - reset hint

2. **Status Capsule**
   - horizontal compact quota tracks
   - relay label
   - reset time

3. **Dual Track Card**
   - 5h and 7d tracks
   - today token and source freshness

Abandon two redundant legacy variants.

Widget rules:

- Small / medium / large.
- Used/remaining mode.
- Dragging with position persistence.
- Snap to screen edges optionally.
- Correct off-screen position.
- Reduced motion.
- Context menu for style/size/hide/open.
- No close/minimize buttons inside the visual.
- Click opens main window; an explicit small target may toggle used/remaining.
- Do not overload single/double-click timing with multiple unrelated actions.

---

# 14. Design system

## 14.1 Visual direction

CodexUU should feel:

- precise
- local
- calm
- technical
- trustworthy
- dense without being cramped

Avoid:

- gaming-dashboard styling
- excessive neon glow
- glass effects that reduce readability
- continuous animated particles
- giant decorative numbers without context

## 14.2 Core palette

Dark theme reference:

```css
:root {
  --bg-canvas: #0b0f14;
  --bg-elevated: #111821;
  --bg-card: #151e29;
  --bg-subtle: #192431;

  --border-default: #273443;
  --border-strong: #3a4a5d;

  --text-primary: #f3f6fa;
  --text-secondary: #a7b2c0;
  --text-muted: #778596;

  --accent-brand: #2c9f9b;
  --quota-5h: #4d9fff;
  --quota-7d: #8b75ff;
  --token-uncached: #4d9fff;
  --token-cached: #8b75ff;
  --token-output: #eca64c;

  --success: #39c98a;
  --warning: #e9b44c;
  --danger: #ef6b74;
  --info: #63a9ff;
}
```

Light theme must be designed independently, not produced by simply swapping background and text.

## 14.3 Typography

- UI: Segoe UI Variable on Windows, system fallback.
- Monospace metadata: Cascadia Mono or system monospace fallback.
- Numeric metrics use tabular numerals.
- Minimum normal body size: 13 px.
- Avoid 9–10 px essential text.
- Use weight and spacing before adding more colors.

## 14.4 Spacing and radii

- 4 px base unit.
- Common gaps: 8, 12, 16, 24.
- Main cards: 12 px radius.
- Compact controls: 8 px radius.
- Avoid nested cards with identical visual weight.

## 14.5 Motion

- Default interaction transitions: 120–180 ms.
- No infinite ambient animation.
- Charts may animate on first load only.
- Respect reduced-motion setting and OS preference.
- Data refresh must not restart every chart animation.

## 14.6 Accessibility

- Keyboard navigation for all actions.
- Visible focus states.
- Accessible names for icon buttons.
- No status communicated by color alone.
- Charts require textual summaries.
- Target WCAG AA contrast.
- Screen-reader labels for quota values and reset times.

---

# 15. Prototype specification

The companion prototype image `CodexUU_1.0_Prototype.png` shows:

- Main Overview window with collapsible rail.
- Four top status cards.
- Usage trend, task list, top projects, and recent sessions.
- Tray popup.
- Minimal ring floating widget.
- Source-health detail card.
- Dark theme using teal brand accent, blue 5h quota, purple 7d quota, and orange output tokens.

The prototype is directional, not a pixel-perfect implementation contract.

Implementation must preserve hierarchy and responsive behavior rather than copying every coordinate.

---

# 16. Settings and migration

## 16.1 New settings schema

Use a versioned settings structure:

```rust
pub struct AppSettings {
    pub schema_version: u32,
    pub general: GeneralSettings,
    pub appearance: AppearanceSettings,
    pub tray: TraySettings,
    pub widget: WidgetSettings,
    pub privacy: PrivacySettings,
    pub sources: SourceOverrides,
    pub updates: UpdateSettings,
}
```

Settings updates:

- Validate in Rust.
- Apply as an atomic patch.
- Write through a temporary file and atomic replace.
- Keep one previous backup.
- Emit `settings://changed`.

## 16.2 Legacy import

On first run:

1. Detect `~/.codexU/config.json`.
2. Show an import summary.
3. Import only approved preferences:
   - language
   - theme
   - quota display
   - timezone
   - shortcut
   - always on top
   - close behavior
   - alert threshold
   - widget preference when mapping is unambiguous
4. Do not import:
   - derived caches
   - stale runtime status
   - update state
   - legacy window coordinates without boundary validation
   - secrets
5. Write new settings.
6. Leave legacy files untouched.
7. Record migration version and outcome.
8. Allow “reset and re-import” only from Advanced settings.

## 16.3 Database migration

Do not migrate the old derived database.

Rebuild the new index from original Codex/CC Switch sources.

---

# 17. Privacy and security

## 17.1 Local-first guarantee

- No telemetry SDK.
- No analytics endpoint.
- No crash upload by default.
- Update checks only contact the configured release endpoint.
- Provider balance requests only run for enabled current relay configuration.
- Diagnostic bundle creation is explicit and previewable.

## 17.2 Tauri capabilities

Create separate capability files for each window.

The frontend should receive only the minimum commands required by that window.

Do not grant generic shell, filesystem, or HTTP permissions to the frontend.

## 17.3 Content Security Policy

- No remote scripts.
- No `eval`.
- Restrict `connect-src` because business HTTP occurs in Rust.
- Bundle fonts and assets locally unless licensing prevents it.
- Sanitize any Markdown rendered in the UI.
- External links open through the approved opener command.

## 17.4 Secrets

- Reuse CC Switch credentials from its own protected/local configuration only when required and approved.
- Do not duplicate API keys in CodexUU settings unless a future feature explicitly requires it.
- If CodexUU ever stores a secret, use Windows credential protection or Tauri Stronghold after a dedicated design review.
- Secrets never enter logs, events, generated bindings, or React state.

## 17.5 Diagnostic bundles

Default bundle contains:

- app version
- OS and architecture
- safe source states
- safe error codes
- parser version
- database schema version
- bounded recent logs
- configuration with sensitive fields removed

Optional fields require explicit selection:

- local paths
- hashed project identifiers
- source file metadata

Never include raw session files or database files.

---

# 18. Testing strategy

## 18.1 Fixture matrix

Create sanitized fixtures covering:

### Quota

- valid 5h + 7d
- only 7d
- only 5h
- monthly/unknown window
- exhausted with reset time
- exhausted without reset time
- missing rate-limit object
- stale fallback
- app-server unavailable
- app-server malformed response

### Sessions

- new and old Codex layouts
- active session
- archived session
- malformed JSON line
- oversized line
- file append
- file truncate
- file replacement
- duplicate event
- timestamp timezone boundary
- week/month boundary
- model switch within session
- missing reasoning effort
- explicit Skill load
- explicit tool call
- text mention that must not count
- deleted project
- temp/internal project
- multiple sessions in one project

### Tasks

- running + archived in same project
- pending only
- scheduled automation
- completed only
- ambiguous activity
- missing title

### CC Switch

- no directory
- no database
- database locked
- current provider from settings
- fallback current provider
- direct logs
- daily rollups
- more than read limit
- unknown schema
- balance success
- balance timeout
- invalid JSON
- cross-host request
- redirect escape
- missing balance fields
- secret value in fixture to verify scrubbing

## 18.2 Legacy parity

During rewrite, a fixture runner must produce:

```text
fixtures/expected/legacy-snapshot.json
fixtures/expected/rust-snapshot.json
```

Compare retained fields:

- quota classification
- reset times
- token periods
- token breakdown
- model totals
- pricing exactness
- project ranking
- session counts
- task status
- Skill counts
- tool counts
- relay totals

Differences require one of:

- Rust bug fix.
- Explicitly approved semantic improvement documented in `docs/source-semantics.md`.
- Legacy behavior marked abandoned in this document.

## 18.3 Rust tests

- Unit tests per parser and aggregator.
- Integration tests using temporary directories and SQLite fixtures.
- Concurrency tests for refresh deduplication.
- Cancellation/shutdown tests.
- Database migration tests.
- Property tests for bounded numeric parsing where valuable.
- Secret-scrubbing tests.
- No network in default test suite.

## 18.4 Frontend tests

- Component states: loading, empty, available, degraded, stale, unavailable.
- Keyboard navigation.
- Responsive layouts.
- Chinese and English text expansion.
- Reduced motion.
- High-contrast and theme snapshots.
- Mock-mode full-page flows.
- Visual regression at:
  - 980×680
  - 1280×800
  - 1600×1000

## 18.5 Packaged app smoke tests

On Windows CI or controlled machine:

- install
- launch
- verify single instance
- tray appears
- main window opens
- global shortcut restores
- close-to-tray works
- updater check does not crash
- quit removes process
- uninstall
- portable launch if portable is retained

---

# 19. Performance and reliability budgets

These are release targets, not marketing claims:

- Idle CPU after stabilization: target below 1% on a typical modern Windows machine.
- No periodic full rescan when source files are unchanged.
- Main window interactive after launch without waiting for complete historical indexing.
- First useful quota/status snapshot appears before full history aggregation.
- Tray-only memory target: below 100 MB where WebView/runtime conditions allow.
- Main-window memory target: below 180 MB with normal history.
- No unbounded channels, arrays, log files, or parser caches.
- Index database operations must not block the Tauri UI thread.
- A malformed source file must not crash the app.
- A failed provider balance request must not clear valid Codex data.
- Shutdown must complete without forcibly terminating managed threads/processes.
- Startup recovery must handle an interrupted database migration or index write.

Measure and record actual results in release notes; do not claim targets were met without evidence.

---

# 20. Logging and diagnostics

## 20.1 Structured logging

Fields:

- timestamp
- level
- target/module
- event name
- correlation ID
- source ID
- duration
- safe result code

Never log raw source lines.

## 20.2 Rotation

- Rolling daily or size-based logs.
- Bounded retained files.
- User can open log folder.
- Debug logging automatically expires or resets after a defined period.

## 20.3 User-visible diagnostics

Diagnostics page separates:

- user-actionable issue
- temporary retry
- unsupported schema
- permission problem
- invalid override
- internal bug

Copy-safe diagnostics must be one click.

---

# 21. Export

## 21.1 Export formats

- JSON
- CSV
- Markdown

Excel is postponed unless there is a concrete user requirement.

## 21.2 Export policy

Default excludes:

- full project path
- transcript content
- prompts
- responses
- tool parameters
- raw session IDs when not necessary

Every export includes:

- app version
- generated time
- timezone
- selected range
- selected scope
- local-record disclaimer
- pricing coverage when money is present

---

# 22. Updates and releases

## 22.1 Versioning

Use SemVer:

```text
1.0.0-alpha.1
1.0.0-alpha.2
1.0.0-beta.1
1.0.0-rc.1
1.0.0
```

Cargo package version is the single source of truth.

The frontend reads the version from Tauri at runtime.

## 22.2 Channels

- Alpha: rewrite testers; may reset derived index.
- Beta: settings migration stable; data schema migration supported.
- Stable: no known data-loss or lifecycle blockers.

## 22.3 CI

Every pull request:

```text
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test --workspace
pnpm lint
pnpm typecheck
pnpm test
pnpm build
generated bindings check
privacy fixture audit
```

## 22.4 Release workflow

Manual release dispatch:

1. Verify clean tagged commit.
2. Build optimized Tauri bundles.
3. Run packaged smoke tests.
4. Generate installer and optional portable build.
5. Generate SHA-256 files.
6. Generate signed updater artifacts and metadata.
7. Publish draft release.
8. Human verifies assets.
9. Promote release.

Do not automatically publish a release for every tag.

## 22.5 Code signing

- Updater artifacts must use Tauri updater signing from the first update-capable alpha.
- Windows Authenticode signing may be introduced when a certificate is available.
- UI must not instruct users to bypass security warnings without checksum verification.

---

# 23. Milestones and acceptance gates

No duration estimates are assigned. Execute sequentially.

## Milestone 0 — Freeze and specification

### Build

- Tag/archive legacy.
- Add this document to `docs/rewrite-plan.md`.
- Add license and third-party notices.
- Create sanitized fixtures.
- Document retained semantics.
- Establish SemVer.

### Gate

- Legacy app still builds from archive.
- Fixtures cover all retained features.
- Every legacy feature is classified as preserve, rewrite, postpone, or abandon.

## Milestone 1 — Tauri shell

### Build

- Rust workspace.
- React/Vite/Tailwind frontend.
- Tauri main window.
- single instance.
- tray.
- global shortcut.
- window persistence.
- settings skeleton.
- mock-data mode.
- CI.

### Gate

- Packaged app installs and launches.
- One instance only.
- Main window and tray lifecycle are stable.
- No Python dependency.
- Mock Overview renders at required window sizes and scaling.

## Milestone 2 — Local index foundation

### Build

- database migrations.
- source cursors.
- JSONL incremental reader.
- privacy reducer.
- session/project/token facts.
- reconciliation scan.
- progress events.

### Gate

- Append/truncate/replace fixtures pass.
- Index contains no secret fixture strings.
- Reopening the app does not duplicate totals.
- No-change refresh performs no full parse.

## Milestone 3 — Codex provider

### Build

- state SQLite reader.
- app-server supervisor.
- quota model.
- automations.
- model/reasoning attribution.
- tasks.
- Skills/tools.
- pricing.

### Gate

- Legacy parity for approved Codex fixtures.
- Runtime disconnect/restart tests pass.
- Quota fallback is explicit.
- Every source has independent health.

## Milestone 4 — CC Switch provider

### Build

- database discovery.
- current provider.
- incremental usage aggregation.
- declarative balance endpoint.
- host authorization.
- relay UI data contract.

### Gate

- Relay failures never clear Codex data.
- Cross-host requests require approval.
- Secret audit passes.
- Legacy relay totals match fixtures or documented corrections.

## Milestone 5 — Main product UI

### Build

- Overview.
- Usage.
- Projects.
- Sessions.
- Skills & Tools.
- Providers.
- Data Sources.
- Settings.
- exports.
- Chinese/English.
- theme and reduced motion.

### Gate

- All source states render.
- Responsive and scaling tests pass.
- No business calculations in React.
- Accessibility keyboard pass.
- Visual regression approved.

## Milestone 6 — Tray and floating widget

### Build

- tray popup.
- dynamic tray icon.
- native notifications.
- three widget styles.
- edge correction.
- widget settings.

### Gate

- focus-loss behavior works.
- repeated tray clicks do not reopen incorrectly.
- widget never becomes permanently off-screen.
- shortcut/tray/widget restore exactly one main window.
- no timing-dependent single/double-click ambiguity.

## Milestone 7 — Migration and updater

### Build

- legacy settings import.
- updater signing.
- release channel.
- diagnostic bundle.
- installer/portable packaging decision.
- rollback documentation.

### Gate

- old settings remain untouched.
- import is repeatable and visible.
- updater verifies signature.
- packaged smoke tests pass.
- uninstall leaves user source data untouched.

## Milestone 8 — Beta stabilization

### Build

- real-data testing.
- performance measurements.
- schema drift handling.
- crash/lifecycle audit.
- documentation.
- user-facing migration notes.

### Gate

- no blocker in startup, shutdown, refresh, tray, updater, or migration.
- no known token double-counting.
- performance results recorded.
- privacy audit complete.
- support/diagnostic workflow usable.

## Milestone 9 — Stable 1.0

### Build

- final branding and repository description.
- stable release.
- archive legacy download.
- post-release rollback plan.

### Gate

- all previous gates remain green.
- final signed updater metadata published.
- known limitations documented.
- no unfinished provider placeholders visible in UI.

---

# 24. Postponed features

Do not include in 1.0 unless separately approved:

- Claude Code.
- Gemini CLI.
- OpenCode.
- Pi.
- Cursor.
- Multi-account provider vault.
- Cloud sync.
- Remote dashboard.
- Mobile companion.
- Team analytics.
- Prompt/transcript viewer.
- AI leadership score.
- Provider marketplace.
- Arbitrary user scripts.
- Plugin SDK exposed to third parties.
- Excel export.
- macOS/Linux installers.
- Custom user-installable themes.
- More than three floating widget designs.

Architecture may prepare extension points, but UI must not advertise unfinished items.

---

# 25. Repository and documentation changes

## README must say

- CodexUU is an independent Windows local AI coding activity and usage console.
- It analyzes local Codex records and optional CC Switch relay records.
- It is not affiliated with OpenAI, Anthropic, CodexBar, codexU, or CC Switch.
- Data is processed locally.
- Local totals may differ from cloud account activity.
- API-equivalent value is an estimate, not a bill or cashback.

## Required files

- `LICENSE`
- `THIRD_PARTY_NOTICES.md`
- `SECURITY.md`
- `PRIVACY.md`
- `CONTRIBUTING.md`
- `docs/source-semantics.md`
- `docs/diagnostics.md`
- `docs/migration.md`

## Repository description

Recommended:

> Windows local console for Codex quota, token, project, session, Skill, tool, and CC Switch relay analytics.

---

# 26. Initial Codex task prompt

Copy the following to Codex when starting implementation:

```text
You are rebuilding CiaoBye/codexUU according to docs/rewrite-plan.md.

First execute Milestone 0 only.

Rules:
1. Do not modify behavior or start the Tauri implementation until the legacy baseline is tagged/archived and fixtures exist.
2. Inspect the current repository, README, AGENTS.md, changelog, data readers, settings, tray, floating widget, tests, and release workflow.
3. Produce a feature inventory mapping every current capability to preserve, rewrite, postpone, or abandon.
4. Create sanitized fixture inputs and expected outputs for quota, token, models, projects, sessions, tasks, Skills, tools, and CC Switch.
5. Add standard SemVer planning, LICENSE, THIRD_PARTY_NOTICES, SECURITY, and privacy documentation.
6. Do not include raw user transcripts, prompts, paths, API keys, or real databases in fixtures.
7. Report every ambiguity instead of silently choosing a new semantic.
8. Run all existing tests and record the baseline.
9. End with a Milestone 0 acceptance report. Do not proceed to Milestone 1 automatically.
```

After Milestone 0 is approved, use:

```text
Proceed with the next milestone in docs/rewrite-plan.md only.

Before coding:
- restate the milestone gate;
- identify files to create/change;
- identify data/security risks;
- confirm which legacy behavior is being preserved.

During coding:
- keep Rust as the business-logic owner;
- keep frontend free of local file/database/credential access;
- add tests for every source state;
- do not add unrelated features or providers.

After coding:
- run the complete required checks;
- produce an acceptance report against every gate item;
- stop before the next milestone.
```

---

# 27. Prototype implementation notes for Codex

When implementing the prototype:

- Start with mock snapshots and all source states.
- Do not connect real data until the main responsive layout and state components are accepted.
- Build reusable components:
  - `SourceBadge`
  - `QuotaRing`
  - `MetricCard`
  - `TokenComposition`
  - `ScopeSelector`
  - `FreshnessIndicator`
  - `EmptyState`
  - `DegradedState`
  - `ErrorCallout`
  - `ProjectRow`
  - `SessionRow`
  - `TaskCard`
- Do not hard-code pixel heights for data panels.
- Use CSS grid with container queries where appropriate.
- Keep chart configuration in feature modules, not global files.
- Create Storybook-like local routes or a component playground without adding Storybook unless necessary.
- Provide mock scenarios selectable through a development-only menu:
  - healthy
  - first run
  - indexing
  - single quota
  - exhausted quota
  - stale runtime
  - relay failed
  - empty history
  - large history

---

# 28. Final decision summary

## Build

- Tauri 2 shell.
- React 19 + TypeScript UI.
- Rust-only business and data engine.
- Incremental local SQLite index.
- Independent Codex and CC Switch providers.
- Supervised Codex app-server.
- Responsive main dashboard.
- Tray popup.
- Three floating widgets.
- Explicit diagnostics, migration, privacy, and updater.

## Keep

- Deep Codex local analytics.
- Official quota semantics.
- Project/session/task/Skill/tool analysis.
- Exact model pricing behavior.
- CC Switch relay accounting.
- Windows tray and status access.
- Local-first privacy.

## Abandon

- PySide6/Python packaged runtime.
- Fixed-size screenshot UI.
- Monolithic refresh and dashboard.
- Five widget variants.
- “羊毛进度” as headline.
- Arbitrary balance scripts.
- Custom version numbering.
- “codexU Windows port” positioning.
- Provider expansion during rewrite.

## Success criterion

CodexUU 1.0 should feel like a stable Windows product whose UI can be replaced without risking the data engine, and whose data engine can refresh or degrade without destabilizing the UI.

---

# 29. Official technical references

- [Tauri 2 System Tray](https://v2.tauri.app/learn/system-tray/)
- [Tauri Global Shortcut Plugin](https://v2.tauri.app/plugin/global-shortcut/)
- [Tauri Single Instance Plugin](https://v2.tauri.app/plugin/single-instance/)
- [Tauri Capabilities](https://v2.tauri.app/security/capabilities/)
- [Tauri Plugins](https://v2.tauri.app/plugin/)
- [React versions](https://react.dev/versions)
- [React 19](https://react.dev/blog/2024/12/05/react-19)
- [Tailwind CSS v4](https://tailwindcss.com/blog/tailwindcss-v4)
- [Tailwind responsive design](https://tailwindcss.com/docs/responsive-design)
- [Current CodexUU repository](https://github.com/CiaoBye/codexUU)
- [codexU upstream reference](https://github.com/shanggqm/codexU)
- [Win-CodexBar reference](https://github.com/nesszer/Win-CodexBar)
- [Codex Usage Desktop reference](https://github.com/itvincent-git/codex-usage-desktop)

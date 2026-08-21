use std::collections::{HashMap, HashSet};
use std::fs::{self, File};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc::{channel, Receiver};
use std::thread;
use std::time::{Duration, SystemTime};

use chrono::{DateTime, Datelike, Utc};
use chrono_tz::Tz;
use serde_json::Value;

use crate::engine::pricing::PricingEngine;
use crate::models::{
    ModelUsage, ProjectRankingItem, ProviderData, QuotaSnapshot, SkillAgg,
    SkillUsageItem, TaskItem, TokenBreakdown, TokenPeriods,
};
use crate::providers::{
    backfill_daily, group_tasks_by_project, is_explicit_skill_event, is_explicit_tool_event,
    is_real_project_path,
};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

pub struct CodexProvider;

#[derive(Debug, Clone)]
struct ProjectAcc {
    path: String,
    tokens: TokenBreakdown,
    cost: f64,
    sessions: u64,
    last_active: DateTime<Tz>,
    primary_model: String,
    /// Per-model token totals used to choose the project primary model by
    /// actual token contribution rather than by session-level metadata.
    model_tokens: HashMap<String, u64>,
}

#[derive(Debug, Clone)]
struct ToolAcc {
    kind: String,
    count: u64,
    days: HashSet<String>,
    projects: HashSet<String>,
    last_used: DateTime<Tz>,
}

impl CodexProvider {
    pub fn source_roots() -> Vec<PathBuf> {
        let home = Self::get_codex_home();
        vec![home.join("sessions"), home.join("archived_sessions")]
    }

    fn normalize_model(value: Option<&str>) -> String {
        value
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .unwrap_or("unknown")
            .to_string()
    }

    pub fn get_codex_home() -> PathBuf {
        dirs::home_dir()
            .map(|h| h.join(".codex"))
            .unwrap_or_else(|| PathBuf::from(".codex"))
    }

    /// Recursively collect all .jsonl files in a directory
    fn collect_jsonl_recursive(dir: &Path, is_archived: bool, out: &mut Vec<(PathBuf, bool)>) {
        if let Ok(entries) = fs::read_dir(dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_dir() {
                    Self::collect_jsonl_recursive(&path, is_archived, out);
                } else if path.extension().and_then(|s| s.to_str()) == Some("jsonl") {
                    out.push((path, is_archived));
                }
            }
        }
    }

    fn session_thread_id(path: &Path) -> String {
        let fallback = path
            .file_stem()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();
        let Ok(file) = File::open(path) else {
            return fallback;
        };
        let mut id = fallback.clone();
        for line in BufReader::new(file).lines().map_while(Result::ok) {
            let Ok(value) = serde_json::from_str::<Value>(&line) else {
                continue;
            };
            let candidate = value
                .get("session_meta")
                .or_else(|| value.get("session"))
                .and_then(|meta| meta.get("thread_id").or_else(|| meta.get("id")))
                .or_else(|| value.get("thread_id"))
                .and_then(Value::as_str);
            if let Some(candidate) = candidate.filter(|candidate| !candidate.is_empty()) {
                id = candidate.to_string();
            }
        }
        id
    }

    fn select_unique_session_files(files: Vec<(PathBuf, bool)>) -> Vec<(PathBuf, bool)> {
        let mut selected: HashMap<String, (PathBuf, bool, SystemTime)> = HashMap::new();
        for (path, archived) in files {
            let id = Self::session_thread_id(&path);
            let modified = fs::metadata(&path)
                .and_then(|metadata| metadata.modified())
                .unwrap_or(SystemTime::UNIX_EPOCH);
            let replace = match selected.get(&id) {
                None => true,
                Some((_, existing_archived, existing_modified)) => {
                    (*existing_archived && !archived)
                        || (*existing_archived == archived && modified > *existing_modified)
                }
            };
            if replace {
                selected.insert(id, (path, archived, modified));
            }
        }
        selected
            .into_values()
            .map(|(path, archived, _)| (path, archived))
            .collect()
    }

    fn parse_ts(ts_str: &str, tz: &Tz) -> Option<DateTime<Tz>> {
        DateTime::parse_from_rfc3339(ts_str)
            .ok()
            .map(|dt| dt.with_timezone(tz))
    }

    /// Parse a timestamp value that may be an RFC3339 string, a numeric
    /// seconds value, or a numeric milliseconds value.
    fn parse_ts_value(value: &Value, tz: &Tz) -> Option<DateTime<Tz>> {
        let instant = match value {
            Value::String(text) => {
                let text = text.trim();
                if text.is_empty() {
                    return None;
                }
                if let Ok(parsed) = DateTime::parse_from_rfc3339(text) {
                    return Some(parsed.with_timezone(tz));
                }
                let number = text.parse::<i64>().ok()?;
                Self::numeric_to_datetime(number)?
            }
            Value::Number(number) => Self::numeric_to_datetime(number.as_i64()?)?,
            _ => return None,
        };
        Some(instant.with_timezone(tz))
    }

    fn numeric_to_datetime(value: i64) -> Option<DateTime<Utc>> {
        if value <= 0 {
            return None;
        }
        // 13-digit values are milliseconds; 10-digit values are seconds.
        if value >= 100_000_000_000 {
            DateTime::from_timestamp_millis(value)
        } else {
            DateTime::from_timestamp(value, 0)
        }
    }

    /// Account `tokens` toward a project's model and promote the model that
    /// contributes the most tokens as the project primary model.
    fn account_project_model(entry: &mut ProjectAcc, model_id: &str, tokens: u64) {
        let model_total = {
            let slot = entry.model_tokens.entry(model_id.to_string()).or_insert(0);
            *slot = slot.saturating_add(tokens);
            *slot
        };
        let primary_total = entry
            .model_tokens
            .get(&entry.primary_model)
            .copied()
            .unwrap_or(0);
        if model_total >= primary_total {
            entry.primary_model = model_id.to_string();
        }
    }

    /// Codex reports `reasoning_output_tokens` inside `output_tokens`. Adding
    /// them together double-counts reasoning.
    fn output_tokens_from_usage(usage: &Value) -> u64 {
        usage
            .get("output_tokens")
            .or_else(|| usage.get("output"))
            .and_then(Value::as_u64)
            .unwrap_or(0)
    }

    fn unavailable_quota(tz: &Tz, source: &str) -> QuotaSnapshot {
        QuotaSnapshot {
            status: "unavailable".to_string(),
            source: source.to_string(),
            last_updated: Utc::now()
                .with_timezone(tz)
                .format("%Y-%m-%d %H:%M:%S")
                .to_string(),
            ..Default::default()
        }
    }

    fn ratio(value: &Value) -> Option<f64> {
        let number = value.as_f64()?;
        let ratio = if number > 1.0 { number / 100.0 } else { number };
        (ratio.is_finite() && (0.0..=1.0).contains(&ratio)).then_some(ratio)
    }

    fn reset_at(value: &Value, tz: &Tz) -> Option<String> {
        if let Some(text) = value.as_str().filter(|text| !text.trim().is_empty()) {
            return Some(text.to_string());
        }
        let seconds = value.as_i64()?;
        DateTime::<Utc>::from_timestamp(seconds, 0)
            .map(|dt| dt.with_timezone(tz).format("%m/%d %H:%M").to_string())
    }

    fn parse_window(window: &Value, tz: &Tz) -> Option<(Option<f64>, Option<String>)> {
        let used = [
            "used_percent",
            "usedPercent",
            "used_ratio",
            "usedRatio",
            "utilization",
        ]
        .iter()
        .find_map(|key| window.get(*key).and_then(Self::ratio));
        let reset = ["resets_at", "resetsAt", "reset_at", "resetAt"]
            .iter()
            .find_map(|key| window.get(*key).and_then(|value| Self::reset_at(value, tz)));
        (used.is_some() || reset.is_some()).then_some((used, reset))
    }

    fn parse_rate_limits(value: &Value, tz: &Tz, source: &str) -> Option<QuotaSnapshot> {
        let rate_limits = value
            .get("rate_limits")
            .or_else(|| value.get("rateLimits"))
            .or_else(|| {
                value
                    .get("payload")
                    .and_then(|payload| payload.get("rate_limits"))
            })
            .or_else(|| {
                value
                    .get("payload")
                    .and_then(|payload| payload.get("rateLimits"))
            })
            .or_else(|| {
                value
                    .get("result")
                    .and_then(|result| result.get("rate_limits"))
            })
            .or_else(|| {
                value
                    .get("result")
                    .and_then(|result| result.get("rateLimits"))
            })
            .or_else(|| {
                value
                    .get("rateLimitsByLimitId")
                    .and_then(|v| v.get("codex"))
            })
            .or_else(|| {
                value
                    .get("result")
                    .and_then(|result| result.get("rateLimitsByLimitId"))
                    .and_then(|v| v.get("codex"))
            })?;

        let seven_day = rate_limits
            .get("seven_day")
            .or_else(|| rate_limits.get("sevenDay"))
            .or_else(|| rate_limits.get("primary"));
        let five_hour = rate_limits
            .get("five_hour")
            .or_else(|| rate_limits.get("fiveHour"))
            .or_else(|| rate_limits.get("secondary"));

        let seven = seven_day.and_then(|window| Self::parse_window(window, tz));
        let five = five_hour.and_then(|window| Self::parse_window(window, tz));
        if seven.is_none() && five.is_none() {
            return None;
        }

        let mut quota = QuotaSnapshot {
            status: "available".to_string(),
            source: source.to_string(),
            last_updated: Utc::now()
                .with_timezone(tz)
                .format("%Y-%m-%d %H:%M:%S")
                .to_string(),
            ..Default::default()
        };
        if let Some((used, reset)) = seven {
            quota.has_seven_day = true;
            quota.seven_day_used_ratio = used;
            quota.seven_day_remaining_ratio = used.map(|ratio| (1.0 - ratio).max(0.0));
            quota.seven_day_reset_at = reset;
        }
        if let Some((used, reset)) = five {
            quota.has_five_hour = true;
            quota.five_hour_used_ratio = used;
            quota.five_hour_remaining_ratio = used.map(|ratio| (1.0 - ratio).max(0.0));
            quota.five_hour_reset_at = reset;
        }
        Some(quota)
    }

    fn send_json_line<W: Write>(writer: &mut W, value: &Value) -> bool {
        serde_json::to_writer(&mut *writer, value).is_ok()
            && writer.write_all(b"\n").is_ok()
            && writer.flush().is_ok()
    }

    fn wait_for_response(receiver: &Receiver<Value>, id: u64) -> Option<Value> {
        let deadline = std::time::Instant::now() + Duration::from_secs(2);
        loop {
            let remaining = deadline.checked_duration_since(std::time::Instant::now())?;
            let value = receiver.recv_timeout(remaining).ok()?;
            if value.get("id").and_then(Value::as_u64) == Some(id) {
                return Some(value);
            }
        }
    }

    fn query_app_server(tz: &Tz) -> Option<QuotaSnapshot> {
        let home = Self::get_codex_home();
        let mut candidates = Vec::new();
        let bundled = home
            .join("plugins")
            .join(".plugin-appserver")
            .join("codex.exe");
        if bundled.is_file() {
            candidates.push(bundled);
        }
        candidates.push(PathBuf::from("codex"));

        for executable in candidates {
            let mut command = Command::new(executable);
            command
                .args(["app-server", "--stdio"])
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::null());
            #[cfg(windows)]
            command.creation_flags(0x08000000);

            let Ok(mut child) = command.spawn() else {
                continue;
            };
            let Some(mut stdin) = child.stdin.take() else {
                let _ = child.kill();
                continue;
            };
            let Some(stdout) = child.stdout.take() else {
                let _ = child.kill();
                continue;
            };
            let (sender, receiver) = channel::<Value>();
            thread::spawn(move || {
                for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                    if let Ok(value) = serde_json::from_str::<Value>(&line) {
                        if sender.send(value).is_err() {
                            break;
                        }
                    }
                }
            });

            let initialize = serde_json::json!({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"clientInfo": {"name": "codexuu", "version": env!("CARGO_PKG_VERSION")}}
            });
            if !Self::send_json_line(&mut stdin, &initialize)
                || Self::wait_for_response(&receiver, 1).is_none()
            {
                let _ = child.kill();
                continue;
            }
            let _ = Self::send_json_line(
                &mut stdin,
                &serde_json::json!({"jsonrpc":"2.0","method":"initialized","params":{}}),
            );
            let request = serde_json::json!({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "account/rateLimits/read",
                "params": {}
            });
            let response = if Self::send_json_line(&mut stdin, &request) {
                Self::wait_for_response(&receiver, 2)
            } else {
                None
            };
            let _ = child.kill();
            if let Some(response) = response {
                if let Some(quota) = Self::parse_rate_limits(&response, tz, "Codex app-server") {
                    return Some(quota);
                }
            }
        }
        None
    }

    /// Read real quota from app-server first, then an explicit local session
    /// snapshot. Missing fields remain unavailable; no fallback numbers are invented.
    pub fn fetch_quota(tz: &Tz) -> QuotaSnapshot {
        if let Some(quota) = Self::query_app_server(tz) {
            return quota;
        }

        let sessions_dir = Self::get_codex_home().join("sessions");
        let mut all_rollouts = Vec::new();
        Self::collect_jsonl_recursive(&sessions_dir, false, &mut all_rollouts);
        all_rollouts.sort_by(|a, b| {
            let meta_a = fs::metadata(&a.0).and_then(|m| m.modified()).ok();
            let meta_b = fs::metadata(&b.0).and_then(|m| m.modified()).ok();
            meta_b.cmp(&meta_a)
        });

        for (file_path, _) in all_rollouts.iter().take(32) {
            let Ok(file) = File::open(file_path) else {
                continue;
            };
            let mut explicit_empty = false;
            for line in BufReader::new(file).lines().map_while(Result::ok) {
                let Ok(value) = serde_json::from_str::<Value>(&line) else {
                    continue;
                };
                let rate_limits = value
                    .get("payload")
                    .and_then(|payload| {
                        payload
                            .get("rate_limits")
                            .or_else(|| payload.get("rateLimits"))
                    })
                    .or_else(|| value.get("rate_limits").or_else(|| value.get("rateLimits")));
                if let Some(rate_limits) = rate_limits {
                    if rate_limits.is_null() {
                        explicit_empty = true;
                        break;
                    }
                    if let Some(quota) =
                        Self::parse_rate_limits(&value, tz, "Codex session snapshot (fallback)")
                    {
                        return quota;
                    }
                }
            }
            if explicit_empty {
                break;
            }
        }
        Self::unavailable_quota(tz, "Codex app-server / session snapshot")
    }

    fn collect_automation_values(path: &Path, values: &mut Vec<Value>) {
        let Ok(content) = fs::read_to_string(path) else {
            return;
        };
        if path.extension().and_then(|ext| ext.to_str()) == Some("jsonl") {
            values.extend(
                content
                    .lines()
                    .filter_map(|line| serde_json::from_str::<Value>(line).ok()),
            );
            return;
        }
        let Ok(value) = serde_json::from_str::<Value>(&content) else {
            return;
        };
        if let Some(items) = value.get("tasks").and_then(Value::as_array) {
            values.extend(items.iter().cloned());
        } else if let Some(items) = value.get("automations").and_then(Value::as_array) {
            values.extend(items.iter().cloned());
        } else if let Some(items) = value.as_array() {
            values.extend(items.iter().cloned());
        } else {
            values.push(value);
        }
    }

    fn scheduled_tasks(tz: &Tz) -> Vec<TaskItem> {
        let automations_dir = Self::get_codex_home().join("automations");
        let Ok(entries) = fs::read_dir(automations_dir) else {
            return Vec::new();
        };
        let mut values = Vec::new();
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_file()
                && matches!(
                    path.extension().and_then(|ext| ext.to_str()),
                    Some("json") | Some("jsonl")
                )
            {
                Self::collect_automation_values(&path, &mut values);
            }
        }

        values
            .into_iter()
            .enumerate()
            .filter_map(|(index, value)| {
                let enabled = value
                    .get("enabled")
                    .or_else(|| value.get("is_enabled"))
                    .and_then(Value::as_bool)
                    .unwrap_or(true);
                if !enabled {
                    return None;
                }
                let id = value
                    .get("id")
                    .or_else(|| value.get("name"))
                    .and_then(Value::as_str)
                    .filter(|id| !id.is_empty())
                    .map(ToOwned::to_owned)
                    .unwrap_or_else(|| format!("scheduled-{index}"));
                let title = value
                    .get("title")
                    .or_else(|| value.get("summary"))
                    .or_else(|| value.get("prompt"))
                    .or_else(|| value.get("task"))
                    .and_then(Value::as_str)
                    .filter(|title| !title.trim().is_empty())
                    .map(|title| title.trim().chars().take(80).collect::<String>())
                    .unwrap_or_else(|| format!("定时任务 {id}"));
                let project_path = value
                    .get("cwd")
                    .or_else(|| value.get("project_path"))
                    .or_else(|| value.get("working_directory"))
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string();
                let updated_at = value
                    .get("next_run_at")
                    .or_else(|| value.get("nextRunAt"))
                    .or_else(|| value.get("schedule"))
                    .and_then(Value::as_str)
                    .and_then(|value| Self::parse_ts(value, tz))
                    .map(|value| value.format("%Y-%m-%d %H:%M").to_string())
                    .or_else(|| {
                        value
                            .get("next_run_at")
                            .or_else(|| value.get("nextRunAt"))
                            .and_then(Value::as_str)
                            .map(|value| value.to_string())
                    })
                    .unwrap_or_else(|| "—".to_string());
                let project_name = Path::new(&project_path)
                    .file_name()
                    .map(|name| name.to_string_lossy().to_string())
                    .filter(|name| !name.is_empty())
                    .unwrap_or_else(|| "定时任务".to_string());
                Some(TaskItem {
                    id: format!("automation-{id}"),
                    project_name,
                    project_path,
                    title,
                    status: "scheduled".to_string(),
                    updated_at,
                    thread_count: 1,
                    channel: "codex".to_string(),
                })
            })
            .collect()
    }

    pub fn parse_all_sessions(days_limit: usize, tz: &Tz) -> ProviderData {
        let home = Self::get_codex_home();
        let sessions_dir = home.join("sessions");
        let archived_dir = home.join("archived_sessions");

        let mut all_files = Vec::new();
        Self::collect_jsonl_recursive(&sessions_dir, false, &mut all_files);
        Self::collect_jsonl_recursive(&archived_dir, true, &mut all_files);
        let all_files = Self::select_unique_session_files(all_files);
        let scanned_files = all_files.len();

        let now = Utc::now().with_timezone(tz);
        let today_str = now.format("%Y-%m-%d").to_string();
        let current_week = now.iso_week();
        let current_month = now.format("%Y-%m").to_string();

        let mut total_periods = TokenPeriods::default();
        let mut daily_map: HashMap<String, (TokenBreakdown, f64, u64)> = HashMap::new();
        // Cost is accumulated per usage event so tiered request pricing is not
        // incorrectly re-evaluated against the model's aggregate token total.
        let mut model_map: HashMap<String, (TokenBreakdown, u64, u64, f64)> = HashMap::new();
        let mut project_map: HashMap<String, ProjectAcc> = HashMap::new();
        let mut tool_map: HashMap<String, ToolAcc> = HashMap::new();
        let mut tasks_map: HashMap<String, TaskItem> = HashMap::new();
        let mut parsed_files = 0usize;
        let mut read_errors = 0usize;
        let mut parse_errors = 0usize;

        for (file_path, is_archived) in all_files {
            let file = match File::open(&file_path) {
                Ok(file) => file,
                Err(_) => {
                    read_errors += 1;
                    continue;
                }
            };
            parsed_files += 1;
            let reader = BufReader::new(file);
            let mut session_project_path = String::new();
            let mut session_title = String::new();
            let mut session_primary_model = Self::normalize_model(None);
            let mut session_tokens = TokenBreakdown::default();
            let mut file_project_tokens = TokenBreakdown::default();
            // Anchor untimestamped sessions to the file's real modification
            // time so old sessions are never attributed to "now" (today).
            let mut session_last_active = fs::metadata(&file_path)
                .and_then(|metadata| metadata.modified())
                .ok()
                .map(|time| {
                    let dt: DateTime<Utc> = time.into();
                    dt.with_timezone(tz)
                })
                .unwrap_or(now);
            let mut thread_id = file_path
                .file_stem()
                .unwrap_or_default()
                .to_string_lossy()
                .to_string();

            let mut highest_uncached = 0u64;
            let mut highest_cached = 0u64;
            let mut highest_output = 0u64;

            for line_res in reader.lines() {
                let line = match line_res {
                    Ok(l) => l,
                    Err(_) => continue,
                };

                if line.is_empty() {
                    continue;
                }

                let val = match serde_json::from_str::<Value>(&line) {
                    Ok(val) => val,
                    Err(_) => {
                        parse_errors += 1;
                        continue;
                    }
                };
                let event_type = val.get("type").and_then(|s| s.as_str()).unwrap_or("");
                let payload = val.get("payload");

                // 1. Context & Metadata (turn_context or session_meta)
                if event_type == "turn_context" {
                    if let Some(p) = payload {
                        if let Some(cwd) = p.get("cwd").and_then(|s| s.as_str()) {
                            session_project_path = cwd.to_string();
                        }
                        if let Some(m) = p.get("model").and_then(|s| s.as_str()) {
                            session_primary_model = m.to_string();
                        }
                    }
                }

                if let Some(meta) = val.get("session_meta").or_else(|| val.get("session")) {
                    if let Some(p) = meta
                        .get("cwd")
                        .or_else(|| meta.get("project_path"))
                        .and_then(|s| s.as_str())
                    {
                        session_project_path = p.to_string();
                    }
                    if let Some(t) = meta
                        .get("title")
                        .or_else(|| meta.get("summary"))
                        .and_then(|s| s.as_str())
                    {
                        session_title = t.to_string();
                    }
                    if let Some(id) = meta
                        .get("thread_id")
                        .or_else(|| meta.get("id"))
                        .and_then(|s| s.as_str())
                    {
                        thread_id = id.to_string();
                    }
                }

                if let Some(model) = val
                    .get("model")
                    .or_else(|| val.get("model_name"))
                    .and_then(|s| s.as_str())
                {
                    session_primary_model = model.to_string();
                }

                // 2. Timestamp
                let mut event_dt = session_last_active;
                if let Some(ts_value) = val.get("timestamp").or_else(|| val.get("created_at")) {
                    if let Some(parsed) = Self::parse_ts_value(ts_value, tz) {
                        event_dt = parsed;
                        session_last_active = parsed;
                    }
                }

                // 3. Token counts extraction
                let mut token_usage_opt = None;
                let mut is_cumulative = false;

                if let Some(p) = payload {
                    if p.get("type").and_then(|s| s.as_str()) == Some("token_count") {
                        if let Some(info) = p.get("info") {
                            if let Some(tc) = info.get("total_token_usage") {
                                token_usage_opt = Some(tc);
                                is_cumulative = true;
                            } else if let Some(tc) = info.get("last_token_usage") {
                                token_usage_opt = Some(tc);
                            }
                        }
                    }
                }
                if token_usage_opt.is_none() {
                    if let Some(tc) = val.get("total_token_usage") {
                        token_usage_opt = Some(tc);
                        is_cumulative = true;
                    } else {
                        token_usage_opt = val.get("token_count").or_else(|| val.get("token_usage"));
                    }
                }

                if let Some(tc) = token_usage_opt {
                    let total_input = tc.get("input_tokens").and_then(|v| v.as_u64()).unwrap_or(0);
                    let cached = tc
                        .get("cached_input_tokens")
                        .or_else(|| tc.get("cached_tokens"))
                        .and_then(|v| v.as_u64())
                        .unwrap_or(0);
                    let uncached = total_input.saturating_sub(cached);
                    // Codex/OpenAI: output_tokens already includes reasoning_output_tokens.
                    let output = Self::output_tokens_from_usage(tc);

                    let (delta_uncached, delta_cached, delta_output) = if is_cumulative {
                        let du = uncached.saturating_sub(highest_uncached);
                        let dc = cached.saturating_sub(highest_cached);
                        let do_ = output.saturating_sub(highest_output);
                        highest_uncached = highest_uncached.max(uncached);
                        highest_cached = highest_cached.max(cached);
                        highest_output = highest_output.max(output);
                        (du, dc, do_)
                    } else {
                        (uncached, cached, output)
                    };

                    if delta_uncached + delta_cached + delta_output > 0 {
                        let delta = TokenBreakdown::new(delta_uncached, delta_cached, delta_output);
                        session_tokens.add(&delta);

                        // Attribution to model
                        let (cost, _) =
                            PricingEngine::calculate_cost(&session_primary_model, &delta);
                        let (model_entry, _sessions_cnt, turns_cnt, model_cost) = model_map
                            .entry(session_primary_model.clone())
                            .or_insert((TokenBreakdown::default(), 0, 0, 0.0));
                        model_entry.add(&delta);
                        *turns_cnt += 1;
                        *model_cost += cost;

                        // Daily aggregation
                        let date_key = event_dt.format("%Y-%m-%d").to_string();
                        let (daily_tb, daily_cost, _daily_sess) = daily_map
                            .entry(date_key.clone())
                            .or_insert((TokenBreakdown::default(), 0.0, 0));
                        daily_tb.add(&delta);
                        *daily_cost += cost;

                        // Period checks
                        if date_key == today_str {
                            total_periods.today.add(&delta);
                        }
                        if event_dt.iso_week() == current_week {
                            total_periods.week.add(&delta);
                        }
                        if event_dt.format("%Y-%m").to_string() == current_month {
                            total_periods.month.add(&delta);
                        }
                        total_periods.all_time.add(&delta);

                        // Project aggregation at event level so cost is priced per actual model.
                        if !session_project_path.is_empty() {
                            let entry = project_map
                                .entry(session_project_path.clone())
                                .or_insert_with(|| ProjectAcc {
                                    path: session_project_path.clone(),
                                    tokens: TokenBreakdown::default(),
                                    cost: 0.0,
                                    sessions: 0,
                                    last_active: event_dt,
                                    primary_model: session_primary_model.clone(),
                                    model_tokens: HashMap::new(),
                                });
                            entry.tokens.add(&delta);
                            entry.cost += cost;
                            Self::account_project_model(entry, &session_primary_model, delta.total);
                            file_project_tokens.add(&delta);
                            if event_dt > entry.last_active {
                                entry.last_active = event_dt;
                            }
                        }
                    }
                }

                // 4. Tool calls. Only explicit tool event records count;
                // metadata fields with a coincidental tool_name do not.
                let payload_type = payload
                    .and_then(|p| p.get("type"))
                    .and_then(Value::as_str)
                    .unwrap_or("");
                let explicit_tool_event = is_explicit_tool_event(&[event_type, payload_type]);
                let mut detected_tool = None;
                if explicit_tool_event {
                    if let Some(p) = payload {
                        if let Some(tool) = p
                            .get("tool_name")
                            .or_else(|| p.get("function_name"))
                            .or_else(|| p.get("name"))
                            .and_then(Value::as_str)
                        {
                            detected_tool = Some(tool.to_string());
                        }
                    }
                    if detected_tool.is_none() {
                        if let Some(tool) = val
                            .get("tool_name")
                            .or_else(|| val.get("function_name"))
                            .or_else(|| val.get("name"))
                            .and_then(Value::as_str)
                        {
                            detected_tool = Some(tool.to_string());
                        }
                    }
                }

                if let Some(tool_name) = detected_tool {
                    let date_k = event_dt.format("%Y-%m-%d").to_string();
                    let proj_k = if session_project_path.is_empty() {
                        "default".to_string()
                    } else {
                        session_project_path.clone()
                    };
                    let entry = tool_map
                        .entry(tool_name.clone())
                        .or_insert_with(|| ToolAcc {
                            kind: "tool".to_string(),
                            count: 0,
                            days: HashSet::new(),
                            projects: HashSet::new(),
                            last_used: event_dt,
                        });
                    entry.count += 1;
                    entry.days.insert(date_k);
                    entry.projects.insert(proj_k);
                    if event_dt > entry.last_used {
                        entry.last_used = event_dt;
                    }
                }

                // 5. Skill loads. Only explicit skill-load event types count.
                let explicit_skill_event = is_explicit_skill_event(&[event_type, payload_type]);
                if explicit_skill_event {
                    let skill_name = val
                        .get("skill_name")
                        .or_else(|| val.get("loaded_skill"))
                        .and_then(|s| s.as_str())
                        .or_else(|| {
                            payload.and_then(|p| {
                                p.get("skill_name")
                                    .or_else(|| p.get("loaded_skill"))
                                    .and_then(|s| s.as_str())
                            })
                        });
                    if let Some(skill_name) = skill_name {
                        let date_k = event_dt.format("%Y-%m-%d").to_string();
                        let proj_k = if session_project_path.is_empty() {
                            "default".to_string()
                        } else {
                            session_project_path.clone()
                        };
                        let entry =
                            tool_map
                                .entry(skill_name.to_string())
                                .or_insert_with(|| ToolAcc {
                                    kind: "skill".to_string(),
                                    count: 0,
                                    days: HashSet::new(),
                                    projects: HashSet::new(),
                                    last_used: event_dt,
                                });
                        entry.count += 1;
                        entry.days.insert(date_k);
                        entry.projects.insert(proj_k);
                        if event_dt > entry.last_used {
                            entry.last_used = event_dt;
                        }
                    }
                }
            }

            if let Some((_, sessions_cnt, _, _)) = model_map.get_mut(&session_primary_model) {
                *sessions_cnt += 1;
            }

            // Count a session against the day it was last active in.
            let session_date = session_last_active.format("%Y-%m-%d").to_string();
            let daily_entry = daily_map.entry(session_date.clone()).or_insert((
                TokenBreakdown::default(),
                0.0,
                0,
            ));
            daily_entry.2 += 1;

            // Project session count (tokens/cost are already added at event level).
            if !session_project_path.is_empty() {
                let entry = project_map
                    .entry(session_project_path.clone())
                    .or_insert_with(|| ProjectAcc {
                        path: session_project_path.clone(),
                        tokens: TokenBreakdown::default(),
                        cost: 0.0,
                        sessions: 0,
                        last_active: session_last_active,
                        primary_model: session_primary_model.clone(),
                        model_tokens: HashMap::new(),
                    });

                // Add any tokens that appeared before the project path was known.
                let remaining = TokenBreakdown::new(
                    session_tokens
                        .uncached_input
                        .saturating_sub(file_project_tokens.uncached_input),
                    session_tokens
                        .cached_input
                        .saturating_sub(file_project_tokens.cached_input),
                    session_tokens
                        .output
                        .saturating_sub(file_project_tokens.output),
                );
                if remaining.total > 0 {
                    entry.tokens.add(&remaining);
                    let (cost, _) =
                        PricingEngine::calculate_cost(&session_primary_model, &remaining);
                    entry.cost += cost;
                    Self::account_project_model(entry, &session_primary_model, remaining.total);
                }

                entry.sessions += 1;
                if session_last_active > entry.last_active {
                    entry.last_active = session_last_active;
                }
            }

            // Tasks Derivation (deduplicated by thread id)
            let status = if is_archived {
                "completed"
            } else {
                let elapsed_hours = (now - session_last_active).num_hours();
                if elapsed_hours <= 2 {
                    "running"
                } else if session_last_active.format("%Y-%m-%d").to_string() == today_str {
                    "pending"
                } else {
                    "completed"
                }
            };

            let title = if !session_title.is_empty() {
                session_title
            } else {
                format!("Session {}", thread_id.chars().take(8).collect::<String>())
            };

            let task = TaskItem {
                id: thread_id.clone(),
                project_name: if !session_project_path.is_empty() {
                    Path::new(&session_project_path)
                        .file_name()
                        .map(|s| s.to_string_lossy().to_string())
                        .unwrap_or_else(|| "未知项目".to_string())
                } else {
                    "未知项目".to_string()
                },
                project_path: session_project_path.clone(),
                channel: "codex".to_string(),
                status: status.to_string(),
                title,
                updated_at: session_last_active.format("%Y-%m-%d %H:%M").to_string(),
                thread_count: 1,
            };

            if let Some(existing) = tasks_map.get_mut(&thread_id) {
                existing.thread_count += 1;
                existing.status = task.status;
                existing.updated_at = task.updated_at;
                if !task.project_name.is_empty() && task.project_name != "未知项目" {
                    existing.project_name = task.project_name;
                    existing.project_path = task.project_path;
                }
            } else {
                tasks_map.insert(thread_id, task);
            }
        }

        let daily_activities = backfill_daily(daily_map, now, days_limit);

        // Model Usage List
        let mut models: Vec<ModelUsage> = model_map
            .into_iter()
            .map(|(model_id, (tokens, sessions, turns, cost_usd))| {
                let (_, status) = PricingEngine::calculate_cost(&model_id, &tokens);
                ModelUsage {
                    model_id,
                    reasoning_effort: None,
                    tokens,
                    cost_usd,
                    sessions,
                    turns,
                    pricing_status: status,
                }
            })
            .collect();
        models.sort_by_key(|m| std::cmp::Reverse(m.tokens.total));

        // Project Rankings: only real, still-existing directories.
        let mut projects: Vec<ProjectRankingItem> = project_map
            .into_iter()
            .filter(|(path, _)| is_real_project_path(path))
            .map(|(_, acc)| ProjectRankingItem {
                rank: 0,
                name: Path::new(&acc.path)
                    .file_name()
                    .map(|s| s.to_string_lossy().to_string())
                    .unwrap_or_else(|| acc.path.clone()),
                path: acc.path,
                tokens: acc.tokens,
                cost_usd: acc.cost,
                sessions: acc.sessions,
                last_active_at: acc.last_active.format("%Y-%m-%d %H:%M").to_string(),
                primary_model: acc.primary_model,
            })
            .collect();
        projects.sort_by_key(|p| std::cmp::Reverse(p.tokens.total));
        for (i, p) in projects.iter_mut().enumerate() {
            p.rank = i + 1;
        }

        // Skills and tools list
        let mut skill_details = HashMap::new();
        let mut skills_and_tools: Vec<SkillUsageItem> = tool_map
            .into_iter()
            .map(|(name, acc)| {
                skill_details.insert(
                    name.clone(),
                    SkillAgg {
                        kind: acc.kind.clone(),
                        count: acc.count,
                        active_days: acc.days.clone(),
                        project_paths: acc.projects.clone(),
                        last_used: acc.last_used.with_timezone(&Utc),
                    },
                );
                SkillUsageItem {
                    name,
                    kind: acc.kind,
                    count: acc.count,
                    active_days: acc.days.len() as u64,
                    project_count: acc.projects.len() as u64,
                    last_used_at: acc.last_used.format("%m/%d %H:%M").to_string(),
                }
            })
            .collect();
        skills_and_tools.sort_by_key(|s| std::cmp::Reverse(s.count));

        let mut tasks: Vec<TaskItem> = tasks_map.into_values().collect();
        let parsed_session_count = tasks.len();
        tasks.extend(Self::scheduled_tasks(tz));
        let session_count = tasks.len();
        tasks = group_tasks_by_project(tasks);

        let attempted_at = now.format("%Y-%m-%d %H:%M:%S").to_string();
        let source_exists = sessions_dir.is_dir() || archived_dir.is_dir();
        let status = if !source_exists {
            "unavailable"
        } else if scanned_files == 0 || parsed_files == 0 || read_errors > 0 || parse_errors > 0 {
            "degraded"
        } else {
            "healthy"
        };
        let message = if !source_exists {
            "未找到 Codex sessions 或 archived_sessions 数据目录".to_string()
        } else if scanned_files == 0 {
            "已找到 Codex 数据目录，但没有可读取的 rollout 文件".to_string()
        } else {
            format!(
                "扫描 {} 个唯一 rollout，解析 {} 个会话{}{}",
                scanned_files,
                parsed_session_count,
                if read_errors > 0 {
                    format!("，{} 个文件读取失败", read_errors)
                } else {
                    String::new()
                },
                if parse_errors > 0 {
                    format!("，{} 行 JSON 无法解析", parse_errors)
                } else {
                    String::new()
                }
            )
        };
        let source_health = crate::models::SourceHealthStatus {
            id: "codex_sessions".to_string(),
            name: "Codex 本机会话日志".to_string(),
            status: status.to_string(),
            message,
            last_success_at: (parsed_files > 0).then_some(attempted_at.clone()),
            last_attempt_at: Some(attempted_at),
            error_code: if read_errors > 0 {
                Some("file_read_failed".to_string())
            } else if parse_errors > 0 {
                Some("json_parse_failed".to_string())
            } else if !source_exists {
                Some("source_not_found".to_string())
            } else {
                None
            },
            source_schema: Some("Codex rollout JSONL".to_string()),
            locations: Self::source_roots()
                .iter()
                .map(|path| path.display().to_string())
                .collect(),
            capabilities: vec![
                "token_components".to_string(),
                "model_attribution".to_string(),
                "project_attribution".to_string(),
                "tool_events".to_string(),
                "skill_events".to_string(),
                "task_status".to_string(),
            ],
            scanned_files,
            parsed_sessions: parsed_session_count,
        };

        ProviderData {
            tokens: total_periods,
            daily_activities,
            models,
            tasks,
            projects,
            skills_and_tools,
            skill_details,
            session_count,
            source_health,
        }
    }

    }

#[cfg(test)]
mod tests {
    use super::CodexProvider;
    use chrono_tz::Asia::Shanghai;
    use serde_json::json;

    #[test]
    fn quota_parser_fails_closed_when_window_fields_are_missing() {
        assert!(CodexProvider::parse_window(&json!({}), &Shanghai).is_none());
        assert!(CodexProvider::parse_rate_limits(
            &json!({"rate_limits": {"primary": {}}}),
            &Shanghai,
            "test"
        )
        .is_none());
    }

    #[test]
    fn quota_parser_normalizes_percent_without_inventing_reset() {
        let quota = CodexProvider::parse_rate_limits(
            &json!({"rate_limits": {"primary": {"used_percent": 47}}}),
            &Shanghai,
            "test",
        )
        .expect("valid percentage should parse");
        assert_eq!(quota.seven_day_used_ratio, Some(0.47));
        assert_eq!(quota.seven_day_reset_at, None);
        assert_eq!(quota.seven_day_remaining_ratio, Some(0.53));
    }

    #[test]
    fn missing_model_is_unknown_and_never_a_billable_default() {
        assert_eq!(CodexProvider::normalize_model(None), "unknown");
        assert_eq!(CodexProvider::normalize_model(Some("  ")), "unknown");
        assert_eq!(CodexProvider::normalize_model(Some("gpt-5.6")), "gpt-5.6");
    }

    #[test]
    fn output_tokens_do_not_add_reasoning() {
        let usage = json!({
            "output_tokens": 100,
            "reasoning_output_tokens": 40
        });
        assert_eq!(CodexProvider::output_tokens_from_usage(&usage), 100);
        assert_eq!(
            CodexProvider::output_tokens_from_usage(&json!({ "output": 12 })),
            12
        );
    }

    #[test]
    fn timestamp_value_supports_rfc3339_seconds_and_millis() {
        let tz = &Shanghai;
        // RFC3339 string.
        let rfc = json!("2026-08-19T06:12:00Z");
        let parsed = CodexProvider::parse_ts_value(&rfc, tz).unwrap();
        assert_eq!(
            parsed.format("%Y-%m-%d %H:%M:%S").to_string(),
            "2026-08-19 14:12:00"
        );
        // Numeric seconds (10 digits).
        let seconds = json!(1_783_375_920i64);
        let s = CodexProvider::parse_ts_value(&seconds, tz).unwrap();
        assert_eq!(
            s.format("%Y-%m-%d %H:%M:%S").to_string(),
            "2026-07-07 06:12:00"
        );
        // Numeric milliseconds (13 digits).
        let millis = json!(1_783_375_920_000i64);
        let m = CodexProvider::parse_ts_value(&millis, tz).unwrap();
        assert_eq!(
            m.format("%Y-%m-%d %H:%M:%S").to_string(),
            "2026-07-07 06:12:00"
        );
        // String-form seconds.
        let s_str = json!("1783375920");
        assert_eq!(
            CodexProvider::parse_ts_value(&s_str, tz)
                .unwrap()
                .timestamp(),
            1_783_375_920
        );
        // Invalid / empty values return None.
        assert!(CodexProvider::parse_ts_value(&json!("not-a-time"), tz).is_none());
        assert!(CodexProvider::parse_ts_value(&json!(""), tz).is_none());
        assert!(CodexProvider::parse_ts_value(&json!(null), tz).is_none());
    }

    #[test]
    fn project_primary_model_follows_largest_token_contributor() {
        let mut acc = super::ProjectAcc {
            path: "C:/Work/App".to_string(),
            tokens: crate::models::TokenBreakdown::default(),
            cost: 0.0,
            sessions: 0,
            last_active: chrono::Utc::now().with_timezone(&Shanghai),
            primary_model: "gemini-2.5-pro".to_string(),
            model_tokens: std::collections::HashMap::new(),
        };
        // gemini contributes 40, gpt contributes 100 -> gpt becomes primary.
        CodexProvider::account_project_model(&mut acc, "gemini-2.5-pro", 40);
        assert_eq!(acc.primary_model, "gemini-2.5-pro");
        CodexProvider::account_project_model(&mut acc, "gpt-5.6", 100);
        assert_eq!(acc.primary_model, "gpt-5.6");
        // Another large gpt contribution keeps it primary.
        CodexProvider::account_project_model(&mut acc, "gpt-5.6", 200);
        assert_eq!(acc.primary_model, "gpt-5.6");
        // A gemini contribution that overtakes gpt promotes gemini again.
        CodexProvider::account_project_model(&mut acc, "gemini-2.5-pro", 1000);
        assert_eq!(acc.primary_model, "gemini-2.5-pro");
    }
}

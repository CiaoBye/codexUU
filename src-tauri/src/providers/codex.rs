use std::collections::{HashMap, HashSet};
use std::fs::{self, File};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc::{channel, Receiver};
use std::thread;
use std::time::{Duration, SystemTime};

use chrono::{DateTime, Datelike, NaiveDate, Utc};
use chrono_tz::Tz;
use serde_json::Value;

use crate::engine::pricing::PricingEngine;
use crate::models::{
    DailyActivity, ModelUsage, ProjectRankingItem, ProviderData, QuotaSnapshot, SkillAgg,
    SkillUsageItem, TaskItem, TokenBreakdown, TokenPeriods,
};
use crate::providers::{group_tasks_by_project, is_real_project_path};

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
                    channel: "Codex".to_string(),
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

        let now = Utc::now().with_timezone(tz);
        let today_str = now.format("%Y-%m-%d").to_string();
        let current_week = now.iso_week();
        let current_month = now.format("%Y-%m").to_string();

        let mut total_periods = TokenPeriods::default();
        let mut daily_map: HashMap<String, (TokenBreakdown, f64, u64)> = HashMap::new();
        let mut model_map: HashMap<String, (TokenBreakdown, u64, u64)> = HashMap::new();
        let mut project_map: HashMap<String, ProjectAcc> = HashMap::new();
        let mut tool_map: HashMap<String, ToolAcc> = HashMap::new();
        let mut tasks_map: HashMap<String, TaskItem> = HashMap::new();

        for (file_path, is_archived) in all_files {
            if let Ok(file) = File::open(&file_path) {
                let reader = BufReader::new(file);
                let mut session_project_path = String::new();
                let mut session_title = String::new();
                let mut session_primary_model = "gpt-4o".to_string();
                let mut session_tokens = TokenBreakdown::default();
                let mut file_project_tokens = TokenBreakdown::default();
                let mut session_last_active = now;
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

                    if let Ok(val) = serde_json::from_str::<Value>(&line) {
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
                        let mut event_dt = now;
                        if let Some(ts_str) = val
                            .get("timestamp")
                            .or_else(|| val.get("created_at"))
                            .and_then(|s| s.as_str())
                        {
                            if let Some(parsed) = Self::parse_ts(ts_str, tz) {
                                event_dt = parsed;
                                session_last_active = parsed;
                            }
                        }

                        // 3. Token counts extraction
                        let mut token_usage_opt = None;

                        if let Some(p) = payload {
                            if p.get("type").and_then(|s| s.as_str()) == Some("token_count") {
                                if let Some(info) = p.get("info") {
                                    token_usage_opt = info
                                        .get("total_token_usage")
                                        .or_else(|| info.get("last_token_usage"));
                                }
                            }
                        }
                        if token_usage_opt.is_none() {
                            token_usage_opt =
                                val.get("token_count").or_else(|| val.get("token_usage"));
                        }

                        if let Some(tc) = token_usage_opt {
                            let total_input =
                                tc.get("input_tokens").and_then(|v| v.as_u64()).unwrap_or(0);
                            let cached = tc
                                .get("cached_input_tokens")
                                .or_else(|| tc.get("cached_tokens"))
                                .and_then(|v| v.as_u64())
                                .unwrap_or(0);
                            let uncached = total_input.saturating_sub(cached);
                            let output_main = tc
                                .get("output_tokens")
                                .or_else(|| tc.get("output"))
                                .and_then(|v| v.as_u64())
                                .unwrap_or(0);
                            let reasoning = tc
                                .get("reasoning_output_tokens")
                                .and_then(|v| v.as_u64())
                                .unwrap_or(0);
                            let output = output_main + reasoning;

                            // Each token field can advance independently; never lose a field's growth
                            // when another field is reset or absent in a later event.
                            let delta_uncached = uncached.saturating_sub(highest_uncached);
                            let delta_cached = cached.saturating_sub(highest_cached);
                            let delta_output = output.saturating_sub(highest_output);

                            highest_uncached = highest_uncached.max(uncached);
                            highest_cached = highest_cached.max(cached);
                            highest_output = highest_output.max(output);

                            if delta_uncached + delta_cached + delta_output > 0 {
                                let delta =
                                    TokenBreakdown::new(delta_uncached, delta_cached, delta_output);
                                session_tokens.add(&delta);

                                // Attribution to model
                                let (model_entry, _sessions_cnt, turns_cnt) = model_map
                                    .entry(session_primary_model.clone())
                                    .or_insert((TokenBreakdown::default(), 0, 0));
                                model_entry.add(&delta);
                                *turns_cnt += 1;

                                // Daily aggregation
                                let date_key = event_dt.format("%Y-%m-%d").to_string();
                                let (daily_tb, daily_cost, _daily_sess) = daily_map
                                    .entry(date_key.clone())
                                    .or_insert((TokenBreakdown::default(), 0.0, 0));
                                daily_tb.add(&delta);
                                let (cost, _) =
                                    PricingEngine::calculate_cost(&session_primary_model, &delta);
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
                                        });
                                    entry.tokens.add(&delta);
                                    entry.cost += cost;
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
                        let explicit_tool_event = [event_type, payload_type].iter().any(|kind| {
                            matches!(
                                kind.to_ascii_lowercase().as_str(),
                                "function_call"
                                    | "custom_tool_call"
                                    | "tool_call"
                                    | "tool_calls"
                                    | "tool-use"
                                    | "tool_use"
                            )
                        });
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
                            let entry =
                                tool_map
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

                        // 5. Skill loads
                        if let Some(skill_name) = val
                            .get("skill_name")
                            .or_else(|| val.get("loaded_skill"))
                            .and_then(|s| s.as_str())
                        {
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

                if let Some((_, sessions_cnt, _)) = model_map.get_mut(&session_primary_model) {
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
                    channel: "Codex".to_string(),
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
        }

        let daily_activities = Self::backfill_daily(daily_map, now, days_limit);

        // Model Usage List
        let mut models: Vec<ModelUsage> = model_map
            .into_iter()
            .map(|(model_id, (tokens, sessions, turns))| {
                let (cost_usd, status) = PricingEngine::calculate_cost(&model_id, &tokens);
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
        tasks.extend(Self::scheduled_tasks(tz));
        let session_count = tasks.len();
        tasks = group_tasks_by_project(tasks);

        ProviderData {
            tokens: total_periods,
            daily_activities,
            models,
            tasks,
            projects,
            skills_and_tools,
            skill_details,
            session_count,
        }
    }

    fn backfill_daily(
        map: HashMap<String, (TokenBreakdown, f64, u64)>,
        now: DateTime<Tz>,
        days_limit: usize,
    ) -> Vec<DailyActivity> {
        let mut items: Vec<DailyActivity> = map
            .into_iter()
            .map(|(date, (tokens, cost_usd, sessions))| DailyActivity {
                date,
                tokens,
                cost_usd,
                sessions,
            })
            .collect();
        items.sort_by(|a, b| a.date.cmp(&b.date));

        let end = now.date_naive();
        let start = items
            .first()
            .and_then(|d| NaiveDate::parse_from_str(&d.date, "%Y-%m-%d").ok())
            .unwrap_or(end);

        let mut by_date: HashMap<String, DailyActivity> =
            items.into_iter().map(|d| (d.date.clone(), d)).collect();

        let mut result = Vec::new();
        let mut cursor = if start > end { end } else { start };
        while cursor <= end {
            let key = cursor.format("%Y-%m-%d").to_string();
            let entry = by_date.remove(&key).unwrap_or_else(|| DailyActivity {
                date: key.clone(),
                tokens: TokenBreakdown::default(),
                cost_usd: 0.0,
                sessions: 0,
            });
            result.push(entry);
            match cursor.succ_opt() {
                Some(next) => cursor = next,
                None => break,
            }
        }

        if days_limit > 0 && result.len() > days_limit {
            let split = result.len() - days_limit;
            result = result.split_off(split);
        }

        result
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
}

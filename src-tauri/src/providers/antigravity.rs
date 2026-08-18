use std::collections::{HashMap, HashSet};
use std::fs::{self, File};
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};

use chrono::{DateTime, Datelike, NaiveDate, Utc};
use chrono_tz::Tz;
use rusqlite::{Connection, OpenFlags};
use serde_json::Value;

use crate::engine::pricing::PricingEngine;
use crate::models::{
    DailyActivity, ModelUsage, ProjectRankingItem, ProviderData, SkillAgg, SkillUsageItem,
    TaskItem, TokenBreakdown, TokenPeriods,
};
use crate::providers::{group_tasks_by_project, is_real_project_path};

pub struct AntigravityProvider;

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

impl AntigravityProvider {
    pub fn get_antigravity_home() -> PathBuf {
        dirs::home_dir()
            .map(|h| h.join(".gemini").join("antigravity"))
            .unwrap_or_else(|| PathBuf::from(".gemini/antigravity"))
    }

    fn parse_ts(ts_str: &str, tz: &Tz) -> Option<DateTime<Tz>> {
        DateTime::parse_from_rfc3339(ts_str)
            .ok()
            .map(|dt| dt.with_timezone(tz))
    }

    fn find_transcript(home: &Path, conv_id: &str) -> Option<PathBuf> {
        let candidates = [
            home.join("brain")
                .join(conv_id)
                .join(".system_generated")
                .join("logs")
                .join("transcript.jsonl"),
            home.join("brain").join(conv_id).join("transcript.jsonl"),
            home.join("brain")
                .join(conv_id)
                .join("logs")
                .join("transcript.jsonl"),
        ];
        candidates.into_iter().find(|p| p.exists())
    }

    pub fn parse_all(days_limit: usize, tz: &Tz) -> ProviderData {
        let home = Self::get_antigravity_home();
        let conv_dir = home.join("conversations");

        let now = Utc::now().with_timezone(tz);
        let today_str = now.format("%Y-%m-%d").to_string();
        let current_week = now.iso_week();
        let current_month = now.format("%Y-%m").to_string();

        let mut total_periods = TokenPeriods::default();
        let mut daily_map: HashMap<String, (TokenBreakdown, f64, u64)> = HashMap::new();
        let mut model_map: HashMap<String, (TokenBreakdown, u64, u64)> = HashMap::new();
        let mut project_map: HashMap<String, ProjectAcc> = HashMap::new();
        let mut tool_map: HashMap<String, ToolAcc> = HashMap::new();
        let mut tasks: Vec<TaskItem> = Vec::new();
        let mut session_count = 0usize;

        if let Ok(entries) = fs::read_dir(&conv_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.extension().and_then(|s| s.to_str()) != Some("db") {
                    continue;
                }

                let conv_id = path
                    .file_stem()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .to_string();
                let transcript_path = Self::find_transcript(&home, &conv_id);
                let Some(transcript_path) = transcript_path else {
                    continue;
                };

                // Read model hints from SQLite metadata (display only, not used for fake token counts).
                let mut sqlite_model: Option<String> = None;
                if let Ok(conn) =
                    Connection::open_with_flags(&path, OpenFlags::SQLITE_OPEN_READ_ONLY)
                {
                    if let Ok(mut stmt) = conn.prepare("SELECT data FROM gen_metadata") {
                        if let Ok(rows) = stmt.query_map([], |row| row.get::<_, Vec<u8>>(0)) {
                            for blob in rows.flatten() {
                                let content = String::from_utf8_lossy(&blob);
                                if content.contains("gemini-3.7-flash") {
                                    sqlite_model = Some("gemini-3.7-flash".to_string());
                                } else if content.contains("gemini-2.5-pro") {
                                    sqlite_model = Some("gemini-2.5-pro".to_string());
                                } else if content.contains("gemini-2.5-flash") {
                                    sqlite_model = Some("gemini-2.5-flash".to_string());
                                } else if content.contains("claude-3-5-sonnet") {
                                    sqlite_model = Some("claude-3-5-sonnet-20241022".to_string());
                                }
                                if sqlite_model.is_some() {
                                    break;
                                }
                            }
                        }
                    }
                }

                let Ok(file) = File::open(&transcript_path) else {
                    continue;
                };
                let reader = BufReader::new(file);

                let mut primary_model = sqlite_model.unwrap_or_else(|| "unknown".to_string());
                let mut project_path: Option<String> = None;
                let mut project_title = String::new();
                let mut status: Option<String> = None;
                let mut conv_tokens = TokenBreakdown::default();
                let mut file_project_tokens = TokenBreakdown::default();
                let mut parsed_events = 0u64;
                let mut last_activity: Option<DateTime<Tz>> = None;
                let mut highest_uncached = 0u64;
                let mut highest_cached = 0u64;
                let mut highest_output = 0u64;

                for line in reader.lines().map_while(Result::ok) {
                    let Ok(val) = serde_json::from_str::<Value>(&line) else {
                        continue;
                    };
                    parsed_events += 1;

                    // Timestamp
                    let mut event_dt = last_activity.unwrap_or(now);
                    if let Some(ts_str) = val
                        .get("timestamp")
                        .or_else(|| val.get("created_at"))
                        .and_then(|s| s.as_str())
                    {
                        if let Some(parsed) = Self::parse_ts(ts_str, tz) {
                            event_dt = parsed;
                            last_activity = Some(parsed);
                        }
                    }

                    // Model
                    if let Some(model) = val
                        .get("model")
                        .or_else(|| val.get("model_id"))
                        .or_else(|| val.get("model_name"))
                        .and_then(|s| s.as_str())
                    {
                        primary_model = model.to_string();
                    }

                    // Project path
                    if project_path.is_none() {
                        if let Some(p) = val
                            .get("cwd")
                            .or_else(|| val.get("project_path"))
                            .or_else(|| val.get("working_directory"))
                            .or_else(|| val.get("directory"))
                            .and_then(|s| s.as_str())
                        {
                            project_path = Some(p.to_string());
                        }
                    }

                    // Title
                    if val.get("type").and_then(|s| s.as_str()) == Some("USER_INPUT") {
                        if let Some(content) = val.get("content").and_then(|s| s.as_str()) {
                            let trimmed = content
                                .replace("<USER_REQUEST>", "")
                                .replace("</USER_REQUEST>", "")
                                .trim()
                                .to_string();
                            if !trimmed.is_empty() {
                                project_title = trimmed.chars().take(48).collect();
                            }
                        }
                    }

                    // Status
                    if status.is_none() {
                        if let Some(s) = val
                            .get("status")
                            .or_else(|| val.get("phase"))
                            .or_else(|| val.get("state"))
                            .and_then(|s| s.as_str())
                        {
                            status = Some(s.to_string());
                        }
                    }

                    // Token usage: cumulative total_token_usage is delta-tracked; per-event usage is added directly.
                    let mut token_usage_opt = None;
                    let mut is_cumulative = false;

                    if let Some(info) = val.get("info") {
                        if let Some(tc) = info.get("total_token_usage") {
                            token_usage_opt = Some(tc);
                            is_cumulative = true;
                        } else if let Some(tc) = info.get("last_token_usage") {
                            token_usage_opt = Some(tc);
                        }
                    }
                    if token_usage_opt.is_none() {
                        if let Some(tc) = val.get("total_token_usage") {
                            token_usage_opt = Some(tc);
                            is_cumulative = true;
                        } else if let Some(tc) = val
                            .get("token_usage")
                            .or_else(|| val.get("usage"))
                            .or_else(|| val.get("last_token_usage"))
                        {
                            token_usage_opt = Some(tc);
                        }
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
                            let delta =
                                TokenBreakdown::new(delta_uncached, delta_cached, delta_output);
                            conv_tokens.add(&delta);

                            let (model_entry, _sessions, model_turns) = model_map
                                .entry(primary_model.clone())
                                .or_insert((TokenBreakdown::default(), 0, 0));
                            model_entry.add(&delta);
                            *model_turns += 1;

                            let date_key = event_dt.format("%Y-%m-%d").to_string();
                            let (daily_tb, daily_cost, _daily_sess) = daily_map
                                .entry(date_key.clone())
                                .or_insert((TokenBreakdown::default(), 0.0, 0));
                            daily_tb.add(&delta);
                            let (cost, _) = PricingEngine::calculate_cost(&primary_model, &delta);
                            *daily_cost += cost;

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

                            if let Some(path) = project_path.as_ref() {
                                if !path.is_empty() {
                                    let entry =
                                        project_map.entry(path.clone()).or_insert_with(|| {
                                            ProjectAcc {
                                                path: path.clone(),
                                                tokens: TokenBreakdown::default(),
                                                cost: 0.0,
                                                sessions: 0,
                                                last_active: event_dt,
                                                primary_model: primary_model.clone(),
                                            }
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
                    }

                    // Tools are counted only on explicit tool-call event types. A
                    // random `tool_calls` field in metadata is not a tool use.
                    let event_type = val
                        .get("type")
                        .or_else(|| val.get("event_type"))
                        .and_then(|v| v.as_str())
                        .map(|s| s.to_ascii_lowercase());
                    let explicit_tool_event = matches!(
                        event_type.as_deref(),
                        Some("function_call")
                            | Some("custom_tool_call")
                            | Some("tool_call")
                            | Some("tool_calls")
                            | Some("tool-use")
                            | Some("tool_use")
                    );
                    if explicit_tool_event {
                        if let Some(tool_calls) = val.get("tool_calls").and_then(|v| v.as_array()) {
                            for tc in tool_calls {
                                if let Some(name) = tc
                                    .get("name")
                                    .or_else(|| {
                                        tc.get("function").and_then(|function| function.get("name"))
                                    })
                                    .and_then(|s| s.as_str())
                                {
                                    let date_k = event_dt.format("%Y-%m-%d").to_string();
                                    let proj_k = project_path
                                        .clone()
                                        .unwrap_or_else(|| "default".to_string());
                                    let entry =
                                        tool_map.entry(name.to_string()).or_insert_with(|| {
                                            ToolAcc {
                                                kind: "tool".to_string(),
                                                count: 0,
                                                days: HashSet::new(),
                                                projects: HashSet::new(),
                                                last_used: event_dt,
                                            }
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
                    }

                    // Skill loads
                    if let Some(skill_name) = val
                        .get("skill_name")
                        .or_else(|| val.get("loaded_skill"))
                        .and_then(|s| s.as_str())
                    {
                        let date_k = event_dt.format("%Y-%m-%d").to_string();
                        let proj_k = project_path
                            .clone()
                            .unwrap_or_else(|| "default".to_string());
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

                if parsed_events == 0 {
                    continue;
                }

                session_count += 1;

                // Use transcript file modification time as a real fallback for activity time.
                let last_activity = last_activity
                    .or_else(|| {
                        fs::metadata(&transcript_path)
                            .and_then(|m| m.modified())
                            .ok()
                            .map(|t| {
                                let dt: DateTime<Utc> = t.into();
                                dt.with_timezone(tz)
                            })
                    })
                    .unwrap_or(now);

                // Session count per active day.
                let session_date = last_activity.format("%Y-%m-%d").to_string();
                let daily_entry = daily_map.entry(session_date.clone()).or_insert((
                    TokenBreakdown::default(),
                    0.0,
                    0,
                ));
                daily_entry.2 += 1;

                // Model session count.
                if let Some((_, sessions_cnt, _)) = model_map.get_mut(&primary_model) {
                    *sessions_cnt += 1;
                }

                // Project session count (tokens/cost already added at event level).
                if let Some(path) = project_path.as_ref() {
                    if !path.is_empty() {
                        let entry = project_map
                            .entry(path.clone())
                            .or_insert_with(|| ProjectAcc {
                                path: path.clone(),
                                tokens: TokenBreakdown::default(),
                                cost: 0.0,
                                sessions: 0,
                                last_active: last_activity,
                                primary_model: primary_model.clone(),
                            });

                        // Add any tokens that appeared before the project path was known.
                        let remaining = TokenBreakdown::new(
                            conv_tokens
                                .uncached_input
                                .saturating_sub(file_project_tokens.uncached_input),
                            conv_tokens
                                .cached_input
                                .saturating_sub(file_project_tokens.cached_input),
                            conv_tokens
                                .output
                                .saturating_sub(file_project_tokens.output),
                        );
                        if remaining.total > 0 {
                            entry.tokens.add(&remaining);
                            let (cost, _) =
                                PricingEngine::calculate_cost(&primary_model, &remaining);
                            entry.cost += cost;
                        }

                        entry.sessions += 1;
                        if last_activity > entry.last_active {
                            entry.last_active = last_activity;
                        }
                    }
                }

                let status = match status.as_deref().map(str::to_ascii_lowercase).as_deref() {
                    Some("running") | Some("active") | Some("in_progress") => "running".to_string(),
                    Some("pending") | Some("queued") | Some("waiting") => "pending".to_string(),
                    Some("completed") | Some("complete") | Some("done") | Some("success") => {
                        "completed".to_string()
                    }
                    _ => {
                        let elapsed_hours = (now - last_activity).num_hours();
                        if elapsed_hours <= 2 {
                            "running".to_string()
                        } else if last_activity.format("%Y-%m-%d").to_string() == today_str {
                            "pending".to_string()
                        } else {
                            "completed".to_string()
                        }
                    }
                };

                let title = if !project_title.is_empty() {
                    project_title
                } else {
                    format!("Task {}", conv_id.chars().take(8).collect::<String>())
                };

                tasks.push(TaskItem {
                    id: conv_id,
                    project_name: project_path
                        .as_ref()
                        .and_then(|p| Path::new(p).file_name())
                        .map(|s| s.to_string_lossy().to_string())
                        .unwrap_or_else(|| "未知项目".to_string()),
                    project_path: project_path.unwrap_or_default(),
                    title,
                    status,
                    updated_at: last_activity.format("%Y-%m-%d %H:%M").to_string(),
                    thread_count: 1,
                    channel: "antigravity".to_string(),
                });
            }
        }

        let daily_activities = Self::backfill_daily(daily_map, now, days_limit);

        // Model usage list sorted
        let mut model_usage: Vec<ModelUsage> = model_map
            .into_iter()
            .map(|(model_id, (tokens, sessions, turns))| {
                let (cost_usd, pricing_status) = PricingEngine::calculate_cost(&model_id, &tokens);
                ModelUsage {
                    model_id,
                    reasoning_effort: None,
                    tokens,
                    sessions,
                    turns,
                    cost_usd,
                    pricing_status,
                }
            })
            .collect();
        model_usage.sort_by_key(|m| std::cmp::Reverse(m.tokens.total));

        // Project ranking: only real, still-existing directories.
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

        // Skills & tools
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

        tasks = group_tasks_by_project(tasks);

        ProviderData {
            tokens: total_periods,
            daily_activities,
            models: model_usage,
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

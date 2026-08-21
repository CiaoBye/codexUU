use std::collections::{HashMap, HashSet};
use std::fs::{self, File};
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use chrono::{DateTime, Datelike, Utc};
use chrono_tz::Tz;
use serde_json::Value;

use crate::engine::pricing::PricingEngine;
use crate::models::{
    ModelUsage, ProjectRankingItem, ProviderData, SkillAgg, SkillUsageItem,
    TaskItem, TokenBreakdown, TokenPeriods,
};
use crate::providers::{
    backfill_daily, group_tasks_by_project, is_explicit_skill_event, is_explicit_tool_event,
    is_real_project_path,
};

use super::antigravity_db::parse_file as parse_db_file;

pub struct AntigravityProvider;

#[derive(Debug, Clone)]
struct ConversationSource {
    db_path: PathBuf,
    home: PathBuf,
}

#[derive(Debug, Clone)]
struct ProjectAcc {
    path: String,
    tokens: TokenBreakdown,
    cost: f64,
    sessions: u64,
    last_active: DateTime<Tz>,
    primary_model: String,
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

struct TokenAggregation<'a> {
    today_str: &'a str,
    current_week_year: i32,
    current_week_number: u32,
    current_month: &'a str,
    total_periods: &'a mut TokenPeriods,
    daily_map: &'a mut HashMap<String, (TokenBreakdown, f64, u64)>,
    model_map: &'a mut HashMap<String, (TokenBreakdown, u64, u64, f64)>,
    project_map: &'a mut HashMap<String, ProjectAcc>,
    conv_tokens: &'a mut TokenBreakdown,
    file_project_tokens: &'a mut TokenBreakdown,
}

impl TokenAggregation<'_> {
    fn apply(
        &mut self,
        delta: &TokenBreakdown,
        model_id: &str,
        event_dt: DateTime<Tz>,
        project_path: Option<&str>,
    ) {
        if delta.total == 0 {
            return;
        }

        self.conv_tokens.add(delta);
        let (cost, _) = PricingEngine::calculate_cost(model_id, delta);

        let (model_entry, _sessions, model_turns, model_cost) = self
            .model_map
            .entry(model_id.to_string())
            .or_insert((TokenBreakdown::default(), 0, 0, 0.0));
        model_entry.add(delta);
        *model_turns += 1;
        *model_cost += cost;

        let date_key = event_dt.format("%Y-%m-%d").to_string();
        let (daily_tokens, daily_cost, _daily_sessions) = self
            .daily_map
            .entry(date_key.clone())
            .or_insert((TokenBreakdown::default(), 0.0, 0));
        daily_tokens.add(delta);
        *daily_cost += cost;

        if date_key == self.today_str {
            self.total_periods.today.add(delta);
        }
        let event_week = event_dt.iso_week();
        if event_week.year() == self.current_week_year
            && event_week.week() == self.current_week_number
        {
            self.total_periods.week.add(delta);
        }
        if event_dt.format("%Y-%m").to_string() == self.current_month {
            self.total_periods.month.add(delta);
        }
        self.total_periods.all_time.add(delta);

        if let Some(path) = project_path.filter(|path| !path.trim().is_empty()) {
            let entry = self
                .project_map
                .entry(path.to_string())
                .or_insert_with(|| ProjectAcc {
                    path: path.to_string(),
                    tokens: TokenBreakdown::default(),
                    cost: 0.0,
                    sessions: 0,
                    last_active: event_dt,
                    primary_model: model_id.to_string(),
                    model_tokens: HashMap::new(),
                });
            entry.tokens.add(delta);
            entry.cost += cost;
            let model_total = {
                let slot = entry.model_tokens.entry(model_id.to_string()).or_insert(0);
                *slot = slot.saturating_add(delta.total);
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
            self.file_project_tokens.add(delta);
            if event_dt > entry.last_active {
                entry.last_active = event_dt;
            }
        }
    }
}

impl AntigravityProvider {
    pub fn source_roots() -> Vec<PathBuf> {
        Self::source_roots_from(&Self::gemini_home())
    }

    fn gemini_home() -> PathBuf {
        std::env::var_os("GEMINI_CLI_HOME")
            .filter(|value| !value.is_empty())
            .map(PathBuf::from)
            .or_else(|| dirs::home_dir().map(|home| home.join(".gemini")))
            .unwrap_or_else(|| PathBuf::from(".gemini"))
    }

    pub fn get_antigravity_home() -> PathBuf {
        Self::gemini_home().join("antigravity")
    }

    fn source_roots_from(gemini_home: &Path) -> Vec<PathBuf> {
        let mut roots = Vec::new();
        for name in ["antigravity", "antigravity-ide", "antigravity-backup"] {
            let home = gemini_home.join(name);
            roots.push(home.join("conversations"));
            roots.push(home.join("brain"));
        }
        roots.push(gemini_home.join("antigravity-cli").join("conversations"));
        roots
    }

    fn product_homes_from(gemini_home: &Path) -> Vec<(PathBuf, PathBuf)> {
        let mut homes = Vec::new();
        for name in ["antigravity", "antigravity-ide", "antigravity-backup"] {
            let home = gemini_home.join(name);
            let conversations = home.join("conversations");
            homes.push((home, conversations));
        }
        let cli_home = gemini_home.join("antigravity-cli");
        let cli_conversations = cli_home.join("conversations");
        homes.push((cli_home, cli_conversations));
        homes
    }

    fn conversation_root_rank(home: &Path) -> u8 {
        match home.file_name().and_then(|name| name.to_str()) {
            Some("antigravity") => 0,
            Some("antigravity-ide") => 1,
            Some("antigravity-cli") => 2,
            Some("antigravity-backup") => 3,
            _ => 4,
        }
    }

    fn select_unique_conversation_sources(homes: &[(PathBuf, PathBuf)]) -> Vec<ConversationSource> {
        let mut selected: HashMap<String, (ConversationSource, u8, SystemTime)> = HashMap::new();
        for (home, conv_dir) in homes {
            let Ok(entries) = fs::read_dir(conv_dir) else {
                continue;
            };
            let rank = Self::conversation_root_rank(home);
            for entry in entries.flatten() {
                let path = entry.path();
                if path.extension().and_then(|ext| ext.to_str()) != Some("db") {
                    continue;
                }
                let id = path
                    .file_stem()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .to_string();
                let modified = fs::metadata(&path)
                    .and_then(|metadata| metadata.modified())
                    .unwrap_or(SystemTime::UNIX_EPOCH);
                let replace = match selected.get(&id) {
                    None => true,
                    Some((_, existing_rank, existing_modified)) => {
                        rank < *existing_rank
                            || (rank == *existing_rank && modified > *existing_modified)
                    }
                };
                if replace {
                    selected.insert(
                        id,
                        (
                            ConversationSource {
                                db_path: path,
                                home: home.clone(),
                            },
                            rank,
                            modified,
                        ),
                    );
                }
            }
        }
        selected
            .into_values()
            .map(|(source, _, _)| source)
            .collect()
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

    fn clean_user_title(content: &str) -> String {
        let request = content
            .split_once("<USER_REQUEST>")
            .and_then(|(_, rest)| rest.split_once("</USER_REQUEST>"))
            .map(|(body, _)| body)
            .unwrap_or(content);
        let without_meta = request
            .split("<ADDITIONAL_METADATA>")
            .next()
            .unwrap_or(request)
            .replace("<USER_REQUEST>", "")
            .replace("</USER_REQUEST>", "");
        let collapsed = without_meta
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ");
        collapsed
            .trim_matches(|ch: char| ch == '/' || ch.is_whitespace())
            .chars()
            .take(48)
            .collect()
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
        let conversation_homes = Self::product_homes_from(&Self::gemini_home());
        let sources = Self::select_unique_conversation_sources(&conversation_homes);

        let now = Utc::now().with_timezone(tz);
        let today_str = now.format("%Y-%m-%d").to_string();
        let current_week = now.iso_week();
        let current_week_year = current_week.year();
        let current_week_number = current_week.week();
        let current_month = now.format("%Y-%m").to_string();

        let mut total_periods = TokenPeriods::default();
        let mut daily_map: HashMap<String, (TokenBreakdown, f64, u64)> = HashMap::new();
        // Cost is accumulated per usage event so tiered request pricing is not
        // incorrectly re-evaluated against the model's aggregate token total.
        let mut model_map: HashMap<String, (TokenBreakdown, u64, u64, f64)> = HashMap::new();
        let mut project_map: HashMap<String, ProjectAcc> = HashMap::new();
        let mut tool_map: HashMap<String, ToolAcc> = HashMap::new();
        let mut tasks: Vec<TaskItem> = Vec::new();
        let mut session_count = 0usize;
        let mut scanned_files = 0usize;
        let mut parsed_db_files = 0usize;
        let mut parsed_transcripts = 0usize;
        let mut db_usage_rows = 0usize;
        let mut db_decode_errors = 0usize;
        let mut read_errors = 0usize;
        let mut parse_errors = 0usize;
        let mut missing_transcripts = 0usize;

        for source in sources {
            let path = source.db_path;
            let home = source.home;
            scanned_files += 1;

            let conv_id = path
                .file_stem()
                .unwrap_or_default()
                .to_string_lossy()
                .to_string();
            let db_session = parse_db_file(&path);
            if db_session.database_opened {
                parsed_db_files += 1;
            }
            db_usage_rows += db_session.generations.len();
            db_decode_errors += db_session.malformed_rows;

            let transcript_path = Self::find_transcript(&home, &conv_id);
            if transcript_path.is_none() {
                missing_transcripts += 1;
            };

            // The database is now the authoritative token source. The
            // brain transcript remains useful for task/project metadata
            // and is retained as a compatibility fallback for old data.
            if db_session.generations.is_empty() && transcript_path.is_none() {
                continue;
            }

            let mut primary_model = db_session
                .generations
                .first()
                .map(|generation| generation.model_id.clone())
                .unwrap_or_else(|| "unknown".to_string());
            let mut project_path: Option<String> = db_session.workspace_path.clone();
            let mut project_title = String::new();
            let mut status: Option<String> = None;
            let mut conv_tokens = TokenBreakdown::default();
            let mut file_project_tokens = TokenBreakdown::default();
            let mut parsed_events = db_session.generations.len() as u64;
            let mut last_activity: Option<DateTime<Tz>> = db_session
                .generations
                .iter()
                .filter(|generation| generation.timestamp_ms > 0)
                .filter_map(|generation| {
                    DateTime::from_timestamp_millis(generation.timestamp_ms)
                        .map(|timestamp| timestamp.with_timezone(tz))
                })
                .max();
            // Untimestamped conversations must not fall through to "now" (which
            // would pollute today with old sessions); anchor them to the file's
            // real modification time instead.
            if last_activity.is_none() {
                last_activity = transcript_path
                    .as_ref()
                    .and_then(|p| fs::metadata(p).ok())
                    .or_else(|| fs::metadata(&path).ok())
                    .and_then(|metadata| metadata.modified().ok())
                    .map(|time| {
                        let dt: DateTime<Utc> = time.into();
                        dt.with_timezone(tz)
                    });
            }
            let mut highest_uncached = 0u64;
            let mut highest_cached = 0u64;
            let mut highest_output = 0u64;
            {
                let mut token_aggregation = TokenAggregation {
                    today_str: &today_str,
                    current_week_year,
                    current_week_number,
                    current_month: &current_month,
                    total_periods: &mut total_periods,
                    daily_map: &mut daily_map,
                    model_map: &mut model_map,
                    project_map: &mut project_map,
                    conv_tokens: &mut conv_tokens,
                    file_project_tokens: &mut file_project_tokens,
                };

                if let Some(transcript_path) = transcript_path.as_ref() {
                    let file = match File::open(transcript_path) {
                        Ok(file) => Some(file),
                        Err(_) => {
                            read_errors += 1;
                            None
                        }
                    };
                    if let Some(file) = file {
                        parsed_transcripts += 1;
                        let reader = BufReader::new(file);

                        for line_result in reader.lines() {
                            let line = match line_result {
                                Ok(line) => line,
                                Err(_) => {
                                    read_errors += 1;
                                    continue;
                                }
                            };
                            let val = match serde_json::from_str::<Value>(&line) {
                                Ok(val) => val,
                                Err(_) => {
                                    parse_errors += 1;
                                    continue;
                                }
                            };
                            parsed_events += 1;

                            // Timestamp
                            let mut event_dt = last_activity.unwrap_or(now);
                            if let Some(ts_value) =
                                val.get("timestamp").or_else(|| val.get("created_at"))
                            {
                                if let Some(parsed) = Self::parse_ts_value(ts_value, tz) {
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
                                    let trimmed = Self::clean_user_title(content);
                                    if !trimmed.is_empty() {
                                        project_title = trimmed;
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

                            // Old installations may expose usage only in the brain
                            // transcript. Prefer decoded DB generations whenever they
                            // exist so the same turn is never counted twice.
                            if db_session.generations.is_empty() {
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
                                    let total_input = tc
                                        .get("input_tokens")
                                        .and_then(|v| v.as_u64())
                                        .unwrap_or(0);
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
                                    let output = output_main.saturating_add(reasoning);

                                    let (delta_uncached, delta_cached, delta_output) =
                                        if is_cumulative {
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

                                    let delta = TokenBreakdown::new(
                                        delta_uncached,
                                        delta_cached,
                                        delta_output,
                                    );
                                    token_aggregation.apply(
                                        &delta,
                                        &primary_model,
                                        event_dt,
                                        project_path.as_deref(),
                                    );
                                }
                            }

                            // Tools are counted only on explicit tool-call event types. A
                            // random `tool_calls` field in metadata is not a tool use.
                            let event_type = val
                                .get("type")
                                .or_else(|| val.get("event_type"))
                                .and_then(|v| v.as_str())
                                .map(|s| s.to_ascii_lowercase());
                            let explicit_tool_event =
                                is_explicit_tool_event(&[event_type.as_deref().unwrap_or("")]);
                            if explicit_tool_event {
                                if let Some(tool_calls) =
                                    val.get("tool_calls").and_then(|v| v.as_array())
                                {
                                    for tc in tool_calls {
                                        if let Some(name) = tc
                                            .get("name")
                                            .or_else(|| {
                                                tc.get("function")
                                                    .and_then(|function| function.get("name"))
                                            })
                                            .and_then(|s| s.as_str())
                                        {
                                            let date_k = event_dt.format("%Y-%m-%d").to_string();
                                            let proj_k = project_path
                                                .clone()
                                                .unwrap_or_else(|| "default".to_string());
                                            let entry = tool_map
                                                .entry(name.to_string())
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
                                    }
                                }
                            }

                            // Skill loads. Only explicit skill-load event types count.
                            if is_explicit_skill_event(&[event_type.as_deref().unwrap_or("")]) {
                                if let Some(skill_name) = val
                                    .get("skill_name")
                                    .or_else(|| val.get("loaded_skill"))
                                    .and_then(|s| s.as_str())
                                {
                                    let date_k = event_dt.format("%Y-%m-%d").to_string();
                                    let proj_k = project_path
                                        .clone()
                                        .unwrap_or_else(|| "default".to_string());
                                    let entry = tool_map
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
                    }
                }

                // Decode the authoritative SQLite generations after the
                // transcript pass so workspace/title metadata is available for
                // project attribution. This path works even when Antigravity
                // is closed and a brain transcript is missing.
                for generation in &db_session.generations {
                    let event_dt = (generation.timestamp_ms > 0)
                        .then(|| DateTime::from_timestamp_millis(generation.timestamp_ms))
                        .flatten()
                        .map(|timestamp| timestamp.with_timezone(tz))
                        .unwrap_or_else(|| last_activity.unwrap_or(now));
                    if last_activity.is_none_or(|current| event_dt > current) {
                        last_activity = Some(event_dt);
                    }
                    token_aggregation.apply(
                        &generation.tokens,
                        &generation.model_id,
                        event_dt,
                        project_path.as_deref(),
                    );
                }
            }

            if parsed_events == 0 {
                continue;
            }

            session_count += 1;

            // Use transcript/database modification time as a real fallback
            // for activity time when protobuf timestamps are unavailable.
            let last_activity = last_activity
                .or_else(|| {
                    transcript_path.as_ref().and_then(|transcript| {
                        fs::metadata(transcript)
                            .and_then(|metadata| metadata.modified())
                            .ok()
                            .map(|time| {
                                let dt: DateTime<Utc> = time.into();
                                dt.with_timezone(tz)
                            })
                    })
                })
                .or_else(|| {
                    fs::metadata(&path)
                        .and_then(|metadata| metadata.modified())
                        .ok()
                        .map(|time| {
                            let dt: DateTime<Utc> = time.into();
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
            if let Some((_, sessions_cnt, _, _)) = model_map.get_mut(&primary_model) {
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
                            model_tokens: HashMap::new(),
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
                        let (cost, _) = PricingEngine::calculate_cost(&primary_model, &remaining);
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

        let daily_activities = backfill_daily(daily_map, now, days_limit);

        // Model usage list sorted
        let mut model_usage: Vec<ModelUsage> = model_map
            .into_iter()
            .map(|(model_id, (tokens, sessions, turns, cost_usd))| {
                let (_, pricing_status) = PricingEngine::calculate_cost(&model_id, &tokens);
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

        let attempted_at = now.format("%Y-%m-%d %H:%M:%S").to_string();
        let source_exists = conversation_homes
            .iter()
            .any(|(_, conv_dir)| conv_dir.is_dir());
        let parsed_any_data = parsed_db_files > 0 || parsed_transcripts > 0;
        let transcript_gap = missing_transcripts > 0 && db_usage_rows == 0;
        let status = if !source_exists {
            "unavailable"
        } else if scanned_files == 0
            || !parsed_any_data
            || transcript_gap
            || db_decode_errors > 0
            || read_errors > 0
            || parse_errors > 0
        {
            "degraded"
        } else {
            "healthy"
        };
        let message = if !source_exists {
            "未找到 Antigravity conversations 数据目录".to_string()
        } else if scanned_files == 0 {
            "已找到 Antigravity 数据目录，但没有会话数据库".to_string()
        } else {
            format!(
                "扫描 {} 个数据库，解析 {} 个 Token 记录、{} 个 transcript{}{}{}{}",
                scanned_files,
                db_usage_rows,
                parsed_transcripts,
                if db_decode_errors > 0 {
                    format!("，{} 行 protobuf 无法解析", db_decode_errors)
                } else {
                    String::new()
                },
                if missing_transcripts > 0 {
                    format!("，{} 个 transcript 缺失", missing_transcripts)
                } else {
                    String::new()
                },
                if read_errors > 0 {
                    format!("，{} 个读取失败", read_errors)
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
            id: "antigravity_db".to_string(),
            name: "Antigravity SQLite/Protobuf".to_string(),
            status: status.to_string(),
            message,
            last_success_at: parsed_any_data.then_some(attempted_at.clone()),
            last_attempt_at: Some(attempted_at),
            error_code: if db_decode_errors > 0 {
                Some("protobuf_decode_failed".to_string())
            } else if read_errors > 0 {
                Some("file_read_failed".to_string())
            } else if parse_errors > 0 {
                Some("json_parse_failed".to_string())
            } else if transcript_gap {
                Some("transcript_missing".to_string())
            } else if !source_exists {
                Some("source_not_found".to_string())
            } else {
                None
            },
            source_schema: Some(
                "SQLite gen_metadata protobuf + Brain transcript JSONL".to_string(),
            ),
            locations: Self::source_roots()
                .iter()
                .map(|path| path.display().to_string())
                .collect(),
            capabilities: vec![
                "token_components".to_string(),
                "offline_db_tokens".to_string(),
                "model_attribution".to_string(),
                "project_attribution".to_string(),
                "tool_events".to_string(),
                "skill_events".to_string(),
                "task_status".to_string(),
            ],
            scanned_files,
            parsed_sessions: session_count,
        };

        ProviderData {
            tokens: total_periods,
            daily_activities,
            models: model_usage,
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
    use super::AntigravityProvider;
    use chrono_tz::Asia::Shanghai;
    use std::fs;
    use std::path::Path;

    #[test]
    fn clean_user_title_keeps_request_and_drops_metadata() {
        let content = "<USER_REQUEST>\n审计最新版本，必须看完所有代码\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\nThe current working directory is CodexUU\n</ADDITIONAL_METADATA>";
        assert_eq!(
            AntigravityProvider::clean_user_title(content),
            "审计最新版本，必须看完所有代码"
        );
    }

    #[test]
    fn clean_user_title_strips_metadata_without_request_tags() {
        let content = "审计最新版本 / <ADDITIONAL_METADATA> The curr";
        assert_eq!(
            AntigravityProvider::clean_user_title(content),
            "审计最新版本"
        );
    }

    #[test]
    fn source_roots_include_ide_backup_and_cli() {
        let roots = AntigravityProvider::source_roots_from(Path::new("gemini-root"));
        let normalized: Vec<String> = roots
            .iter()
            .map(|path| path.to_string_lossy().replace('\\', "/"))
            .collect();
        assert!(normalized
            .iter()
            .any(|path| path.ends_with("gemini-root/antigravity/conversations")));
        assert!(normalized
            .iter()
            .any(|path| path.ends_with("gemini-root/antigravity-ide/conversations")));
        assert!(normalized
            .iter()
            .any(|path| path.ends_with("gemini-root/antigravity-ide/brain")));
        assert!(normalized
            .iter()
            .any(|path| path.ends_with("gemini-root/antigravity-backup/conversations")));
        assert!(normalized
            .iter()
            .any(|path| path.ends_with("gemini-root/antigravity-cli/conversations")));
    }

    #[test]
    fn timestamp_value_supports_rfc3339_seconds_and_millis() {
        use serde_json::json;
        let tz = &Shanghai;
        // RFC3339 string.
        let parsed =
            AntigravityProvider::parse_ts_value(&json!("2026-08-19T06:12:00Z"), tz).unwrap();
        assert_eq!(
            parsed.format("%Y-%m-%d %H:%M:%S").to_string(),
            "2026-08-19 14:12:00"
        );
        // Numeric seconds.
        let s = AntigravityProvider::parse_ts_value(&json!(1_783_375_920i64), tz).unwrap();
        assert_eq!(
            s.format("%Y-%m-%d %H:%M:%S").to_string(),
            "2026-07-07 06:12:00"
        );
        // Numeric milliseconds.
        let m = AntigravityProvider::parse_ts_value(&json!(1_783_375_920_000i64), tz).unwrap();
        assert_eq!(
            m.format("%Y-%m-%d %H:%M:%S").to_string(),
            "2026-07-07 06:12:00"
        );
        // Invalid / empty.
        assert!(AntigravityProvider::parse_ts_value(&json!("garbage"), tz).is_none());
        assert!(AntigravityProvider::parse_ts_value(&json!(""), tz).is_none());
        assert!(AntigravityProvider::parse_ts_value(&json!(null), tz).is_none());
    }

    #[test]
    fn conversation_files_prefer_live_over_backup_copy() {
        let tmp = std::env::temp_dir().join(format!(
            "codexuu-ag-roots-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or(0)
        ));
        let live_home = tmp.join("antigravity");
        let backup_home = tmp.join("antigravity-backup");
        let live_dir = live_home.join("conversations");
        let backup_dir = backup_home.join("conversations");
        fs::create_dir_all(&live_dir).expect("live conversations dir");
        fs::create_dir_all(&backup_dir).expect("backup conversations dir");
        fs::write(live_dir.join("sess-1.db"), b"live").expect("live db");
        fs::write(backup_dir.join("sess-1.db"), b"backup").expect("backup db");
        fs::write(backup_dir.join("sess-only-backup.db"), b"unique").expect("backup-only db");

        let selected = AntigravityProvider::select_unique_conversation_sources(&[
            (live_home.clone(), live_dir),
            (backup_home, backup_dir),
        ]);
        let _ = fs::remove_dir_all(&tmp);

        let paths: Vec<String> = selected
            .iter()
            .map(|source| source.db_path.to_string_lossy().replace('\\', "/"))
            .collect();
        assert_eq!(selected.len(), 2);
        assert!(paths
            .iter()
            .any(|path| path.ends_with("/antigravity/conversations/sess-1.db")));
        assert!(paths
            .iter()
            .any(|path| path.ends_with("/antigravity-backup/conversations/sess-only-backup.db")));
        assert!(!paths
            .iter()
            .any(|path| path.ends_with("/antigravity-backup/conversations/sess-1.db")));
    }
}

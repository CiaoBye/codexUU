use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq, Eq)]
pub struct TokenBreakdown {
    pub uncached_input: u64,
    pub cached_input: u64,
    pub output: u64,
    pub total: u64,
}

impl TokenBreakdown {
    pub fn new(uncached_input: u64, cached_input: u64, output: u64) -> Self {
        Self {
            uncached_input,
            cached_input,
            output,
            total: uncached_input + cached_input + output,
        }
    }

    pub fn add(&mut self, other: &TokenBreakdown) {
        self.uncached_input += other.uncached_input;
        self.cached_input += other.cached_input;
        self.output += other.output;
        self.total = self.uncached_input + self.cached_input + self.output;
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct TokenPeriods {
    pub today: TokenBreakdown,
    pub week: TokenBreakdown,
    pub month: TokenBreakdown,
    pub all_time: TokenBreakdown,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct QuotaFamily {
    pub id: String,
    pub label: String,
    pub five_hour_used_ratio: Option<f64>,
    pub five_hour_remaining_ratio: Option<f64>,
    pub five_hour_reset_at: Option<String>,
    pub seven_day_used_ratio: Option<f64>,
    pub seven_day_remaining_ratio: Option<f64>,
    pub seven_day_reset_at: Option<String>,
    pub has_five_hour: bool,
    pub has_seven_day: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct QuotaSnapshot {
    pub five_hour_used_ratio: Option<f64>,
    pub five_hour_remaining_ratio: Option<f64>,
    pub five_hour_reset_at: Option<String>,
    pub seven_day_used_ratio: Option<f64>,
    pub seven_day_remaining_ratio: Option<f64>,
    pub seven_day_reset_at: Option<String>,
    pub has_five_hour: bool,
    pub has_seven_day: bool,
    pub source: String,
    pub status: String,
    pub last_updated: String,
    #[serde(default)]
    pub families: Vec<QuotaFamily>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelUsage {
    pub model_id: String,
    pub reasoning_effort: Option<String>,
    pub tokens: TokenBreakdown,
    pub sessions: u64,
    pub turns: u64,
    pub cost_usd: f64,
    pub pricing_status: String, // "exact", "unpriced", "not_applicable"
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DailyActivity {
    pub date: String, // YYYY-MM-DD
    pub tokens: TokenBreakdown,
    pub cost_usd: f64,
    pub sessions: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskItem {
    pub id: String,
    pub project_name: String,
    pub project_path: String,
    pub title: String,
    pub status: String, // "running", "pending", "scheduled", "completed"
    pub updated_at: String,
    pub thread_count: usize,
    pub channel: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectRankingItem {
    pub rank: usize,
    pub name: String,
    pub path: String,
    pub tokens: TokenBreakdown,
    pub cost_usd: f64,
    pub sessions: u64,
    pub last_active_at: String,
    pub primary_model: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillUsageItem {
    pub name: String,
    pub kind: String, // "skill", "tool"
    pub count: u64,
    pub active_days: u64,
    pub project_count: u64,
    pub last_used_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SourceHealthStatus {
    pub id: String,
    pub name: String,
    pub status: String, // "healthy", "degraded", "stale", "refreshing", "unavailable"
    pub message: String,
    pub last_success_at: Option<String>,
    pub last_attempt_at: Option<String>,
    pub error_code: Option<String>,
    pub source_schema: Option<String>,
    pub locations: Vec<String>,
    pub capabilities: Vec<String>,
    pub scanned_files: usize,
    pub parsed_sessions: usize,
}

impl Default for SourceHealthStatus {
    fn default() -> Self {
        Self {
            id: String::new(),
            name: String::new(),
            status: "unavailable".to_string(),
            message: String::new(),
            last_success_at: None,
            last_attempt_at: None,
            error_code: None,
            source_schema: None,
            locations: Vec::new(),
            capabilities: Vec::new(),
            scanned_files: 0,
            parsed_sessions: 0,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DashboardSnapshot {
    pub channel: String, // "codex", "antigravity", "all"
    pub quota: QuotaSnapshot,
    pub tokens: TokenPeriods,
    pub daily_activities: Vec<DailyActivity>,
    pub models: Vec<ModelUsage>,
    pub tasks: Vec<TaskItem>,
    pub projects: Vec<ProjectRankingItem>,
    pub skills_and_tools: Vec<SkillUsageItem>,
    pub sources_health: Vec<SourceHealthStatus>,
    pub timestamp: String,
}

/// Internal aggregation result produced by each provider.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ProviderData {
    pub tokens: TokenPeriods,
    pub daily_activities: Vec<DailyActivity>,
    pub models: Vec<ModelUsage>,
    pub tasks: Vec<TaskItem>,
    pub projects: Vec<ProjectRankingItem>,
    pub skills_and_tools: Vec<SkillUsageItem>,
    /// Raw skill/tool detail used for cross-channel union merging.
    pub skill_details: HashMap<String, SkillAgg>,
    /// Number of successfully parsed sessions (for source health).
    pub session_count: usize,
    pub source_health: SourceHealthStatus,
}

/// Raw skill/tool aggregation detail.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillAgg {
    pub kind: String,
    pub count: u64,
    pub active_days: HashSet<String>,
    pub project_paths: HashSet<String>,
    pub last_used: DateTime<Utc>,
}

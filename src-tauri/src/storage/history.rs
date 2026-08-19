use crate::models::{DailyActivity, DashboardSnapshot, TokenBreakdown, TokenPeriods};
use chrono::Datelike;
use chrono_tz::Tz;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;

/// Version 2 history document. The `daily` and `all_time` maps are keyed by
/// statistic timezone first, then channel, because date bucketing for
/// today/week/month is timezone-dependent. Old version-1 files (which had no
/// timezone dimension) are migrated under [`HistoryDocument::LEGACY_TIMEZONE`].
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
struct HistoryDocument {
    version: u32,
    /// timezone -> channel -> date(YYYY-MM-DD) -> activity
    daily: HashMap<String, HashMap<String, HashMap<String, DailyActivity>>>,
    /// timezone -> channel -> cumulative breakdown
    all_time: HashMap<String, HashMap<String, TokenBreakdown>>,
}

/// The exact shape of the version-1 history file, retained only to migrate it.
#[derive(Debug, Clone, Deserialize)]
struct HistoryDocumentV1 {
    version: u32,
    daily: HashMap<String, HashMap<String, DailyActivity>>,
    all_time: HashMap<String, TokenBreakdown>,
}

impl HistoryDocument {
    /// Timezone assumed for version-1 files, which predate the timezone
    /// dimension. This matches the app default and the aggregator default, so
    /// legacy archives remain visible to the default configuration.
    const LEGACY_TIMEZONE: &'static str = "Asia/Shanghai";

    fn migrate_from_v1(v1: HistoryDocumentV1) -> Self {
        let mut daily = std::collections::HashMap::new();
        daily.insert(Self::LEGACY_TIMEZONE.to_string(), v1.daily);
        let mut all_time = std::collections::HashMap::new();
        all_time.insert(Self::LEGACY_TIMEZONE.to_string(), v1.all_time);
        Self {
            version: 2,
            daily,
            all_time,
        }
    }
}

fn history_dir() -> PathBuf {
    std::env::var_os("CODExUU_HISTORY_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            dirs::data_dir()
                .unwrap_or_else(|| PathBuf::from("."))
                .join("CodexUU")
        })
}

fn history_path() -> PathBuf {
    history_dir().join("history-v2.json")
}

fn legacy_history_path() -> PathBuf {
    history_dir().join("history-v1.json")
}

fn load() -> HistoryDocument {
    // Try the version-2 file first.
    if let Ok(content) = fs::read_to_string(history_path()) {
        if let Ok(document) = serde_json::from_str::<HistoryDocument>(&content) {
            if document.version == 2 {
                return document;
            }
        }
    }
    // Migrate a version-1 file (timezone-less) if present.
    if let Ok(content) = fs::read_to_string(legacy_history_path()) {
        if let Ok(v1) = serde_json::from_str::<HistoryDocumentV1>(&content) {
            if v1.version == 1 {
                return HistoryDocument::migrate_from_v1(v1);
            }
        }
    }
    HistoryDocument {
        version: 2,
        ..Default::default()
    }
}

fn save(document: &HistoryDocument) -> Result<(), String> {
    let path = history_path();
    let Some(parent) = path.parent() else {
        return Err("历史目录不存在".to_string());
    };
    fs::create_dir_all(parent).map_err(|error| format!("创建历史目录失败：{error}"))?;
    let content =
        serde_json::to_string(document).map_err(|error| format!("序列化历史失败：{error}"))?;
    crate::storage::file::write_atomic(&path, &content)
        .map_err(|error| format!("提交历史失败：{error}"))
}

/// Recomputes the `today / week / month / all_time` buckets from a set of
/// daily rows in the given timezone. `week` counts rows whose date is within
/// the current ISO week starting on Monday (00:00), `month` counts rows in the
/// current calendar month, and `all_time` is the sum of every row. This is the
/// single source of truth for period buckets after any merge or archive fill.
pub fn recompute_periods(daily: &[DailyActivity], tz: &Tz) -> TokenPeriods {
    let now = chrono::Utc::now().with_timezone(tz);
    let today_str = now.format("%Y-%m-%d").to_string();
    let month_prefix = now.format("%Y-%m").to_string();
    let weekday = now.weekday().number_from_monday(); // 1 = Monday .. 7 = Sunday
    let monday = now.date_naive() - chrono::Duration::days((weekday - 1) as i64);
    let today = now.date_naive();

    let mut periods = TokenPeriods::default();
    for activity in daily {
        periods.all_time.add(&activity.tokens);
        if activity.date == today_str {
            periods.today.add(&activity.tokens);
        }
        if let Ok(date) = chrono::NaiveDate::parse_from_str(&activity.date, "%Y-%m-%d") {
            if date >= monday && date <= today {
                periods.week.add(&activity.tokens);
            }
        }
        if activity.date.starts_with(&month_prefix) {
            periods.month.add(&activity.tokens);
        }
    }
    periods
}

/// True when a daily row is a synthetic "consecutive natural day" zero-fill
/// produced by the providers — no tokens, no cost, no sessions. Such a row
/// must never mask a real archived row.
fn is_zero_fill(activity: &DailyActivity) -> bool {
    activity.tokens.total == 0 && activity.cost_usd == 0.0 && activity.sessions == 0
}

/// Chooses which row to keep when the current observation and an archived row
/// describe the same date. A real archived row takes precedence over a
/// provider zero-fill (so pruned history is never zeroed out); otherwise the
/// fresher current observation wins.
fn merge_row(current: &DailyActivity, archived: &DailyActivity) -> DailyActivity {
    if is_zero_fill(current) && archived.tokens.total > 0 {
        archived.clone()
    } else {
        current.clone()
    }
}

/// Reconciles current source data with the local per-timezone daily summaries.
/// Current source data wins for dates it observes with real activity; dates
/// whose source rows have been pruned are filled from the archive. Crucially,
/// provider zero-fill rows never overwrite a real archived row, and the
/// today/week/month/all_time buckets are recomputed from the final daily rows.
pub fn reconcile(mut snapshot: DashboardSnapshot, timezone: &str) -> DashboardSnapshot {
    let mut document = load();
    let tz: Tz = timezone
        .parse()
        .unwrap_or(HistoryDocument::LEGACY_TIMEZONE.parse().unwrap());

    let channel_daily = document
        .daily
        .entry(timezone.to_string())
        .or_default()
        .entry(snapshot.channel.clone())
        .or_default();

    let mut by_date: HashMap<String, DailyActivity> = snapshot
        .daily_activities
        .iter()
        .cloned()
        .map(|activity| (activity.date.clone(), activity))
        .collect();

    // Merge archived rows: a real archived row fills a gap and also takes
    // precedence over a provider zero-fill row for the same date.
    for (date, archived) in channel_daily.iter() {
        match by_date.get_mut(date) {
            Some(current) => {
                let merged = merge_row(current, archived);
                *current = merged;
            }
            None => {
                by_date.insert(date.clone(), archived.clone());
            }
        }
    }

    let mut daily: Vec<DailyActivity> = by_date.into_values().collect();
    daily.sort_by(|left, right| left.date.cmp(&right.date));
    snapshot.daily_activities = daily;

    snapshot.tokens = recompute_periods(&snapshot.daily_activities, &tz);

    // Persist the merged rows so the archive stays the record of real history.
    let channel_all_time = document.all_time.entry(timezone.to_string()).or_default();
    for activity in &snapshot.daily_activities {
        channel_daily.insert(activity.date.clone(), activity.clone());
    }
    channel_all_time.insert(snapshot.channel.clone(), snapshot.tokens.all_time.clone());
    let _ = save(&document);
    snapshot
}

#[cfg(test)]
mod tests {
    use super::{is_zero_fill, recompute_periods};
    use crate::models::{DailyActivity, TokenBreakdown, TokenPeriods};
    use std::sync::{Mutex, OnceLock};

    /// Serializes tests that mutate the process-global history directory
    /// (`CODExUU_HISTORY_DIR`), which parallel tests would otherwise race on.
    fn history_lock() -> &'static Mutex<()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(()))
    }

    fn day(date: &str, uncached: u64, cached: u64, output: u64, sessions: u64) -> DailyActivity {
        DailyActivity {
            date: date.to_string(),
            tokens: TokenBreakdown::new(uncached, cached, output),
            cost_usd: 0.0,
            sessions,
        }
    }

    fn zero_fill(date: &str) -> DailyActivity {
        DailyActivity {
            date: date.to_string(),
            tokens: TokenBreakdown::default(),
            cost_usd: 0.0,
            sessions: 0,
        }
    }

    #[test]
    fn zero_fill_is_detected() {
        assert!(is_zero_fill(&zero_fill("2026-08-17")));
        assert!(!is_zero_fill(&day("2026-08-17", 1, 0, 0, 1)));
    }

    #[test]
    fn recompute_periods_sums_component_consistent_breakdowns() {
        let daily = vec![
            day("2026-08-17", 10, 20, 30, 1), // Monday (start of week, but see below)
            day("2026-08-20", 40, 5, 1, 1),
        ];
        let periods = recompute_periods(&daily, &chrono_tz::Asia::Shanghai);
        // The exact today/week/month membership depends on the current date,
        // but all_time must always equal the sum of every daily row.
        assert_eq!(
            periods.all_time,
            TokenBreakdown::new(50, 25, 31),
            "all_time must sum every daily row regardless of today's date"
        );
        // today must never exceed the full all_time.
        assert!(periods.today.total <= periods.all_time.total);
        assert!(periods.week.total <= periods.all_time.total);
        assert!(periods.month.total <= periods.all_time.total);
        // today/week/month must be component-consistent (total == sum of parts).
        assert_eq!(
            periods.today.total,
            periods.today.uncached_input + periods.today.cached_input + periods.today.output
        );
        assert_eq!(
            periods.week.total,
            periods.week.uncached_input + periods.week.cached_input + periods.week.output
        );
        assert_eq!(
            periods.month.total,
            periods.month.uncached_input + periods.month.cached_input + periods.month.output
        );
    }

    #[test]
    fn recompute_periods_barriers_are_timezone_consistent() {
        // Given a fixed "now" is injected via the current clock we cannot pin
        // exact today, so we assert structural invariants that hold for any
        // real clock: buckets are non-negative and never exceed all_time.
        let daily = vec![day("2020-01-01", 100, 0, 0, 1)];
        let periods = recompute_periods(&daily, &chrono_tz::Asia::Shanghai);
        assert!(periods.today.total <= 100);
        assert!(periods.week.total <= 100);
        assert!(periods.month.total <= 100);
        assert_eq!(periods.all_time.uncached_input, 100);
    }

    #[test]
    fn token_periods_total_is_component_consistent_by_construction() {
        let periods = TokenPeriods {
            today: TokenBreakdown::new(1, 2, 3),
            week: TokenBreakdown::new(4, 5, 6),
            month: TokenBreakdown::new(7, 8, 9),
            all_time: TokenBreakdown::new(10, 11, 12),
        };
        assert_eq!(periods.today.total, 6);
        assert_eq!(periods.week.total, 15);
        assert_eq!(periods.month.total, 24);
        assert_eq!(periods.all_time.total, 33);
    }

    #[test]
    fn zero_fill_row_never_masks_archived_real_row() {
        // A provider zero-fill for a pruned-source date must not overwrite a
        // real archived row; the archived value is what is preserved.
        let archived = day("2026-08-17", 100, 200, 300, 1);
        let current = zero_fill("2026-08-17");
        let merged = super::merge_row(&current, &archived);
        assert_eq!(merged.tokens, archived.tokens);
        assert_eq!(merged.sessions, archived.sessions);
        assert_eq!(merged.date, archived.date);
    }

    #[test]
    fn real_current_row_still_wins_over_archived() {
        let current = day("2026-08-17", 50, 0, 0, 1);
        let archived = day("2026-08-17", 500, 0, 0, 1);
        let merged = super::merge_row(&current, &archived);
        // The fresh observation is authoritative for an observed real date.
        assert_eq!(merged.tokens, current.tokens);
    }

    #[test]
    fn v1_history_migrates_under_the_legacy_timezone() {
        let _lock = history_lock().lock().unwrap();
        use serde_json::json;

        let dir = std::env::temp_dir().join(format!(
            "codexuu-history-migrate-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).expect("create temp history dir");
        std::env::set_var("CODExUU_HISTORY_DIR", &dir);

        // Simulate an old version-1 file: no timezone dimension.
        let v1 = json!({
            "version": 1,
            "daily": {
                "codex": {
                    "2026-08-17": {
                        "date": "2026-08-17",
                        "tokens": {"uncached_input": 10, "cached_input": 0, "output": 0, "total": 10},
                        "cost_usd": 0.0,
                        "sessions": 1
                    }
                }
            },
            "all_time": {
                "codex": {"uncached_input": 10, "cached_input": 0, "output": 0, "total": 10}
            }
        });
        std::fs::write(dir.join("history-v1.json"), v1.to_string()).expect("write v1 file");

        let document = super::load();
        let codex_daily = &document
            .daily
            .get(super::HistoryDocument::LEGACY_TIMEZONE)
            .and_then(|by_channel| by_channel.get("codex"))
            .expect("v1 daily migrated under legacy timezone");
        assert_eq!(codex_daily.len(), 1);
        assert_eq!(codex_daily["2026-08-17"].tokens.total, 10);
        assert_eq!(
            document
                .all_time
                .get(super::HistoryDocument::LEGACY_TIMEZONE)
                .and_then(|by_channel| by_channel.get("codex"))
                .map(|b| b.total),
            Some(10)
        );
        assert_eq!(document.version, 2);

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn reconcile_fills_pruned_dates_and_recomputes_all_time() {
        let _lock = history_lock().lock().unwrap();
        use crate::models::DashboardSnapshot;
        use crate::storage::settings;
        use chrono_tz::Tz;

        let dir = std::env::temp_dir().join(format!(
            "codexuu-history-reconcile-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).expect("create temp history dir");
        std::env::set_var("CODExUU_HISTORY_DIR", &dir);

        // First pass: current data observes today only, but the archive already
        // holds a real historical day (source pruned since).
        let first = DashboardSnapshot {
            channel: "codex".to_string(),
            quota: crate::models::QuotaSnapshot::default(),
            tokens: TokenPeriods::default(),
            daily_activities: vec![zero_fill("2026-08-16"), day("2026-08-17", 0, 0, 0, 0)],
            models: Vec::new(),
            tasks: Vec::new(),
            projects: Vec::new(),
            skills_and_tools: Vec::new(),
            sources_health: Vec::new(),
            timestamp: String::new(),
        };
        // Pre-seed the archive with a real historical row under the timezone.
        {
            let timezone = settings::AppSettings::default().timezone;
            let mut document = super::load();
            document
                .daily
                .entry(timezone.clone())
                .or_default()
                .entry("codex".to_string())
                .or_default()
                .insert("2026-08-16".to_string(), day("2026-08-16", 100, 0, 0, 1));
            super::save(&document).expect("seed archive");
        }

        let tz_name = settings::AppSettings::default().timezone;
        let tz: Tz = tz_name.parse().expect("default tz");
        // The current daily set includes a zero-fill for the archived date.
        let snapshot = super::reconcile(first, &tz_name);

        let archived_day = snapshot
            .daily_activities
            .iter()
            .find(|d| d.date == "2026-08-16")
            .expect("archived date preserved");
        assert_eq!(
            archived_day.tokens.total, 100,
            "zero-fill must not erase archive"
        );
        assert_eq!(archived_day.sessions, 1);

        // Recomputing all_time must include the restored archived row.
        let recomputed = super::recompute_periods(&snapshot.daily_activities, &tz);
        assert_eq!(recomputed.all_time.total, 100);

        let _ = std::fs::remove_dir_all(&dir);
    }
}

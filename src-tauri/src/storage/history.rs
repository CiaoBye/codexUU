use crate::models::{DailyActivity, DashboardSnapshot, TokenBreakdown};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
struct HistoryDocument {
    version: u32,
    daily: HashMap<String, HashMap<String, DailyActivity>>,
    all_time: HashMap<String, TokenBreakdown>,
}

fn history_path() -> PathBuf {
    dirs::data_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("CodexUU")
        .join("history-v1.json")
}

fn load() -> HistoryDocument {
    fs::read_to_string(history_path())
        .ok()
        .and_then(|content| serde_json::from_str::<HistoryDocument>(&content).ok())
        .filter(|document| document.version == 1)
        .unwrap_or_else(|| HistoryDocument {
            version: 1,
            ..Default::default()
        })
}

fn save(document: &HistoryDocument) -> Result<(), String> {
    let path = history_path();
    let Some(parent) = path.parent() else {
        return Err("历史目录不存在".to_string());
    };
    fs::create_dir_all(parent).map_err(|error| format!("创建历史目录失败：{error}"))?;
    let content =
        serde_json::to_string(document).map_err(|error| format!("序列化历史失败：{error}"))?;
    let temp = path.with_extension("json.tmp");
    fs::write(&temp, content).map_err(|error| format!("写入历史失败：{error}"))?;
    crate::storage::file::replace(&temp, &path)
        .map_err(|error| format!("提交历史失败：{error}"))?;
    Ok(())
}

fn sum_daily_tokens(daily: &[DailyActivity]) -> TokenBreakdown {
    let mut summed = TokenBreakdown::default();
    for activity in daily {
        summed.add(&activity.tokens);
    }
    summed
}

fn complete_tokens_with_largest_total(
    current: &TokenBreakdown,
    summed_daily: &TokenBreakdown,
) -> TokenBreakdown {
    if summed_daily.total >= current.total {
        summed_daily.clone()
    } else {
        current.clone()
    }
}

/// Reconciles current source data with local daily summaries. Current source
/// data wins for dates it can still observe; archived dates fill gaps left by
/// pruned/deleted source files. Only aggregate counters are persisted.
pub fn reconcile(mut snapshot: DashboardSnapshot) -> DashboardSnapshot {
    let mut document = load();
    let archived_daily = document.daily.entry(snapshot.channel.clone()).or_default();
    let mut daily = snapshot.daily_activities.clone();
    let current_dates: std::collections::HashSet<String> =
        daily.iter().map(|activity| activity.date.clone()).collect();
    for (date, activity) in archived_daily.iter() {
        if !current_dates.contains(date) {
            daily.push(activity.clone());
        }
    }
    daily.sort_by(|left, right| left.date.cmp(&right.date));
    snapshot.daily_activities = daily;

    let summed_daily = sum_daily_tokens(&snapshot.daily_activities);
    snapshot.tokens.all_time =
        complete_tokens_with_largest_total(&snapshot.tokens.all_time, &summed_daily);

    let current_daily = snapshot.daily_activities.clone();
    for activity in current_daily {
        archived_daily.insert(activity.date.clone(), activity);
    }
    document
        .all_time
        .insert(snapshot.channel.clone(), snapshot.tokens.all_time.clone());
    let _ = save(&document);
    snapshot
}

#[cfg(test)]
mod tests {
    use super::{complete_tokens_with_largest_total, sum_daily_tokens};
    use crate::models::{DailyActivity, TokenBreakdown};

    #[test]
    fn all_time_sums_daily_rows_instead_of_mixing_components() {
        let daily = vec![
            DailyActivity {
                date: "2026-08-17".to_string(),
                tokens: TokenBreakdown::new(10, 20, 30),
                cost_usd: 0.0,
                sessions: 1,
            },
            DailyActivity {
                date: "2026-08-18".to_string(),
                tokens: TokenBreakdown::new(40, 5, 1),
                cost_usd: 0.0,
                sessions: 1,
            },
        ];
        let summed = sum_daily_tokens(&daily);
        assert_eq!(summed, TokenBreakdown::new(50, 25, 31));

        let larger_current = TokenBreakdown::new(200, 0, 0);
        let chosen = complete_tokens_with_largest_total(&larger_current, &summed);
        assert_eq!(chosen, larger_current);

        let smaller_current = TokenBreakdown::new(1, 1, 1);
        let chosen = complete_tokens_with_largest_total(&smaller_current, &summed);
        assert_eq!(chosen, summed);
    }
}

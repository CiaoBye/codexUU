pub mod antigravity;
pub mod antigravity_db;
pub mod antigravity_quota;
pub mod codex;
pub mod registry;

use std::collections::HashMap;
use std::path::Path;

use chrono::{DateTime, NaiveDate};
use chrono_tz::Tz;

use crate::models::{DailyActivity, TaskItem, TokenBreakdown};

/// Fill consecutive natural days between the earliest and latest observed date,
/// inserting zero rows for dates with no data. Providers must call this so
/// charts render unbroken date ranges and missing days are never disguised as
/// active days.
pub fn backfill_daily(
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

/// Normalize workspace paths so Windows drive-letter and slash variants merge.
pub fn normalize_project_path(raw: &str) -> String {
    let trimmed = raw.trim().replace('\\', "/");
    let without_trailing = trimmed.trim_end_matches('/');
    #[cfg(windows)]
    {
        without_trailing.to_ascii_lowercase()
    }
    #[cfg(not(windows))]
    {
        without_trailing.to_string()
    }
}

/// A normalized path that is a tool home directory or runtime scratch rooted in
/// the OS temp directory. This deliberately does NOT blanket-tag every path
/// that merely contains a `temp`/`tmp` segment: users keep real projects in
/// folders like `C:\Temp`, and those must stay in the ranking.
fn is_cache_or_tool_home(normalized: &str) -> bool {
    let parts: Vec<&str> = normalized
        .split('/')
        .filter(|part| !part.is_empty())
        .collect();
    // Tool home dirs are never user project workspaces.
    if parts
        .iter()
        .any(|part| matches!(*part, ".codex" | ".gemini"))
    {
        return true;
    }

    // A workspace rooted directly inside the OS temp directory is runtime
    // scratch rather than a user project. The prefix match keeps drive-level
    // folders such as `C:\Temp` (a distinct, real directory) from being dropped.
    if let Ok(tmp) = std::env::temp_dir().canonicalize() {
        let tmp_norm = normalize_project_path(&tmp.to_string_lossy());
        if !tmp_norm.is_empty() && normalized.starts_with(&tmp_norm) {
            let remainder = &normalized[tmp_norm.len()..];
            if remainder.is_empty() || remainder.starts_with('/') {
                return true;
            }
        }
    }
    false
}

/// Keep project ranking limited to directories that still exist and are not
/// clearly runtime/cache locations rather than user projects.
pub fn is_real_project_path(raw: &str) -> bool {
    let path = Path::new(raw);
    if raw.trim().is_empty() || !path.is_dir() {
        return false;
    }
    !is_cache_or_tool_home(&normalize_project_path(raw))
}

pub fn is_explicit_skill_event(kinds: &[&str]) -> bool {
    kinds.iter().any(|kind| {
        matches!(
            kind.to_ascii_lowercase().as_str(),
            "skill" | "skill_load" | "skill_loaded" | "loaded_skill" | "skill_use" | "load_skill"
        )
    })
}

/// Tool usage is counted only for the two explicit event kinds emitted by the
/// supported providers. Names such as `tool_call` are not part of the product
/// metric contract and may also occur as incidental metadata.
pub fn is_explicit_tool_event(kinds: &[&str]) -> bool {
    kinds.iter().any(|kind| {
        matches!(
            kind.to_ascii_lowercase().as_str(),
            "function_call" | "custom_tool_call"
        )
    })
}

/// Aggregate task cards by project and status. The latest thread supplies the
/// title/time while the count retains the number of underlying threads.
pub fn group_tasks_by_project(tasks: Vec<TaskItem>) -> Vec<TaskItem> {
    let mut grouped: HashMap<(String, String), TaskItem> = HashMap::new();
    for mut task in tasks {
        task.project_path = normalize_project_path(&task.project_path);
        if !task.channel.is_empty() {
            task.channel = task.channel.to_ascii_lowercase();
        }
        let key = (task.project_path.clone(), task.status.clone());
        if let Some(existing) = grouped.get_mut(&key) {
            existing.thread_count += task.thread_count;
            if task.updated_at > existing.updated_at {
                existing.title = task.title;
                existing.updated_at = task.updated_at;
                existing.channel = task.channel;
            }
            if existing.project_name == "未知项目" && task.project_name != "未知项目" {
                existing.project_name = task.project_name;
            }
        } else {
            grouped.insert(key, task);
        }
    }
    let mut result: Vec<TaskItem> = grouped.into_values().collect();
    result.sort_by(|a, b| b.updated_at.cmp(&a.updated_at));
    result
}

#[cfg(test)]
mod tests {
    use super::{
        group_tasks_by_project, is_cache_or_tool_home, is_explicit_skill_event,
        is_explicit_tool_event, is_real_project_path, normalize_project_path,
    };
    use crate::models::TaskItem;
    use std::path::PathBuf;

    #[test]
    fn windows_paths_normalize_drive_letter_and_slashes() {
        let left = normalize_project_path(r"C:\Work\App");
        let right = normalize_project_path("c:/Work/App/");
        assert_eq!(left.to_ascii_lowercase(), right.to_ascii_lowercase());
        assert!(!left.ends_with('/'));
        assert!(!right.ends_with('/'));
    }

    #[test]
    fn real_project_path_keeps_existing_source_tree() {
        let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        assert!(is_real_project_path(&manifest.to_string_lossy()));
    }

    #[test]
    fn cache_home_rejects_tool_home_dirs_and_os_temp_roots() {
        assert!(is_cache_or_tool_home("c:/users/x/.codex/sessions"));
        assert!(is_cache_or_tool_home("c:/users/x/.gemini/antigravity"));
        // A plain "temp"/"tmp" segment is no longer treated as disqualifying.
        assert!(!is_cache_or_tool_home("c:/work/tmp/project"));
        assert!(!is_cache_or_tool_home("c:/temp"));
        assert!(!is_cache_or_tool_home("c:/work/app"));
    }

    #[test]
    fn skill_event_requires_explicit_load_type() {
        assert!(is_explicit_skill_event(&["skill_loaded"]));
        assert!(!is_explicit_skill_event(&["message"]));
    }

    #[test]
    fn tool_event_requires_supported_explicit_type() {
        assert!(is_explicit_tool_event(&["FUNCTION_CALL"]));
        assert!(is_explicit_tool_event(&["custom_tool_call"]));
        for incidental_kind in ["tool_call", "tool_calls", "tool-use", "tool_use", "message"] {
            assert!(!is_explicit_tool_event(&[incidental_kind]));
        }
    }

    fn task(title: &str, updated_at: &str, channel: &str) -> TaskItem {
        TaskItem {
            id: format!("{title}-{channel}"),
            project_name: "App".to_string(),
            project_path: "C:/Work/App".to_string(),
            title: title.to_string(),
            status: "running".to_string(),
            updated_at: updated_at.to_string(),
            thread_count: 1,
            channel: channel.to_string(),
        }
    }

    #[test]
    fn grouped_task_uses_the_latest_threads_title_time_and_channel() {
        let older = task("Codex older", "2026-08-20 09:00", "Codex");
        let newer = task("Antigravity latest", "2026-08-20 10:00", "Antigravity");

        for input in [
            vec![older.clone(), newer.clone()],
            vec![newer.clone(), older.clone()],
        ] {
            let grouped = group_tasks_by_project(input);
            assert_eq!(grouped.len(), 1);
            assert_eq!(grouped[0].title, "Antigravity latest");
            assert_eq!(grouped[0].updated_at, "2026-08-20 10:00");
            assert_eq!(grouped[0].channel, "antigravity");
            assert_eq!(grouped[0].thread_count, 2);
        }
    }
}

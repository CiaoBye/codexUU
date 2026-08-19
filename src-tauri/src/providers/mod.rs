pub mod antigravity;
pub mod antigravity_db;
pub mod codex;

use std::collections::HashMap;
use std::path::Path;

use crate::models::TaskItem;

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

/// Keep project ranking limited to directories that still exist and are not
/// clearly runtime/cache locations rather than user projects.
pub fn is_real_project_path(raw: &str) -> bool {
    let path = Path::new(raw);
    if raw.trim().is_empty() || !path.is_dir() {
        return false;
    }

    let normalized = normalize_project_path(raw);
    let parts: Vec<&str> = normalized
        .split('/')
        .filter(|part| !part.is_empty())
        .collect();
    if parts
        .iter()
        .any(|part| matches!(*part, ".codex" | ".gemini" | "temp" | "tmp"))
    {
        return false;
    }
    true
}

pub fn is_explicit_skill_event(kinds: &[&str]) -> bool {
    kinds.iter().any(|kind| {
        matches!(
            kind.to_ascii_lowercase().as_str(),
            "skill" | "skill_load" | "skill_loaded" | "loaded_skill" | "skill_use" | "load_skill"
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
            }
            if existing.channel != task.channel {
                existing.channel = "all".to_string();
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
    use super::{is_explicit_skill_event, is_real_project_path, normalize_project_path};
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
    fn skill_event_requires_explicit_load_type() {
        assert!(is_explicit_skill_event(&["skill_loaded"]));
        assert!(!is_explicit_skill_event(&["message"]));
    }
}

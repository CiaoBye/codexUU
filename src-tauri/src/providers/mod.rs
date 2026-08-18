pub mod antigravity;
pub mod codex;

use std::collections::HashMap;
use std::path::Path;

use crate::models::TaskItem;

/// Keep project ranking limited to directories that still exist and are not
/// clearly runtime/cache locations rather than user projects.
pub fn is_real_project_path(raw: &str) -> bool {
    let path = Path::new(raw);
    if raw.trim().is_empty() || !path.is_dir() {
        return false;
    }

    let normalized = raw.replace('\\', "/").to_ascii_lowercase();
    let parts: Vec<&str> = normalized
        .split('/')
        .filter(|part| !part.is_empty())
        .collect();
    if parts.iter().any(|part| {
        matches!(
            *part,
            ".codex" | ".gemini" | "appdata" | "temp" | "tmp" | "cache"
        )
    }) {
        return false;
    }
    true
}

/// Aggregate task cards by project and status. The latest thread supplies the
/// title/time while the count retains the number of underlying threads.
pub fn group_tasks_by_project(tasks: Vec<TaskItem>) -> Vec<TaskItem> {
    let mut grouped: HashMap<(String, String), TaskItem> = HashMap::new();
    for task in tasks {
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

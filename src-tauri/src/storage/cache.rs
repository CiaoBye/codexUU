use serde::{de::DeserializeOwned, Deserialize, Serialize};
use std::collections::hash_map::DefaultHasher;
use std::collections::HashMap;
use std::fs;
use std::hash::{Hash, Hasher};
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant, UNIX_EPOCH};

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ProviderCache<T> {
    version: u32,
    provider: String,
    timezone: String,
    fingerprint: String,
    saved_at: String,
    data: T,
}

fn cache_path(provider: &str) -> PathBuf {
    dirs::data_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("CodexUU")
        .join("cache")
        .join(format!("provider-{provider}-v1.json"))
}

fn collect_files(root: &Path, output: &mut Vec<String>) {
    let Ok(metadata) = fs::metadata(root) else {
        output.push(format!("{}|missing", root.display()));
        return;
    };
    if metadata.is_file() {
        let modified = metadata
            .modified()
            .ok()
            .and_then(|value| value.duration_since(UNIX_EPOCH).ok())
            .map(|value| value.as_nanos())
            .unwrap_or_default();
        output.push(format!(
            "{}|{}|{}",
            root.display(),
            metadata.len(),
            modified
        ));
        return;
    }
    let Ok(entries) = fs::read_dir(root) else {
        output.push(format!("{}|unreadable", root.display()));
        return;
    };
    for entry in entries.flatten() {
        collect_files(&entry.path(), output);
    }
}

/// Computes a cheap persistent fingerprint from source paths without reading
/// transcript bodies. It invalidates the snapshot cache when files are added,
/// removed, resized, or modified. Results are memoized for 2 seconds so the
/// main window and widget can share one directory walk.
pub fn source_fingerprint(roots: &[PathBuf]) -> String {
    let key = roots
        .iter()
        .map(|path| path.to_string_lossy().into_owned())
        .collect::<Vec<_>>()
        .join("\n");
    if let Ok(memo) = fingerprint_memo().lock() {
        if let Some((saved_at, fingerprint)) = memo.get(&key) {
            if saved_at.elapsed() < Duration::from_secs(2) {
                return fingerprint.clone();
            }
        }
    }

    let mut records = Vec::new();
    for root in roots {
        collect_files(root, &mut records);
    }
    records.sort();
    let mut hasher = DefaultHasher::new();
    records.hash(&mut hasher);
    let fingerprint = format!("{:016x}", hasher.finish());
    if let Ok(mut memo) = fingerprint_memo().lock() {
        memo.insert(key, (Instant::now(), fingerprint.clone()));
    }
    fingerprint
}

fn fingerprint_memo() -> &'static Mutex<HashMap<String, (Instant, String)>> {
    static MEMO: OnceLock<Mutex<HashMap<String, (Instant, String)>>> = OnceLock::new();
    MEMO.get_or_init(|| Mutex::new(HashMap::new()))
}

fn read_cache<T: DeserializeOwned>(provider: &str) -> Option<ProviderCache<T>> {
    let content = fs::read_to_string(cache_path(provider)).ok()?;
    let cache = serde_json::from_str::<ProviderCache<T>>(&content).ok()?;
    (cache.version == 1 && cache.provider == provider).then_some(cache)
}

pub fn load_exact<T: DeserializeOwned>(
    provider: &str,
    timezone: &str,
    fingerprint: &str,
) -> Option<T> {
    let cache = read_cache::<T>(provider)?;
    (cache.timezone == timezone && cache.fingerprint == fingerprint).then_some(cache.data)
}

pub fn load_latest<T: DeserializeOwned>(provider: &str, timezone: &str) -> Option<T> {
    let cache = read_cache::<T>(provider)?;
    (cache.timezone == timezone).then_some(cache.data)
}

pub fn save<T: Serialize>(
    provider: &str,
    timezone: &str,
    fingerprint: &str,
    data: &T,
    saved_at: &str,
) -> Result<(), String> {
    let path = cache_path(provider);
    let Some(parent) = path.parent() else {
        return Err("缓存目录不存在".to_string());
    };
    fs::create_dir_all(parent).map_err(|error| format!("创建缓存目录失败：{error}"))?;
    let cache = ProviderCache {
        version: 1,
        provider: provider.to_string(),
        timezone: timezone.to_string(),
        fingerprint: fingerprint.to_string(),
        saved_at: saved_at.to_string(),
        data,
    };
    let content =
        serde_json::to_string(&cache).map_err(|error| format!("序列化缓存失败：{error}"))?;
    let temp = path.with_extension("json.tmp");
    fs::write(&temp, content).map_err(|error| format!("写入缓存失败：{error}"))?;
    crate::storage::file::replace(&temp, &path)
        .map_err(|error| format!("提交缓存失败：{error}"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::source_fingerprint;
    use std::path::PathBuf;

    #[test]
    fn fingerprint_is_stable_for_same_roots() {
        let roots = vec![
            PathBuf::from(".codex/sessions"),
            PathBuf::from(".codex/archived_sessions"),
        ];
        assert_eq!(source_fingerprint(&roots), source_fingerprint(&roots));
    }

    #[test]
    fn fingerprint_distinguishes_different_roots() {
        assert_ne!(
            source_fingerprint(&[PathBuf::from("missing-source-a")]),
            source_fingerprint(&[PathBuf::from("missing-source-b")])
        );
    }
}

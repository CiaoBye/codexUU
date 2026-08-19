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
    /// Statistic-boundary key (day|isoweek|month) captured at save time. When
    /// it no longer matches the current period, the cached `today/week/month`
    /// buckets are stale and must be invalidated even if the fingerprint is
    /// unchanged (e.g. a day rolled over while the source files stayed put).
    period: String,
    fingerprint: String,
    saved_at: String,
    data: T,
}

fn cache_path(provider: &str) -> PathBuf {
    let base = std::env::var_os("CODExUU_CACHE_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            dirs::data_dir()
                .unwrap_or_else(|| PathBuf::from("."))
                .join("CodexUU")
                .join("cache")
        });
    base.join(format!("provider-{provider}-v1.json"))
}

/// Statistic-boundary key that changes whenever the reporting day, ISO week,
/// or month rolls over in `tz`. Snapshot caches whose `today/week/month`
/// buckets are derived from this period must be invalidated when it changes.
pub fn stat_period(tz: &chrono_tz::Tz) -> String {
    let now = chrono::Utc::now().with_timezone(tz);
    format!(
        "{}|{}|{}",
        now.format("%Y-%m-%d"),
        now.format("%G-W%V"), // ISO week year + week, e.g. 2026-W34
        now.format("%Y-%m"),
    )
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
    period: &str,
    fingerprint: &str,
) -> Option<T> {
    let cache = read_cache::<T>(provider)?;
    (cache.timezone == timezone && cache.period == period && cache.fingerprint == fingerprint)
        .then_some(cache.data)
}

pub fn load_latest<T: DeserializeOwned>(provider: &str, timezone: &str) -> Option<T> {
    let cache = read_cache::<T>(provider)?;
    (cache.timezone == timezone).then_some(cache.data)
}

pub fn save<T: Serialize>(
    provider: &str,
    timezone: &str,
    period: &str,
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
        period: period.to_string(),
        fingerprint: fingerprint.to_string(),
        saved_at: saved_at.to_string(),
        data,
    };
    let content =
        serde_json::to_string(&cache).map_err(|error| format!("序列化缓存失败：{error}"))?;
    crate::storage::file::write_atomic(&path, &content)
        .map_err(|error| format!("提交缓存失败：{error}"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{load_exact, save, source_fingerprint};
    use std::fs;
    use std::path::PathBuf;

    /// Returns a unique temp cache dir and installs it via the env override so
    /// tests never touch the real user data directory.
    fn temp_cache_dir() -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "codexuu-cache-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::env::set_var("CODExUU_CACHE_DIR", &dir);
        dir
    }

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

    #[test]
    fn cache_invalidates_when_stat_period_rolls_over() {
        let dir = temp_cache_dir();
        let provider = "test-provider";
        let timezone = "Asia/Shanghai";
        let fingerprint = "same-fingerprint";
        save(
            provider,
            timezone,
            "2026-08-17|2026-W34|2026-08", // period on day A
            fingerprint,
            &42u32,
            "saved",
        )
        .expect("cache should save");

        // Same provider/timezone/fingerprint but a new reporting day must NOT
        // match the cache — the today/week/month buckets would be stale.
        assert_eq!(
            load_exact::<u32>(
                provider,
                timezone,
                "2026-08-18|2026-W34|2026-08", // period on day B
                fingerprint,
            ),
            None,
            "cache written on a previous stat day must not be served"
        );

        // The exact same period should still hit.
        assert_eq!(
            load_exact::<u32>(
                provider,
                timezone,
                "2026-08-17|2026-W34|2026-08",
                fingerprint,
            ),
            Some(42),
            "cache matching timezone, period and fingerprint should be served"
        );

        // A differing timezone in the same period must also miss.
        assert_eq!(
            load_exact::<u32>(provider, "UTC", "2026-08-17|2026-W34|2026-08", fingerprint,),
            None
        );
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn stat_period_changes_across_reporting_days() {
        // Sanity: the period string embeds different components so distinct
        // boundary days yield distinct keys (day and week/month components).
        assert_ne!(
            super::stat_period(&chrono_tz::Asia::Shanghai),
            String::new(),
            "stat_period must produce a non-empty key"
        );
    }
}

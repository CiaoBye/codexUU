use std::collections::{HashMap, HashSet};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

/// Owns refresh de-duplication and cooldown state for all background jobs.
/// Providers do not need to know how a refresh is scheduled; they only expose
/// the work that should run under a provider-scoped key.
pub struct RefreshCoordinator;

impl RefreshCoordinator {
    fn in_flight() -> &'static Mutex<HashSet<String>> {
        static STATE: OnceLock<Mutex<HashSet<String>>> = OnceLock::new();
        STATE.get_or_init(|| Mutex::new(HashSet::new()))
    }

    fn last_completed() -> &'static Mutex<HashMap<String, Instant>> {
        static STATE: OnceLock<Mutex<HashMap<String, Instant>>> = OnceLock::new();
        STATE.get_or_init(|| Mutex::new(HashMap::new()))
    }

    pub fn try_start(key: &str, min_interval: Duration) -> bool {
        let Ok(mut in_flight) = Self::in_flight().lock() else {
            return false;
        };
        if in_flight.contains(key) {
            return false;
        }
        if let Ok(last_completed) = Self::last_completed().lock() {
            if last_completed
                .get(key)
                .is_some_and(|last| last.elapsed() < min_interval)
            {
                return false;
            }
        }
        in_flight.insert(key.to_string())
    }

    pub fn is_in_flight(key: &str) -> bool {
        Self::in_flight()
            .lock()
            .map(|state| state.contains(key))
            .unwrap_or(false)
    }

    pub fn finish(key: &str) {
        if let Ok(mut in_flight) = Self::in_flight().lock() {
            in_flight.remove(key);
        }
        if let Ok(mut last_completed) = Self::last_completed().lock() {
            last_completed.insert(key.to_string(), Instant::now());
        }
    }
}

#[cfg(test)]
mod tests {
    use super::RefreshCoordinator;
    use std::time::Duration;

    #[test]
    fn refresh_is_deduplicated_and_cooled_down_after_completion() {
        let key = format!(
            "refresh-coordinator-test-{}",
            std::thread::current().name().unwrap_or("unnamed")
        );
        assert!(RefreshCoordinator::try_start(&key, Duration::from_secs(0)));
        assert!(!RefreshCoordinator::try_start(&key, Duration::from_secs(0)));
        assert!(RefreshCoordinator::is_in_flight(&key));

        RefreshCoordinator::finish(&key);

        assert!(!RefreshCoordinator::is_in_flight(&key));
        assert!(!RefreshCoordinator::try_start(&key, Duration::from_secs(60)));
    }
}

use std::path::PathBuf;

use chrono_tz::Tz;

use crate::models::{ProviderData, QuotaSnapshot};

use super::{antigravity::AntigravityProvider, antigravity_quota, codex::CodexProvider};

pub type UsageCollector = fn(usize, &Tz) -> ProviderData;
pub type QuotaCollector = fn(&Tz) -> QuotaSnapshot;
pub type SourceRoots = fn() -> Vec<PathBuf>;

#[derive(Clone, Copy)]
pub struct ProviderSpec {
    pub id: &'static str,
    pub name: &'static str,
    pub source_schema: &'static str,
    pub collect_usage: UsageCollector,
    pub collect_quota: QuotaCollector,
    pub source_roots: SourceRoots,
}
fn codex_usage(days_limit: usize, tz: &Tz) -> ProviderData {
    CodexProvider::parse_all_sessions(days_limit, tz)
}

fn codex_quota(tz: &Tz) -> QuotaSnapshot {
    CodexProvider::fetch_quota(tz)
}

fn codex_roots() -> Vec<PathBuf> {
    CodexProvider::source_roots()
}

fn antigravity_usage(days_limit: usize, tz: &Tz) -> ProviderData {
    AntigravityProvider::parse_all(days_limit, tz)
}

fn antigravity_quota(tz: &Tz) -> QuotaSnapshot {
    antigravity_quota::fetch_quota(tz)
}

fn antigravity_roots() -> Vec<PathBuf> {
    AntigravityProvider::source_roots()
}

static PROVIDERS: [ProviderSpec; 2] = [
    ProviderSpec {
        id: "codex",
        name: "Codex",
        source_schema: "Codex rollout JSONL",
        collect_usage: codex_usage,
        collect_quota: codex_quota,
        source_roots: codex_roots,
    },
    ProviderSpec {
        id: "antigravity",
        name: "Antigravity",
        source_schema: "Antigravity conversations / brain",
        collect_usage: antigravity_usage,
        collect_quota: antigravity_quota,
        source_roots: antigravity_roots,
    },
];

/// Static provider registry. Adding a provider now has one explicit wiring
/// point, while the existing provider parsers remain independently testable.
pub struct ProviderRegistry;

impl ProviderRegistry {
    pub fn all() -> &'static [ProviderSpec] {
        &PROVIDERS
    }

    pub fn get(id: &str) -> Option<&'static ProviderSpec> {
        Self::all().iter().find(|provider| provider.id == id)
    }
}

#[cfg(test)]
mod tests {
    use super::ProviderRegistry;

    #[test]
    fn built_in_providers_have_stable_ids_and_wiring() {
        let ids: Vec<&str> = ProviderRegistry::all()
            .iter()
            .map(|provider| provider.id)
            .collect();
        assert_eq!(ids, vec!["codex", "antigravity"]);
        assert_eq!(ProviderRegistry::get("codex").map(|provider| provider.name), Some("Codex"));
        assert!(ProviderRegistry::get("unknown").is_none());
    }
}

use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};
use std::thread;
use std::time::{Duration, Instant};

use chrono::{DateTime, Utc};
use chrono_tz::Tz;

use crate::engine::refresh::RefreshCoordinator;
use crate::models::{
    DailyActivity, DashboardSnapshot, ModelUsage, ProjectRankingItem, ProviderData, QuotaSnapshot,
    SkillAgg, SkillUsageItem, SourceHealthStatus, TokenBreakdown,
};
use crate::providers::registry::ProviderRegistry;
use crate::providers::{group_tasks_by_project, normalize_project_path};
use crate::storage::{cache, history};

pub struct Aggregator;

impl Aggregator {
    fn quota_cache() -> &'static Mutex<Option<(String, Instant, QuotaSnapshot)>> {
        static CACHE: OnceLock<Mutex<Option<(String, Instant, QuotaSnapshot)>>> = OnceLock::new();
        CACHE.get_or_init(|| Mutex::new(None))
    }

    fn antigravity_quota_cache() -> &'static Mutex<Option<(String, Instant, QuotaSnapshot)>> {
        static CACHE: OnceLock<Mutex<Option<(String, Instant, QuotaSnapshot)>>> = OnceLock::new();
        CACHE.get_or_init(|| Mutex::new(None))
    }

    fn resolve_tz(timezone: Option<&str>) -> Tz {
        timezone
            .and_then(|s| s.parse().ok())
            .unwrap_or(chrono_tz::Asia::Shanghai)
    }

    fn skill_to_item(name: String, agg: &SkillAgg, tz: &Tz) -> SkillUsageItem {
        let last_used: DateTime<Tz> = agg.last_used.with_timezone(tz);
        SkillUsageItem {
            name,
            kind: agg.kind.clone(),
            count: agg.count,
            active_days: agg.active_days.len() as u64,
            project_count: agg.project_paths.len() as u64,
            last_used_at: last_used.format("%m/%d %H:%M").to_string(),
        }
    }

    fn cache_timestamp(tz: &Tz) -> String {
        Utc::now()
            .with_timezone(tz)
            .format("%Y-%m-%d %H:%M:%S")
            .to_string()
    }

    fn should_persist(data: &ProviderData) -> bool {
        matches!(data.source_health.status.as_str(), "healthy" | "degraded")
    }

    fn persist_provider(provider: &str, timezone: &str, tz: &Tz, parsed: &ProviderData) {
        if !Self::should_persist(parsed) {
            return;
        }
        let Some(spec) = ProviderRegistry::get(provider) else {
            return;
        };
        let roots = (spec.source_roots)();
        let fingerprint = cache::source_fingerprint(&roots);
        let period = cache::stat_period(tz);
        let _ = cache::save(
            provider,
            timezone,
            &period,
            &fingerprint,
            parsed,
            &Self::cache_timestamp(tz),
        );
    }

    fn start_refresh(key: &str, min_interval: Duration) -> bool {
        RefreshCoordinator::try_start(key, min_interval)
    }

    fn refresh_in_flight(key: &str) -> bool {
        RefreshCoordinator::is_in_flight(key)
    }

    fn finish_refresh(key: &str) {
        RefreshCoordinator::finish(key);
    }

    fn schedule_usage_refresh(provider: &str, timezone: String, tz: Tz) -> bool {
        let key = format!("{provider}|{timezone}");
        if !Self::start_refresh(&key, Duration::from_secs(120)) {
            return false;
        }
        let Some(spec) = ProviderRegistry::get(provider).copied() else {
            Self::finish_refresh(&key);
            return false;
        };
        let provider_id = spec.id;

        thread::spawn(move || {
            let _guard = InFlightGuard { key };
            let parsed = (spec.collect_usage)(0, &tz);
            Self::persist_provider(provider_id, &timezone, &tz, &parsed);
        });
        true
    }

    fn quota_cache_for(provider: &str) -> &'static Mutex<Option<(String, Instant, QuotaSnapshot)>> {
        match provider {
            "antigravity" => Self::antigravity_quota_cache(),
            _ => Self::quota_cache(),
        }
    }

    fn schedule_quota_refresh(provider: &str, timezone: String, tz: Tz) {
        let key = format!("{provider}-quota|{timezone}");
        if !Self::start_refresh(&key, Duration::from_secs(30)) {
            return;
        }
        let Some(spec) = ProviderRegistry::get(provider).copied() else {
            Self::finish_refresh(&key);
            return;
        };
        let provider_id = spec.id;

        thread::spawn(move || {
            let _guard = InFlightGuard { key };
            let snapshot = (spec.collect_quota)(&tz);
            if let Ok(mut cache) = Self::quota_cache_for(provider_id).lock() {
                let replace_cache = cache
                    .as_ref()
                    .map(|(_, _, cached)| {
                        snapshot.status == "available" || cached.status != "available"
                    })
                    .unwrap_or(true);
                if replace_cache {
                    *cache = Some((timezone, Instant::now(), snapshot));
                }
            }
        });
    }

    fn loading_provider_data(
        id: &str,
        name: &str,
        schema: &str,
        locations: Vec<String>,
        message: &str,
        tz: &Tz,
    ) -> ProviderData {
        ProviderData {
            source_health: SourceHealthStatus {
                id: id.to_string(),
                name: name.to_string(),
                status: "refreshing".to_string(),
                message: message.to_string(),
                last_success_at: None,
                last_attempt_at: Some(Self::cache_timestamp(tz)),
                error_code: Some("initial_scan_in_progress".to_string()),
                source_schema: Some(schema.to_string()),
                locations,
                capabilities: vec!["background_refresh".to_string()],
                scanned_files: 0,
                parsed_sessions: 0,
            },
            ..Default::default()
        }
    }

    fn mark_refreshing(mut data: ProviderData, tz: &Tz, provider_name: &str) -> ProviderData {
        data.source_health.status = "refreshing".to_string();
        data.source_health.error_code = Some("refresh_in_progress".to_string());
        data.source_health.last_attempt_at = Some(Self::cache_timestamp(tz));
        data.source_health.message =
            format!("检测到 {provider_name} 数据源变化，后台刷新中；当前展示上次成功快照");
        if !data
            .source_health
            .capabilities
            .iter()
            .any(|capability| capability == "background_refresh")
        {
            data.source_health
                .capabilities
                .push("background_refresh".to_string());
        }
        data
    }

    fn mark_stale(mut data: ProviderData, tz: &Tz, provider_name: &str) -> ProviderData {
        data.source_health.status = "stale".to_string();
        data.source_health.error_code = Some("refresh_deferred".to_string());
        data.source_health.last_attempt_at = Some(Self::cache_timestamp(tz));
        data.source_health.message =
            format!("检测到 {provider_name} 数据源变化，后台刷新已限流；当前展示最近成功快照");
        data
    }

    /// A forced quota fetch that comes back unavailable must not overwrite a
    /// previously fetched available snapshot with nothing.
    fn should_keep_previous_quota(
        fresh_status: &str,
        cached_status: &str,
        requested_timezone: &str,
        cached_timezone: &str,
    ) -> bool {
        requested_timezone == cached_timezone
            && fresh_status != "available"
            && cached_status == "available"
    }

    fn load_quota(provider: &str, tz: &Tz, force: bool) -> QuotaSnapshot {
        let timezone = tz.to_string();
        let Some(spec) = ProviderRegistry::get(provider).copied() else {
            return QuotaSnapshot {
                status: "unavailable".to_string(),
                source: format!("未知 Provider：{provider}"),
                last_updated: Self::cache_timestamp(tz),
                ..Default::default()
            };
        };
        let quota_cache = Self::quota_cache_for(provider);
        if force {
            let snapshot = (spec.collect_quota)(tz);
            if let Ok(mut cache) = quota_cache.lock() {
                let keep_previous = cache
                    .as_ref()
                    .map(|(cached_timezone, _, cached)| {
                        Self::should_keep_previous_quota(
                            &snapshot.status,
                            &cached.status,
                            &timezone,
                            cached_timezone,
                        )
                    })
                    .unwrap_or(false);
                if keep_previous {
                    if let Some((_, _, cached)) = cache.as_ref().cloned() {
                        return cached;
                    }
                }
                *cache = Some((timezone, Instant::now(), snapshot.clone()));
            }
            return snapshot;
        }

        if let Ok(cache) = quota_cache.lock() {
            if let Some((cached_timezone, cached_at, snapshot)) = cache.as_ref() {
                if cached_timezone == &timezone && cached_at.elapsed() < Duration::from_secs(30) {
                    return snapshot.clone();
                }
                if cached_timezone == &timezone {
                    let stale_snapshot = snapshot.clone();
                    drop(cache);
                    Self::schedule_quota_refresh(provider, timezone, *tz);
                    return stale_snapshot;
                }
            }
        }

        Self::schedule_quota_refresh(provider, timezone, *tz);
        QuotaSnapshot {
            status: "refreshing".to_string(),
            source: format!("{} 额度后台查询中", spec.name),
            last_updated: Self::cache_timestamp(tz),
            ..Default::default()
        }
    }

    fn load_provider_data(provider: &str, tz: &Tz, force: bool) -> ProviderData {
        let timezone = tz.to_string();
        let Some(spec) = ProviderRegistry::get(provider).copied() else {
            return Self::loading_provider_data(
                provider,
                provider,
                "unknown",
                Vec::new(),
                "Provider 未注册",
                tz,
            );
        };
        let roots = (spec.source_roots)();
        if force {
            let parsed = (spec.collect_usage)(0, tz);
            Self::persist_provider(provider, &timezone, tz, &parsed);
            return parsed;
        }

        let fingerprint = cache::source_fingerprint(&roots);
        let period = cache::stat_period(tz);
        if let Some(mut cached) =
            cache::load_exact::<ProviderData>(provider, &timezone, &period, &fingerprint)
        {
            cached.source_health.message = format!("缓存命中：{}", cached.source_health.message);
            cached.source_health.last_attempt_at = Some(Self::cache_timestamp(tz));
            if !cached
                .source_health
                .capabilities
                .iter()
                .any(|capability| capability == "snapshot_cache")
            {
                cached
                    .source_health
                    .capabilities
                    .push("snapshot_cache".to_string());
            }
            return cached;
        }

        if let Some(cached) = cache::load_latest::<ProviderData>(provider, &timezone) {
            let key = format!("{provider}|{timezone}");
            let scheduled = Self::schedule_usage_refresh(provider, timezone, *tz);
            return if scheduled || Self::refresh_in_flight(&key) {
                Self::mark_refreshing(cached, tz, spec.name)
            } else {
                Self::mark_stale(cached, tz, spec.name)
            };
        }

        Self::schedule_usage_refresh(provider, timezone, *tz);
        Self::loading_provider_data(
            &format!("{provider}_sessions"),
            &format!("{} 会话", spec.name),
            spec.source_schema,
            roots
                .into_iter()
                .map(|path| path.display().to_string())
                .collect(),
            "首次扫描正在后台进行，完成后点击刷新即可看到完整数据",
            tz,
        )
    }

    fn load_codex_data(tz: &Tz, force: bool) -> ProviderData {
        Self::load_provider_data("codex", tz, force)
    }

    fn load_antigravity_data(tz: &Tz, force: bool) -> ProviderData {
        Self::load_provider_data("antigravity", tz, force)
    }

    /// Restore each provider's own archived daily rows before any cross-channel
    /// merge. If one provider has pruned a day to zero while the other still
    /// reports activity for that date, merging first would produce a non-zero
    /// partial row and incorrectly override the complete `all` archive.
    fn restore_provider_history(channel: &str, mut data: ProviderData, tz: &Tz) -> ProviderData {
        let snapshot = DashboardSnapshot {
            channel: channel.to_string(),
            quota: QuotaSnapshot::default(),
            quotas: HashMap::new(),
            tokens: std::mem::take(&mut data.tokens),
            daily_activities: std::mem::take(&mut data.daily_activities),
            models: Vec::new(),
            tasks: Vec::new(),
            projects: Vec::new(),
            skills_and_tools: Vec::new(),
            sources_health: Vec::new(),
            timestamp: String::new(),
        };
        let restored = history::reconcile(snapshot, &tz.to_string());
        data.tokens = restored.tokens;
        data.daily_activities = restored.daily_activities;
        data
    }

    pub fn build_snapshot(channel: &str, timezone: Option<String>) -> DashboardSnapshot {
        Self::build_snapshot_with_refresh(channel, timezone, false)
    }

    /// Map a refresh request onto per-provider force flags. A single channel
    /// only forces that provider; the other provider keeps its cached snapshot
    /// (normal non-force load). "all" forces both, preserving the original
    /// full-rescan semantics.
    fn refresh_force_for(channel: &str, provider: &str, force: bool) -> bool {
        if !force {
            return false;
        }
        matches!(channel, "all") || channel == provider
    }

    pub fn build_snapshot_with_refresh(
        channel: &str,
        timezone: Option<String>,
        force: bool,
    ) -> DashboardSnapshot {
        let tz = Self::resolve_tz(timezone.as_deref());
        // A refresh on a single channel only re-scans that provider; the other
        // provider keeps its cached snapshot instead of forcing a full rescan.
        let codex_force = Self::refresh_force_for(channel, "codex", force);
        let antigravity_force = Self::refresh_force_for(channel, "antigravity", force);
        let codex_quota = Self::load_quota("codex", &tz, codex_force);
        let antigravity_quota = Self::load_quota("antigravity", &tz, antigravity_force);
        let c_data = Self::load_codex_data(&tz, codex_force);
        let a_data = Self::load_antigravity_data(&tz, antigravity_force);

        let now_str = Utc::now()
            .with_timezone(&tz)
            .format("%Y-%m-%d %H:%M:%S")
            .to_string();

        let quota_available = codex_quota.status == "available";
        let quota_refreshing = codex_quota.status == "refreshing";
        let codex_quota_health = SourceHealthStatus {
            id: "codex_app_server".to_string(),
            name: "Codex Runtime / 额度".to_string(),
            status: if quota_refreshing {
                "refreshing"
            } else if quota_available && codex_quota.source.contains("app-server") {
                "healthy"
            } else if quota_available {
                "degraded"
            } else {
                "unavailable"
            }
            .to_string(),
            message: if quota_refreshing {
                "额度查询正在后台进行，界面不会等待 app-server 启动".to_string()
            } else if quota_available {
                format!("已连接 (数据源: {})", codex_quota.source)
            } else {
                "未读取到 Codex 实时额度，请确认已登录并运行过 Codex".to_string()
            },
            last_success_at: quota_available.then_some(codex_quota.last_updated.clone()),
            last_attempt_at: Some(now_str.clone()),
            error_code: (!quota_available && !quota_refreshing)
                .then_some("quota_unavailable".to_string()),
            source_schema: Some("Codex app-server rate limits".to_string()),
            locations: Vec::new(),
            capabilities: vec![
                "quota_windows".to_string(),
                "reset_time".to_string(),
                "background_refresh".to_string(),
            ],
            scanned_files: 0,
            parsed_sessions: 0,
        };
        let ag_quota_available = antigravity_quota.status == "available";
        let ag_quota_refreshing = antigravity_quota.status == "refreshing";
        let antigravity_quota_health = SourceHealthStatus {
            id: "antigravity_quota".to_string(),
            name: "Antigravity Runtime / 额度".to_string(),
            status: if ag_quota_refreshing {
                "refreshing"
            } else if ag_quota_available {
                "healthy"
            } else {
                "unavailable"
            }
            .to_string(),
            message: if ag_quota_refreshing {
                "正在查询本机 Antigravity 语言服务额度".to_string()
            } else if ag_quota_available {
                format!("已连接 (数据源: {})", antigravity_quota.source)
            } else {
                antigravity_quota.source.clone()
            },
            last_success_at: ag_quota_available.then_some(antigravity_quota.last_updated.clone()),
            last_attempt_at: Some(now_str.clone()),
            error_code: (!ag_quota_available && !ag_quota_refreshing)
                .then_some("quota_unavailable".to_string()),
            source_schema: Some("Antigravity language server RetrieveUserQuotaSummary".to_string()),
            locations: vec!["127.0.0.1 language_server".to_string()],
            capabilities: vec![
                "quota_windows".to_string(),
                "reset_time".to_string(),
                "background_refresh".to_string(),
            ],
            scanned_files: 0,
            parsed_sessions: 0,
        };
        let sources_health = vec![
            codex_quota_health,
            antigravity_quota_health,
            c_data.source_health.clone(),
            a_data.source_health.clone(),
        ];

        let snapshot = match channel {
            "antigravity" => DashboardSnapshot {
                channel: "antigravity".to_string(),
                quota: antigravity_quota.clone(),
                quotas: HashMap::from([("antigravity".to_string(), antigravity_quota)]),
                tokens: a_data.tokens,
                daily_activities: a_data.daily_activities,
                models: a_data.models,
                tasks: a_data.tasks,
                projects: a_data.projects,
                skills_and_tools: a_data.skills_and_tools,
                sources_health,
                timestamp: now_str,
            },
            "all" => {
                let c_data = Self::restore_provider_history("codex", c_data, &tz);
                let a_data = Self::restore_provider_history("antigravity", a_data, &tz);
                let merged = Self::merge_all(c_data, a_data, &tz);
                DashboardSnapshot {
                    channel: "all".to_string(),
                    quota: codex_quota.clone(),
                    quotas: HashMap::from([
                        ("codex".to_string(), codex_quota),
                        ("antigravity".to_string(), antigravity_quota),
                    ]),
                    tokens: merged.tokens,
                    daily_activities: merged.daily_activities,
                    models: merged.models,
                    tasks: merged.tasks,
                    projects: merged.projects,
                    skills_and_tools: merged.skills_and_tools,
                    sources_health,
                    timestamp: now_str,
                }
            }
            _ => DashboardSnapshot {
                channel: "codex".to_string(),
                quota: codex_quota.clone(),
                quotas: HashMap::from([("codex".to_string(), codex_quota)]),
                tokens: c_data.tokens,
                daily_activities: c_data.daily_activities,
                models: c_data.models,
                tasks: c_data.tasks,
                projects: c_data.projects,
                skills_and_tools: c_data.skills_and_tools,
                sources_health,
                timestamp: now_str,
            },
        };
        history::reconcile(snapshot, &tz.to_string())
    }

    fn merge_all(codex: ProviderData, antigravity: ProviderData, tz: &Tz) -> ProviderData {
        // Period buckets are recomputed from the merged daily rows below so the
        // "all" channel's today/week/month/all_time always equal the sum of its
        // own daily activities (single-source consistency), never a sum of two
        // independently-computed per-provider buckets.
        let mut daily_map: HashMap<String, (TokenBreakdown, f64, u64)> = HashMap::new();
        for d in &codex.daily_activities {
            let entry =
                daily_map
                    .entry(d.date.clone())
                    .or_insert((TokenBreakdown::default(), 0.0, 0));
            entry.0.add(&d.tokens);
            entry.1 += d.cost_usd;
            entry.2 += d.sessions;
        }
        for d in &antigravity.daily_activities {
            let entry =
                daily_map
                    .entry(d.date.clone())
                    .or_insert((TokenBreakdown::default(), 0.0, 0));
            entry.0.add(&d.tokens);
            entry.1 += d.cost_usd;
            entry.2 += d.sessions;
        }
        let mut merged_daily: Vec<DailyActivity> = daily_map
            .into_iter()
            .map(|(date, (tokens, cost_usd, sessions))| DailyActivity {
                date,
                tokens,
                cost_usd,
                sessions,
            })
            .collect();
        merged_daily.sort_by(|a, b| a.date.cmp(&b.date));
        let merged_tokens = history::recompute_periods(&merged_daily, tz);

        let mut model_map: HashMap<String, ModelUsage> = HashMap::new();
        for m in codex.models {
            model_map.insert(m.model_id.clone(), m);
        }
        for m in antigravity.models {
            if let Some(existing) = model_map.get_mut(&m.model_id) {
                existing.tokens.add(&m.tokens);
                existing.sessions += m.sessions;
                existing.turns += m.turns;
                existing.cost_usd += m.cost_usd;
                existing.pricing_status = match (existing.pricing_status.as_str(), m.pricing_status.as_str()) {
                    ("exact", "exact") => "exact".to_string(),
                    ("unpriced", "unpriced") => "unpriced".to_string(),
                    _ => "partial".to_string(),
                };
            } else {
                model_map.insert(m.model_id.clone(), m);
            }
        }
        let mut merged_models: Vec<ModelUsage> = model_map.into_values().collect();
        merged_models.sort_by_key(|m| std::cmp::Reverse(m.tokens.total));

        let mut merged_tasks = codex.tasks;
        merged_tasks.extend(antigravity.tasks);
        merged_tasks = group_tasks_by_project(merged_tasks);

        let mut proj_map: HashMap<String, ProjectRankingItem> = HashMap::new();
        for mut p in codex.projects {
            p.path = normalize_project_path(&p.path);
            proj_map.insert(p.path.clone(), p);
        }
        for mut p in antigravity.projects {
            p.path = normalize_project_path(&p.path);
            if let Some(existing) = proj_map.get_mut(&p.path) {
                let incoming_total = p.tokens.total;
                let existing_total = existing.tokens.total;
                existing.tokens.add(&p.tokens);
                existing.cost_usd += p.cost_usd;
                existing.sessions += p.sessions;
                if existing.last_active_at < p.last_active_at {
                    existing.last_active_at = p.last_active_at.clone();
                }
                // When both providers contribute equally, prefer the incoming
                // model so the merge result is consistent with the per-provider
                // account_project_model tie-breaking (which uses >=).
                if incoming_total >= existing_total {
                    existing.primary_model = p.primary_model;
                }
            } else {
                proj_map.insert(p.path.clone(), p);
            }
        }
        let mut merged_projects: Vec<ProjectRankingItem> = proj_map.into_values().collect();
        merged_projects.sort_by_key(|p| std::cmp::Reverse(p.tokens.total));
        for (i, p) in merged_projects.iter_mut().enumerate() {
            p.rank = i + 1;
        }

        let mut skill_map: HashMap<String, SkillAgg> = codex.skill_details;
        for (name, agg) in antigravity.skill_details {
            if let Some(existing) = skill_map.get_mut(&name) {
                existing.count += agg.count;
                existing.active_days.extend(agg.active_days);
                existing.project_paths.extend(agg.project_paths);
                if agg.last_used > existing.last_used {
                    existing.last_used = agg.last_used;
                }
            } else {
                skill_map.insert(name, agg);
            }
        }
        let mut merged_skills: Vec<SkillUsageItem> = skill_map
            .into_iter()
            .map(|(name, agg)| Self::skill_to_item(name, &agg, tz))
            .collect();
        merged_skills.sort_by_key(|s| std::cmp::Reverse(s.count));

        ProviderData {
            tokens: merged_tokens,
            daily_activities: merged_daily,
            models: merged_models,
            tasks: merged_tasks,
            projects: merged_projects,
            skills_and_tools: merged_skills,
            skill_details: HashMap::new(),
            session_count: codex.session_count + antigravity.session_count,
            source_health: SourceHealthStatus::default(),
        }
    }
}

/// Clears the in-flight marker on drop so a panicking background worker cannot
/// leave a key stuck forever (which would starve future refreshes).
struct InFlightGuard {
    key: String,
}

impl Drop for InFlightGuard {
    fn drop(&mut self) {
        Aggregator::finish_refresh(&self.key);
    }
}

#[cfg(test)]
mod tests {
    use super::{Aggregator, InFlightGuard};
    use crate::models::{
        DailyActivity, DashboardSnapshot, ProjectRankingItem, ProviderData, QuotaSnapshot,
        TokenBreakdown, TokenPeriods,
    };
    use std::collections::HashMap;
    use std::time::Duration;

    fn day(date: &str, total: u64) -> DailyActivity {
        DailyActivity {
            date: date.to_string(),
            tokens: TokenBreakdown::new(total, 0, 0),
            cost_usd: 0.0,
            sessions: u64::from(total > 0),
        }
    }

    fn snapshot(channel: &str, daily_activities: Vec<DailyActivity>) -> DashboardSnapshot {
        DashboardSnapshot {
            channel: channel.to_string(),
            quota: QuotaSnapshot::default(),
            quotas: HashMap::new(),
            tokens: TokenPeriods::default(),
            daily_activities,
            models: Vec::new(),
            tasks: Vec::new(),
            projects: Vec::new(),
            skills_and_tools: Vec::new(),
            sources_health: Vec::new(),
            timestamp: String::new(),
        }
    }

    fn project(path: &str, total: u64, model: &str) -> ProjectRankingItem {
        ProjectRankingItem {
            rank: 0,
            name: path.to_string(),
            path: path.to_string(),
            tokens: TokenBreakdown::new(total, 0, 0),
            cost_usd: 0.0,
            sessions: 1,
            last_active_at: "2026-08-19".to_string(),
            primary_model: model.to_string(),
        }
    }

    #[test]
    fn merge_all_picks_primary_model_from_larger_contributor() {
        let codex = ProviderData {
            tokens: TokenPeriods::default(),
            projects: vec![project(r"C:\Work\App", 10, "gpt-5.6")],
            ..Default::default()
        };
        let antigravity = ProviderData {
            tokens: TokenPeriods::default(),
            projects: vec![project("c:/Work/App", 40, "gemini-2.5-pro")],
            ..Default::default()
        };
        let merged = Aggregator::merge_all(codex, antigravity, &chrono_tz::Asia::Shanghai);
        assert_eq!(merged.projects.len(), 1);
        assert_eq!(merged.projects[0].tokens.total, 50);
        assert_eq!(merged.projects[0].primary_model, "gemini-2.5-pro");
    }

    #[test]
    fn forced_quota_failure_only_keeps_success_from_same_timezone() {
        assert!(Aggregator::should_keep_previous_quota(
            "unavailable",
            "available",
            "Asia/Shanghai",
            "Asia/Shanghai",
        ));
        assert!(!Aggregator::should_keep_previous_quota(
            "unavailable",
            "available",
            "UTC",
            "Asia/Shanghai",
        ));
        assert!(!Aggregator::should_keep_previous_quota(
            "available",
            "available",
            "Asia/Shanghai",
            "Asia/Shanghai",
        ));
    }

    #[test]
    fn all_history_restores_each_provider_before_same_day_merge() {
        let _lock = crate::storage::history::test_lock().lock().unwrap();
        let root = std::env::temp_dir().join(format!(
            "codexuu-aggregator-history-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&root).expect("create history root");
        std::env::set_var("CODExUU_HISTORY_DIR", &root);
        let timezone = "Asia/Shanghai";
        let tz = chrono_tz::Asia::Shanghai;
        let date = "2026-08-17";

        // Seed complete per-provider history and the previous all-channel sum.
        crate::storage::history::reconcile(snapshot("codex", vec![day(date, 10)]), timezone);
        crate::storage::history::reconcile(snapshot("antigravity", vec![day(date, 5)]), timezone);
        crate::storage::history::reconcile(snapshot("all", vec![day(date, 15)]), timezone);

        // Codex has since pruned that day (zero-fill), while Antigravity still
        // observes a real non-zero row for the same date.
        let codex = ProviderData {
            daily_activities: vec![day(date, 0)],
            ..Default::default()
        };
        let antigravity = ProviderData {
            daily_activities: vec![day(date, 5)],
            ..Default::default()
        };

        let codex = Aggregator::restore_provider_history("codex", codex, &tz);
        let antigravity = Aggregator::restore_provider_history("antigravity", antigravity, &tz);
        let merged = Aggregator::merge_all(codex, antigravity, &tz);
        let final_snapshot =
            crate::storage::history::reconcile(snapshot("all", merged.daily_activities), timezone);

        assert_eq!(final_snapshot.tokens.all_time.total, 15);
        assert_eq!(final_snapshot.daily_activities[0].tokens.total, 15);

        std::env::remove_var("CODExUU_HISTORY_DIR");
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn in_flight_marker_is_cleared_when_worker_panics() {
        let key = "codex|panic-test-tz";
        assert!(Aggregator::start_refresh(key, Duration::ZERO));
        assert!(Aggregator::refresh_in_flight(key));

        // A panicking worker still releases the in-flight marker on unwind.
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let _guard = InFlightGuard {
                key: key.to_string(),
            };
            panic!("worker boom");
        }));
        assert!(result.is_err());
        assert!(!Aggregator::refresh_in_flight(key));
    }

    #[test]
    fn in_flight_marker_cleared_on_normal_completion() {
        let key = "codex|completion-test-tz";
        assert!(Aggregator::start_refresh(key, Duration::ZERO));
        {
            let _guard = InFlightGuard {
                key: key.to_string(),
            };
        }
        assert!(!Aggregator::refresh_in_flight(key));
    }

    #[test]
    fn single_channel_force_does_not_force_other_provider() {
        // Force refresh on codex only: codex is forced, antigravity is not.
        assert!(Aggregator::refresh_force_for("codex", "codex", true));
        assert!(!Aggregator::refresh_force_for("codex", "antigravity", true));
        // Force refresh on antigravity only.
        assert!(!Aggregator::refresh_force_for("antigravity", "codex", true));
        assert!(Aggregator::refresh_force_for(
            "antigravity",
            "antigravity",
            true
        ));
    }

    #[test]
    fn all_channel_forces_both_and_non_force_never_forces() {
        // "all" preserves full-rescan semantics for both providers.
        assert!(Aggregator::refresh_force_for("all", "codex", true));
        assert!(Aggregator::refresh_force_for("all", "antigravity", true));
        // Non-force refresh never forces either provider.
        assert!(!Aggregator::refresh_force_for("codex", "codex", false));
        assert!(!Aggregator::refresh_force_for(
            "codex",
            "antigravity",
            false
        ));
        assert!(!Aggregator::refresh_force_for("all", "codex", false));
        assert!(!Aggregator::refresh_force_for("all", "antigravity", false));
    }
}

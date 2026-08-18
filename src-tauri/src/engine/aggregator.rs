use std::collections::HashMap;

use chrono::{DateTime, Utc};
use chrono_tz::Tz;

use crate::models::{
    DailyActivity, DashboardSnapshot, ModelUsage, ProjectRankingItem, ProviderData, QuotaSnapshot,
    SkillAgg, SkillUsageItem, SourceHealthStatus, TokenBreakdown,
};
use crate::providers::antigravity::AntigravityProvider;
use crate::providers::codex::CodexProvider;

pub struct Aggregator;

impl Aggregator {
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

    pub fn build_snapshot(channel: &str, timezone: Option<String>) -> DashboardSnapshot {
        let tz = Self::resolve_tz(timezone.as_deref());
        let codex_quota = CodexProvider::fetch_quota(&tz);
        let c_data = CodexProvider::parse_all_sessions(30, &tz);
        let a_data = AntigravityProvider::parse_all(30, &tz);

        let now_str = Utc::now()
            .with_timezone(&tz)
            .format("%Y-%m-%d %H:%M:%S")
            .to_string();

        let sources_health = vec![
            SourceHealthStatus {
                id: "codex_app_server".to_string(),
                name: "Codex Runtime / 额度".to_string(),
                status: if codex_quota.status == "available" {
                    "healthy".to_string()
                } else if codex_quota.status == "unavailable" {
                    "unavailable".to_string()
                } else {
                    "degraded".to_string()
                },
                message: if codex_quota.status == "available" {
                    format!("已连接 (数据源: {})", codex_quota.source)
                } else {
                    "未读取到 Codex 实时额度，请确认已登录并运行过 Codex".to_string()
                },
                last_success_at: Some(codex_quota.last_updated.clone()),
            },
            SourceHealthStatus {
                id: "codex_sessions".to_string(),
                name: "Codex 本机会话日志".to_string(),
                status: if c_data.session_count > 0 {
                    "healthy".to_string()
                } else {
                    "degraded".to_string()
                },
                message: if c_data.session_count > 0 {
                    format!("已索引 {} 个会话", c_data.session_count)
                } else {
                    "未找到 Codex 本机会话".to_string()
                },
                last_success_at: Some(now_str.clone()),
            },
            SourceHealthStatus {
                id: "antigravity_db".to_string(),
                name: "Antigravity SQLite/Brain".to_string(),
                status: if a_data.session_count > 0 {
                    "healthy".to_string()
                } else {
                    "degraded".to_string()
                },
                message: if a_data.session_count > 0 {
                    format!("已解析 {} 个会话记录", a_data.session_count)
                } else {
                    "未找到可解析的 Antigravity 会话".to_string()
                },
                last_success_at: Some(now_str.clone()),
            },
        ];

        match channel {
            "antigravity" => DashboardSnapshot {
                channel: "antigravity".to_string(),
                quota: QuotaSnapshot {
                    status: "not_applicable".to_string(),
                    source: "Antigravity 无官方额度限制".to_string(),
                    last_updated: now_str.clone(),
                    ..Default::default()
                },
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
                let merged = Self::merge_all(c_data, a_data, &tz);
                DashboardSnapshot {
                    channel: "all".to_string(),
                    quota: codex_quota,
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
                quota: codex_quota,
                tokens: c_data.tokens,
                daily_activities: c_data.daily_activities,
                models: c_data.models,
                tasks: c_data.tasks,
                projects: c_data.projects,
                skills_and_tools: c_data.skills_and_tools,
                sources_health,
                timestamp: now_str,
            },
        }
    }

    fn merge_all(codex: ProviderData, antigravity: ProviderData, tz: &Tz) -> ProviderData {
        // Merge tokens
        let mut merged_tokens = codex.tokens.clone();
        merged_tokens.today.add(&antigravity.tokens.today);
        merged_tokens.week.add(&antigravity.tokens.week);
        merged_tokens.month.add(&antigravity.tokens.month);
        merged_tokens.all_time.add(&antigravity.tokens.all_time);

        // Merge daily activities
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

        // Merge models
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
                if existing.pricing_status != "exact" || m.pricing_status != "exact" {
                    existing.pricing_status = if existing.pricing_status == "unpriced"
                        && m.pricing_status == "unpriced"
                    {
                        "unpriced".to_string()
                    } else {
                        "partial".to_string()
                    };
                }
            } else {
                model_map.insert(m.model_id.clone(), m);
            }
        }
        let mut merged_models: Vec<ModelUsage> = model_map.into_values().collect();
        merged_models.sort_by_key(|m| std::cmp::Reverse(m.tokens.total));

        // Merge tasks
        let mut merged_tasks = codex.tasks;
        merged_tasks.extend(antigravity.tasks);
        merged_tasks.sort_by(|a, b| b.updated_at.cmp(&a.updated_at));

        // Merge projects by real path
        let mut proj_map: HashMap<String, ProjectRankingItem> = HashMap::new();
        for p in codex.projects {
            proj_map.insert(p.path.clone(), p);
        }
        for p in antigravity.projects {
            if let Some(existing) = proj_map.get_mut(&p.path) {
                existing.tokens.add(&p.tokens);
                existing.cost_usd += p.cost_usd;
                existing.sessions += p.sessions;
                if existing.last_active_at < p.last_active_at {
                    existing.last_active_at = p.last_active_at;
                }
                if p.tokens.total > existing.tokens.total {
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

        // Merge skills/tools with union of active days and projects.
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
        }
    }
}

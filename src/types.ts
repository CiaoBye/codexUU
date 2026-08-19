export interface TokenBreakdown {
  uncached_input: number;
  cached_input: number;
  output: number;
  total: number;
}

export interface TokenPeriods {
  today: TokenBreakdown;
  week: TokenBreakdown;
  month: TokenBreakdown;
  all_time: TokenBreakdown;
}

export interface QuotaFamily {
  id: string;
  label: string;
  five_hour_used_ratio: number | null;
  five_hour_remaining_ratio: number | null;
  five_hour_reset_at: string | null;
  seven_day_used_ratio: number | null;
  seven_day_remaining_ratio: number | null;
  seven_day_reset_at: string | null;
  has_five_hour: boolean;
  has_seven_day: boolean;
}

export interface QuotaSnapshot {
  five_hour_used_ratio: number | null;
  five_hour_remaining_ratio: number | null;
  five_hour_reset_at: string | null;
  seven_day_used_ratio: number | null;
  seven_day_remaining_ratio: number | null;
  seven_day_reset_at: string | null;
  has_five_hour: boolean;
  has_seven_day: boolean;
  source: string;
  status: string;
  last_updated: string;
  families: QuotaFamily[];
}

export interface ModelUsage {
  model_id: string;
  reasoning_effort: string | null;
  tokens: TokenBreakdown;
  sessions: number;
  turns: number;
  cost_usd: number;
  pricing_status: string;
}

export interface DailyActivity {
  date: string;
  tokens: TokenBreakdown;
  cost_usd: number;
  sessions: number;
}

export interface TaskItem {
  id: string;
  project_name: string;
  project_path: string;
  title: string;
  status: 'running' | 'pending' | 'scheduled' | 'completed';
  updated_at: string;
  thread_count: number;
  channel: string;
}

export interface ProjectRankingItem {
  rank: number;
  name: string;
  path: string;
  tokens: TokenBreakdown;
  cost_usd: number;
  sessions: number;
  last_active_at: string;
  primary_model: string;
}

export interface SkillUsageItem {
  name: string;
  kind: 'skill' | 'tool';
  count: number;
  active_days: number;
  project_count: number;
  last_used_at: string;
}

export interface SourceHealthStatus {
  id: string;
  name: string;
  status: 'healthy' | 'degraded' | 'stale' | 'refreshing' | 'unavailable';
  message: string;
  last_success_at: string | null;
  last_attempt_at: string | null;
  error_code: string | null;
  source_schema: string | null;
  locations: string[];
  capabilities: string[];
  scanned_files: number;
  parsed_sessions: number;
}

export interface DashboardSnapshot {
  channel: 'codex' | 'antigravity' | 'all';
  quota: QuotaSnapshot;
  tokens: TokenPeriods;
  daily_activities: DailyActivity[];
  models: ModelUsage[];
  tasks: TaskItem[];
  projects: ProjectRankingItem[];
  skills_and_tools: SkillUsageItem[];
  sources_health: SourceHealthStatus[];
  timestamp: string;
}

export interface AppSettings {
  schema_version: number;
  theme: 'dark' | 'light' | 'system';
  language: 'zh-CN' | 'en';
  quota_mode: 'used' | 'remaining';
  timezone: string;
  global_shortcut: string;
  always_on_top: boolean;
  close_to_tray: boolean;
  start_at_login: boolean;
  widget_enabled: boolean;
  widget_style: 'ring' | 'capsule' | 'tracks' | 'disc' | 'gauge';
  widget_scale: number;
  default_channel: 'codex' | 'antigravity' | 'all';
}

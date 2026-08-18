import { DashboardSnapshot, AppSettings } from './types';

// Check if running inside Tauri environment
export const isTauri = (): boolean => {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
};

// Safe invoke wrapper
async function invokeTauri<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  if (isTauri()) {
    const { invoke } = await import('@tauri-apps/api/core');
    return await invoke<T>(cmd, args);
  }
  throw new Error(`Tauri environment not detected for command ${cmd}`);
}

// Default mock data for standalone UI development and test mode
export const MOCK_SNAPSHOT: DashboardSnapshot = {
  channel: 'codex',
  quota: {
    five_hour_used_ratio: 0.28,
    five_hour_remaining_ratio: 0.72,
    five_hour_reset_at: '19:45',
    seven_day_used_ratio: 0.47,
    seven_day_remaining_ratio: 0.53,
    seven_day_reset_at: '08/21 14:30',
    has_five_hour: true,
    has_seven_day: true,
    source: 'app-server (实时)',
    status: 'available',
    last_updated: '2026-08-17 16:20:00',
  },
  tokens: {
    today: { uncached_input: 1_240_000, cached_input: 8_120_000, output: 680_000, total: 10_040_000 },
    week: { uncached_input: 4_850_000, cached_input: 32_100_000, output: 2_450_000, total: 39_400_000 },
    month: { uncached_input: 18_200_000, cached_input: 115_000_000, output: 9_800_000, total: 143_000_000 },
    all_time: { uncached_input: 65_400_000, cached_input: 420_000_000, output: 36_200_000, total: 521_600_000 },
  },
  daily_activities: [
    { date: '2026-08-11', tokens: { uncached_input: 800000, cached_input: 4500000, output: 350000, total: 5650000 }, cost_usd: 11.2, sessions: 12 },
    { date: '2026-08-12', tokens: { uncached_input: 950000, cached_input: 5200000, output: 420000, total: 6570000 }, cost_usd: 13.5, sessions: 15 },
    { date: '2026-08-13', tokens: { uncached_input: 1100000, cached_input: 6800000, output: 510000, total: 8410000 }, cost_usd: 16.8, sessions: 18 },
    { date: '2026-08-14', tokens: { uncached_input: 1300000, cached_input: 8200000, output: 640000, total: 10140000 }, cost_usd: 20.4, sessions: 22 },
    { date: '2026-08-15', tokens: { uncached_input: 720000, cached_input: 4100000, output: 310000, total: 5130000 }, cost_usd: 9.8, sessions: 10 },
    { date: '2026-08-16', tokens: { uncached_input: 1050000, cached_input: 7100000, output: 580000, total: 8730000 }, cost_usd: 17.5, sessions: 19 },
    { date: '2026-08-17', tokens: { uncached_input: 1240000, cached_input: 8120000, output: 680000, total: 10040000 }, cost_usd: 20.1, sessions: 24 },
  ],
  models: [
    { model_id: 'gpt-4o', reasoning_effort: null, tokens: { uncached_input: 45000000, cached_input: 290000000, output: 25000000, total: 360000000 }, sessions: 48, turns: 420, cost_usd: 725.0, pricing_status: 'exact' },
    { model_id: 'o3-mini', reasoning_effort: 'high', tokens: { uncached_input: 12000000, cached_input: 85000000, output: 6500000, total: 103500000 }, sessions: 22, turns: 180, cost_usd: 88.5, pricing_status: 'exact' },
    { model_id: 'claude-3-5-sonnet-20241022', reasoning_effort: null, tokens: { uncached_input: 5400000, cached_input: 32000000, output: 3200000, total: 40600000 }, sessions: 15, turns: 95, cost_usd: 73.8, pricing_status: 'exact' },
    { model_id: 'gemini-3.7-flash', reasoning_effort: null, tokens: { uncached_input: 3000000, cached_input: 13000000, output: 1500000, total: 17500000 }, sessions: 8, turns: 62, cost_usd: 0.92, pricing_status: 'exact' },
  ],
  tasks: [
    { id: 'task-1', project_name: 'CodexUU', project_path: 'C:/Users/Ayuan/Documents/Vibe/CodexUU', title: '按照规划完成架构重构并进行相关测试', status: 'running', updated_at: '16:20', thread_count: 1, channel: 'antigravity' },
    { id: 'task-2', project_name: 'CodexUU', project_path: 'C:/Users/Ayuan/Documents/Vibe/CodexUU', title: '项目审计与合规分析', status: 'completed', updated_at: '15:08', thread_count: 1, channel: 'antigravity' },
    { id: 'task-3', project_name: 'VibeStudio', project_path: 'C:/Users/Ayuan/Documents/Vibe/VibeStudio', title: '修复 Windows 原生窗口拖拽抖动', status: 'pending', updated_at: '13:40', thread_count: 2, channel: 'codex' },
    { id: 'task-4', project_name: 'CodexUU', project_path: 'C:/Users/Ayuan/Documents/Vibe/CodexUU', title: '定时全量数据索引快照', status: 'scheduled', updated_at: '12:00', thread_count: 1, channel: 'codex' },
  ],
  projects: [
    { rank: 1, name: 'CodexUU', path: 'C:/Users/Ayuan/Documents/Vibe/CodexUU', tokens: { uncached_input: 35000000, cached_input: 240000000, output: 19000000, total: 294000000 }, cost_usd: 577.5, sessions: 42, last_active_at: '16:20', primary_model: 'gpt-4o' },
    { rank: 2, name: 'VibeStudio', path: 'C:/Users/Ayuan/Documents/Vibe/VibeStudio', tokens: { uncached_input: 18000000, cached_input: 110000000, output: 9500000, total: 137500000 }, cost_usd: 240.2, sessions: 21, last_active_at: '13:40', primary_model: 'o3-mini' },
    { rank: 3, name: 'AgentCore', path: 'C:/Users/Ayuan/Documents/Vibe/AgentCore', tokens: { uncached_input: 12400000, cached_input: 70000000, output: 7700000, total: 90100000 }, cost_usd: 70.4, sessions: 14, last_active_at: '08/15 17:12', primary_model: 'claude-3-5-sonnet' },
  ],
  skills_and_tools: [
    { name: 'run_command', kind: 'tool', count: 540, active_days: 18, project_count: 5, last_used_at: '16:20' },
    { name: 'view_file', kind: 'tool', count: 480, active_days: 18, project_count: 5, last_used_at: '16:18' },
    { name: 'replace_file_content', kind: 'tool', count: 320, active_days: 16, project_count: 4, last_used_at: '16:15' },
    { name: 'write_to_file', kind: 'tool', count: 210, active_days: 15, project_count: 4, last_used_at: '16:10' },
    { name: 'grep_search', kind: 'tool', count: 185, active_days: 14, project_count: 5, last_used_at: '15:55' },
    { name: 'antigravity-guide', kind: 'skill', count: 42, active_days: 8, project_count: 2, last_used_at: '14:20' },
    { name: 'agy-customizations', kind: 'skill', count: 28, active_days: 6, project_count: 2, last_used_at: '11:15' },
  ],
  sources_health: [
    { id: 'codex_app_server', name: 'Codex Runtime / 额度', status: 'healthy', message: '已连接 (app-server stdio)', last_success_at: '16:20:00' },
    { id: 'codex_sessions', name: 'Codex 本机会话日志', status: 'healthy', message: '已索引 77 个会话', last_success_at: '16:20:00' },
    { id: 'antigravity_db', name: 'Antigravity SQLite/Brain', status: 'healthy', message: '已解析 2 个会话数据库', last_success_at: '16:20:00' },
  ],
  timestamp: '2026-08-17 16:20:00',
};

// Empty snapshot used before real data arrives, so failures never display fake numbers.
export const EMPTY_SNAPSHOT: DashboardSnapshot = {
  channel: 'codex',
  quota: {
    five_hour_used_ratio: null,
    five_hour_remaining_ratio: null,
    five_hour_reset_at: null,
    seven_day_used_ratio: null,
    seven_day_remaining_ratio: null,
    seven_day_reset_at: null,
    has_five_hour: false,
    has_seven_day: false,
    source: '',
    status: 'unavailable',
    last_updated: '',
  },
  tokens: {
    today: { uncached_input: 0, cached_input: 0, output: 0, total: 0 },
    week: { uncached_input: 0, cached_input: 0, output: 0, total: 0 },
    month: { uncached_input: 0, cached_input: 0, output: 0, total: 0 },
    all_time: { uncached_input: 0, cached_input: 0, output: 0, total: 0 },
  },
  daily_activities: [],
  models: [],
  tasks: [],
  projects: [],
  skills_and_tools: [],
  sources_health: [],
  timestamp: '',
};

export const DEFAULT_SETTINGS: AppSettings = {
  schema_version: 1,
  theme: 'dark',
  language: 'zh-CN',
  quota_mode: 'used',
  timezone: 'Asia/Shanghai',
  global_shortcut: 'Ctrl+U',
  always_on_top: false,
  close_to_tray: true,
  start_at_login: false,
  widget_enabled: true,
  widget_style: 'ring',
  widget_scale: 1.0,
  default_channel: 'codex',
};

export async function fetchDashboardSnapshot(channel: string = 'codex', timezone?: string): Promise<DashboardSnapshot> {
  if (isTauri()) {
    return await invokeTauri<DashboardSnapshot>('get_dashboard_snapshot', { channel, timezone });
  }
  // Standalone UI development / tests: use deterministic mock data.
  return { ...MOCK_SNAPSHOT, channel };
}

export async function fetchSettings(): Promise<AppSettings> {
  if (isTauri()) {
    return await invokeTauri<AppSettings>('get_settings');
  }
  return DEFAULT_SETTINGS;
}

export async function updateSettings(settings: AppSettings): Promise<AppSettings> {
  if (isTauri()) {
    return await invokeTauri<AppSettings>('save_settings', { settings });
  }
  return settings;
}

export async function triggerRefresh(scope: string = 'all'): Promise<DashboardSnapshot> {
  if (isTauri()) {
    return await invokeTauri<DashboardSnapshot>('refresh_data', { scope });
  }
  return MOCK_SNAPSHOT;
}

export async function exportData(format: string, channel: string): Promise<string> {
  if (isTauri()) {
    return await invokeTauri<string>('export_data', { format, channel });
  }
  return '{"status": "exported"}';
}

export async function setWidgetVisible(visible: boolean): Promise<void> {
  if (isTauri()) {
    await invokeTauri('set_widget_visible', { visible });
  }
}

export async function setWidgetStyle(style: string, scale: number): Promise<void> {
  if (isTauri()) {
    await invokeTauri('set_widget_style', { style, scale });
  }
}

export async function showMainWindow(): Promise<void> {
  try {
    await invokeTauri('show_main_window');
  } catch {}
}

export async function minimizeMainWindow(): Promise<void> {
  try {
    await invokeTauri('minimize_main_window');
  } catch {}
}

export async function closeMainWindow(): Promise<void> {
  try {
    await invokeTauri('close_main_window');
  } catch {}
}

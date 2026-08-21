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
    families: [],
  },
  quotas: {},
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

export async function fetchDashboardSnapshot(
  channel: DashboardSnapshot['channel'] = 'codex',
  timezone?: string,
): Promise<DashboardSnapshot> {
  if (isTauri()) {
    return await invokeTauri<DashboardSnapshot>('get_dashboard_snapshot', { channel, timezone });
  }
  return { ...EMPTY_SNAPSHOT, channel };
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

export async function triggerRefresh(
  scope: DashboardSnapshot['channel'] = 'all',
): Promise<DashboardSnapshot> {
  if (isTauri()) {
    return await invokeTauri<DashboardSnapshot>('refresh_data', { scope });
  }
  return { ...EMPTY_SNAPSHOT, channel: scope };
}

export async function exportData(format: string, channel: string): Promise<string> {
  if (isTauri()) {
    return await invokeTauri<string>('export_data', { format, channel });
  }
  throw new Error(`Tauri environment not detected for command export_data`);
}

export async function setWidgetVisible(visible: boolean): Promise<void> {
  if (isTauri()) {
    await invokeTauri('toggle_desktop_widget', { visible });
  }
}

export async function setWidgetStyle(style: string, scale: number): Promise<void> {
  if (isTauri()) {
    await invokeTauri('set_widget_style', { style, scale });
  }
}

export async function showMainWindow(): Promise<void> {
  if (isTauri()) await invokeTauri('show_main_window');
}

export async function minimizeMainWindow(): Promise<void> {
  if (isTauri()) await invokeTauri('minimize_main_window');
}

export async function closeMainWindow(): Promise<void> {
  if (isTauri()) await invokeTauri('close_main_window');
}

export async function isMainWindowMaximized(): Promise<boolean> {
  if (isTauri()) {
    return await invokeTauri<boolean>('is_main_window_maximized');
  }
  return false;
}

export async function toggleMaximizeMainWindow(): Promise<boolean> {
  if (isTauri()) {
    return await invokeTauri<boolean>('toggle_maximize_main_window');
  }
  return false;
}

export function startWindowDrag(event: { button: number; target: EventTarget | null }): void {
  if (event.button !== 0 || !isTauri()) return;
  const target = event.target as HTMLElement | null;
  if (target?.closest('[data-no-drag]')) return;
  void import('@tauri-apps/api/window').then(({ getCurrentWindow }) => {
    void getCurrentWindow().startDragging();
  });
}

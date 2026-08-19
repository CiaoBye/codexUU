import React, { useState, useEffect } from 'react';
import { DashboardSnapshot, AppSettings } from './types';
import {
  fetchDashboardSnapshot,
  fetchSettings,
  triggerRefresh,
  updateSettings,
  minimizeMainWindow,
  toggleMaximizeMainWindow,
  closeMainWindow,
  DEFAULT_SETTINGS,
  EMPTY_SNAPSHOT,
  isTauri,
  isMainWindowMaximized,
} from './api';
import { readCachedSnapshot, writeCachedSnapshot } from './lib/snapshotCache';
import { createLatestWins, LatestWinsGuard, RequestToken } from './lib/requestGuard';
import { nextTabId, prevTabId, isTabListNavKey } from './lib/rovingTabs';
import { TopNav } from './components/layout/TopNav';
import { QuotaCompass } from './components/dashboard/QuotaCompass';
import { TokenMetricCards } from './components/dashboard/TokenMetricCards';
import { TaskBoardTab } from './components/tabs/TaskBoardTab';
import { UsageTrendsTab } from './components/tabs/UsageTrendsTab';
import { ProjectRankingTab } from './components/tabs/ProjectRankingTab';
import { SkillUsageTab } from './components/tabs/SkillUsageTab';
import { SettingsModal } from './components/settings/SettingsModal';
import { DesktopStatusWidget } from './components/floating/DesktopStatusWidget';
import {
  ListTodo,
  TrendingUp,
  Award,
  Wrench,
} from 'lucide-react';

function applyTheme(theme: string) {
  const root = document.documentElement;
  if (theme === 'light') {
    root.classList.add('light');
  } else if (theme === 'dark') {
    root.classList.remove('light');
  } else {
    const prefersLight = window.matchMedia('(prefers-color-scheme: light)').matches;
    root.classList.toggle('light', prefersLight);
  }
}

function effectiveTheme(theme: string): 'dark' | 'light' {
  if (theme === 'light') return 'light';
  if (theme === 'dark') return 'dark';
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

// A stable latest-wins guard shared across all async snapshot fetch paths, so
// ordering is tracked across renders without resetting on every re-render.
function useLatestWinsRef(): React.MutableRefObject<LatestWinsGuard> {
  const ref = React.useRef<LatestWinsGuard | null>(null);
  if (ref.current === null) ref.current = createLatestWins();
  return ref as React.MutableRefObject<LatestWinsGuard>;
}

export const App: React.FC = () => {
  // Check if this window is the floating desktop widget
  const isWidgetWindow = typeof window !== 'undefined' && window.location.hash === '#widget';

  const [snapshot, setSnapshot] = useState<DashboardSnapshot>(
    () => readCachedSnapshot('codex') ?? EMPTY_SNAPSHOT,
  );
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [activeChannel, setActiveChannel] = useState<DashboardSnapshot['channel']>('codex');
  const [activeTab, setActiveTab] = useState<'tasks' | 'trends' | 'projects' | 'skills'>('tasks');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isMaximized, setIsMaximized] = useState(false);
  const snapshotReady = Boolean(snapshot.timestamp);

  // Latest-wins guard: across init, channel switches, refresh, timezone
  // refetch and widget polling, only the newest request may commit its result;
  // slower stale responses are dropped so a snapshot never lands out of order.
  const orderingRef = useLatestWinsRef();

  // Apply theme whenever settings.theme changes, and follow OS changes for system mode.
  useEffect(() => {
    applyTheme(settings.theme);
    if (settings.theme === 'system') {
      const mq = window.matchMedia('(prefers-color-scheme: light)');
      const handler = () => applyTheme('system');
      mq.addEventListener('change', handler);
      return () => mq.removeEventListener('change', handler);
    }
  }, [settings.theme]);

  // Persist the snapshot, but only under its own channel key, so a later
  // channel is never re-read as the current channel on the next open.
  useEffect(() => {
    writeCachedSnapshot(snapshot);
  }, [snapshot]);

  // Commit a freshly fetched snapshot to the UI if it is still the latest
  // request, keeping activeChannel and snapshot.channel consistent so the
  // visible data always belongs to the selected channel.
  const commitSnapshot = React.useCallback(
    (token: RequestToken, snap: DashboardSnapshot, nextChannel?: DashboardSnapshot['channel']) => {
      token.commit(() => {
        const channel = snap.channel ?? nextChannel;
        setActiveChannel(channel);
        setSnapshot(snap);
        setIsRefreshing(false);
        setError(null);
      });
    },
    [],
  );

  // Load initial settings and snapshot
  useEffect(() => {
    if (isWidgetWindow) return;
    const token = orderingRef.current.next();
    async function init() {
      try {
        const s = await fetchSettings();
        // Settings are not channel-ordered: they must always land even if the
        // user switched channels while settings were loading (otherwise the
        // app would be stuck on DEFAULT_SETTINGS for the whole session).
        setSettings(s);
        // The default-channel selection and cached first frame are gated by the
        // latest-wins token so a stale init never overrides a user channel
        // switch that happened during startup.
        token.commit(() => {
          const channel = s.default_channel || 'codex';
          setActiveChannel(channel);
          // First frame: show this channel's own cache (never another channel's),
          // then the live fetch replaces it.
          const cached = readCachedSnapshot(channel);
          if (cached) {
            setSnapshot(cached);
            setError(null);
          }
        });
        const snap = await fetchDashboardSnapshot(s.default_channel || 'codex', s.timezone);
        commitSnapshot(token, snap);
      } catch (err) {
        token.commit(() => {
          setError(`初始化失败：${err instanceof Error ? err.message : String(err)}`);
          setIsRefreshing(false);
        });
      }
    }
    void init();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isWidgetWindow]);

  // The widget is a separate webview. Refresh its settings and snapshot so
  // style/scale/quota changes made in the main window become visible without
  // restarting the desktop widget.
  useEffect(() => {
    if (!isWidgetWindow) return;
    let disposed = false;
    let refreshInFlight = false;
    const refreshWidget = async () => {
      if (refreshInFlight || disposed) return;
      refreshInFlight = true;
      const token = orderingRef.current.next();
      try {
        const currentSettings = await fetchSettings();
        if (disposed || !currentSettings.widget_enabled) return;
        token.commit(() => {
          setSettings(currentSettings);
          setActiveChannel(currentSettings.default_channel || 'codex');
        });
        const currentSnapshot = await fetchDashboardSnapshot(
          currentSettings.default_channel || 'codex',
          currentSettings.timezone,
        );
        commitSnapshot(token, currentSnapshot);
      } catch (err) {
        token.commit(() => {
          if (!disposed) setError(`悬浮窗刷新失败：${err instanceof Error ? err.message : String(err)}`);
        });
      } finally {
        refreshInFlight = false;
      }
    };
    void refreshWidget();
    const timer = window.setInterval(refreshWidget, 60_000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isWidgetWindow]);

  const handleWindowCommand = async (command: () => Promise<void>, label: string) => {
    try {
      await command();
    } catch (err) {
      setError(`${label}失败：${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const handleToggleMaximize = async () => {
    try {
      const maximized = await toggleMaximizeMainWindow();
      setIsMaximized(maximized);
    } catch (err) {
      setError(`最大化窗口失败：${err instanceof Error ? err.message : String(err)}`);
    }
  };

  // Handle Channel Change
  const handleChannelChange = async (ch: string) => {
    const nextChannel = ch as DashboardSnapshot['channel'];
    const token = orderingRef.current.next();
    // Optimistically switch the selected channel so the UI reflects intent
    // immediately; only the latest switch may commit the fetched snapshot.
    token.commit(() => {
      setActiveChannel(nextChannel);
      setIsRefreshing(true);
      // First frame uses this channel's own cached data, never another channel's.
      const cached = readCachedSnapshot(nextChannel);
      if (cached) setSnapshot(cached);
    });
    try {
      const snap = await fetchDashboardSnapshot(nextChannel, settings.timezone);
      commitSnapshot(token, snap, nextChannel);
    } catch (err) {
      token.commit(() => {
        setError(`切换渠道失败：${err instanceof Error ? err.message : String(err)}`);
        setIsRefreshing(false);
      });
    }
  };

  // Handle Refresh
  const handleRefresh = async () => {
    const token = orderingRef.current.next();
    token.commit(() => setIsRefreshing(true));
    try {
      const snap = await triggerRefresh(activeChannel);
      commitSnapshot(token, snap, activeChannel);
    } catch (err) {
      token.commit(() => {
        setError(`刷新失败：${err instanceof Error ? err.message : String(err)}`);
        setIsRefreshing(false);
      });
    }
  };

  // Handle Theme Toggle (persists immediately)
  const handleToggleTheme = async () => {
    const current = effectiveTheme(settings.theme);
    const next: 'light' | 'dark' = current === 'dark' ? 'light' : 'dark';
    const updated: AppSettings = { ...settings, theme: next };
    setSettings(updated);
    applyTheme(next);
    try {
      await updateSettings(updated);
    } catch (err) {
      setError(`主题设置保存失败：${err instanceof Error ? err.message : String(err)}`);
    }
  };

  // Handle Toggle Quota Mode (persists immediately)
  const handleToggleQuotaMode = async () => {
    const nextMode: 'used' | 'remaining' = settings.quota_mode === 'used' ? 'remaining' : 'used';
    const updated: AppSettings = { ...settings, quota_mode: nextMode };
    setSettings(updated);
    try {
      await updateSettings(updated);
    } catch (err) {
      setError(`额度口径设置保存失败：${err instanceof Error ? err.message : String(err)}`);
    }
  };

  // Roving-tabindex navigation for the dashboard tablist: arrow keys / Home /
  // End move the active tab and focus, keeping only the selected tab in the
  // sequential tab order.
  const dashboardTabIds = ['tasks', 'trends', 'projects', 'skills'];
  const handleDashboardTabKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (!isTabListNavKey(event.key)) return;
    event.preventDefault();
    const current = activeTab;
    const next = event.key === 'ArrowRight'
      ? nextTabId(dashboardTabIds, current)
      : event.key === 'ArrowLeft'
        ? prevTabId(dashboardTabIds, current)
        : event.key === 'Home'
          ? dashboardTabIds[0]
          : dashboardTabIds[dashboardTabIds.length - 1];
    setActiveTab(next as typeof activeTab);
    document.getElementById(`dashboard-tab-${next}`)?.focus();
  };

  useEffect(() => {
    if (isWidgetWindow || !isTauri()) {
      return;
    }
    let cancelled = false;
    const syncMaximized = async () => {
      try {
        const maximized = await isMainWindowMaximized();
        if (!cancelled) {
          setIsMaximized(maximized);
        }
      } catch {
        // Keep the last known maximize state if the native query fails.
      }
    };
    const onResize = () => {
      void syncMaximized();
    };
    void syncMaximized();
    window.addEventListener('resize', onResize);
    return () => {
      cancelled = true;
      window.removeEventListener('resize', onResize);
    };
  }, [isWidgetWindow]);

  // If floating widget window mode, render only widget
  if (isWidgetWindow) {
    return (
      <>
        {error && (
          <div role="alert" className="px-2 py-1 text-[10px] text-red-500">
            {error}
          </div>
        )}
        <DesktopStatusWidget
          quota={snapshot.quota}
          tokens={snapshot.tokens}
          style={settings.widget_style}
          scale={settings.widget_scale}
          quotaMode={settings.quota_mode}
          onToggleQuotaMode={handleToggleQuotaMode}
        />
      </>
    );
  }

  const tabs: Array<{ id: 'tasks' | 'trends' | 'projects' | 'skills'; label: string; icon: typeof ListTodo }> = [
    { id: 'tasks', label: '今日任务', icon: ListTodo },
    { id: 'trends', label: '用量趋势', icon: TrendingUp },
    { id: 'projects', label: '项目排行', icon: Award },
    { id: 'skills', label: 'Skill & 工具', icon: Wrench },
  ];

  const hasUsageData = snapshot.tokens.all_time.total > 0
    || snapshot.daily_activities.length > 0
    || snapshot.models.length > 0
    || snapshot.projects.length > 0
    || snapshot.tasks.length > 0;
  const needsFirstRunHint = snapshot.sources_health.length > 0
    && !hasUsageData
    && snapshot.sources_health.some((source) => source.status === 'unavailable' || source.status === 'degraded');

  return (
    <div className="h-full w-full overflow-hidden bg-[var(--bg-canvas)] text-[var(--text-primary)] flex flex-col">
      <TopNav
        channel={activeChannel}
        onChannelChange={handleChannelChange}
        isRefreshing={isRefreshing}
        onRefresh={handleRefresh}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onOpenExport={() => setActiveTab('projects')}
        theme={settings.theme}
        effectiveTheme={effectiveTheme(settings.theme)}
        onToggleTheme={handleToggleTheme}
        onMinimize={() => handleWindowCommand(minimizeMainWindow, '最小化窗口')}
        onToggleMaximize={() => void handleToggleMaximize()}
        onClose={() => handleWindowCommand(closeMainWindow, '关闭窗口')}
        isMaximized={isMaximized}
        lastUpdated={snapshot.timestamp}
      />

      <main className="dashboard-main flex-1 min-h-0 overflow-hidden px-3 py-1.5 flex flex-col gap-1.5 w-full" data-no-drag>
        {error && (
          <div role="alert" aria-live="assertive" className="px-4 py-2 rounded-xl bg-red-500/10 border border-red-500/30 text-red-500 text-xs flex items-center justify-between gap-3">
            <span>{error}</span>
            <button
              type="button"
              onClick={() => void handleRefresh()}
              disabled={isRefreshing}
              className="shrink-0 px-2 py-1 rounded-lg border border-red-400/30 hover:bg-red-500/10 disabled:opacity-50"
            >
              重试
            </button>
          </div>
        )}

        {needsFirstRunHint && (
          <div role="status" className="px-4 py-3 rounded-xl ui-chip-warning text-xs flex items-center justify-between gap-3">
            <div>
              <div className="font-semibold">尚未发现可统计的本地会话</div>
              <div className="text-xs text-[var(--text-secondary)] mt-0.5">
                首次运行时请先使用 Codex 或 Antigravity 产生会话；如果你确认已有数据，请打开“数据源诊断”查看路径和错误原因。
              </div>
            </div>
            <button
              type="button"
              onClick={() => setIsSettingsOpen(true)}
              className="shrink-0 px-2.5 py-1.5 rounded-lg border border-current/30 hover:bg-[color-mix(in_srgb,var(--warning)_12%,transparent)]"
            >
              查看诊断
            </button>
          </div>
        )}

        {/* Row 1: Quota Compass + 4 Token Metric Cards */}
        <div className="dashboard-hero">
          <QuotaCompass
            quota={snapshot.quota}
            quotaMode={settings.quota_mode}
            onToggleQuotaMode={handleToggleQuotaMode}
          />
          <TokenMetricCards tokens={snapshot.tokens} unavailable={!snapshotReady} />
        </div>

        {/* Row 2: In-place Tab Switcher Bar */}
        <div className="flex items-stretch border-b border-[var(--border-default)] shrink-0">
          <div role="tablist" aria-label="仪表盘内容" className="flex items-stretch w-full">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  id={`dashboard-tab-${tab.id}`}
                  tabIndex={isActive ? 0 : -1}
                  aria-selected={isActive}
                  // aria-controls only points at a panel that is rendered —
                  // only the active tab's panel exists in the DOM.
                  {...(isActive ? { 'aria-controls': `dashboard-panel-${tab.id}` } : {})}
                  onClick={() => setActiveTab(tab.id)}
                  onKeyDown={handleDashboardTabKeyDown}
                  className={`flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 text-xs font-semibold transition-all border-b-2 -mb-px ${
                    isActive
                      ? 'text-[var(--accent-brand)] border-[var(--accent-brand)]'
                      : 'text-[var(--text-secondary)] border-transparent hover:text-[var(--text-primary)]'
                  }`}
                >
                  <Icon aria-hidden="true" className="w-3.5 h-3.5" />
                  <span>{tab.label}</span>
                  {tab.id === 'tasks' && snapshot.tasks.length > 0 && (
                    <span className="text-[11px] font-mono text-[var(--text-muted)]">
                      {snapshot.tasks.length}
                    </span>
                  )}
                  {tab.id === 'projects' && snapshot.projects.length > 0 && (
                    <span className="text-[11px] font-mono text-[var(--text-muted)]">
                      {snapshot.projects.length}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Row 3: Tab Content Panels */}
        <div id={`dashboard-panel-${activeTab}`} role="tabpanel" aria-labelledby={`dashboard-tab-${activeTab}`} className="flex-1 min-h-0 h-full overflow-hidden">
          {activeTab === 'tasks' && <TaskBoardTab tasks={snapshot.tasks} />}
          {activeTab === 'trends' && (
            <UsageTrendsTab
              dailyActivities={snapshot.daily_activities}
              models={snapshot.models}
              today={snapshot.timestamp.slice(0, 10)}
            />
          )}
          {activeTab === 'projects' && (
            <ProjectRankingTab
              projects={snapshot.projects}
              channel={activeChannel}
            />
          )}
          {activeTab === 'skills' && (
            <SkillUsageTab skillsAndTools={snapshot.skills_and_tools} />
          )}
        </div>
      </main>

      {/* Settings Modal */}
      <SettingsModal
        key={isSettingsOpen ? 'open' : 'closed'}
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        settings={settings}
        onSaveSettings={async (s) => {
          const timezoneChanged = s.timezone !== settings.timezone;
          setSettings(s);
          applyTheme(s.theme);
          if (timezoneChanged) {
            const token = orderingRef.current.next();
            token.commit(() => setIsRefreshing(true));
            try {
              const snap = await fetchDashboardSnapshot(activeChannel, s.timezone);
              commitSnapshot(token, snap, activeChannel);
            } catch (err) {
              token.commit(() => {
                setError(`时区切换后刷新失败：${err instanceof Error ? err.message : String(err)}`);
                setIsRefreshing(false);
              });
            }
          }
        }}
        sourcesHealth={snapshot.sources_health}
        onRefreshSources={handleRefresh}
        isRefreshing={isRefreshing}
      />
    </div>
  );
};

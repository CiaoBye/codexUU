import React, { useState, useEffect } from 'react';
import { DashboardSnapshot, AppSettings } from './types';
import {
  fetchDashboardSnapshot,
  fetchSettings,
  triggerRefresh,
  updateSettings,
  minimizeMainWindow,
  closeMainWindow,
  DEFAULT_SETTINGS,
  EMPTY_SNAPSHOT,
} from './api';
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

export const App: React.FC = () => {
  // Check if this window is the floating desktop widget
  const isWidgetWindow = typeof window !== 'undefined' && window.location.hash === '#widget';

  const [snapshot, setSnapshot] = useState<DashboardSnapshot>(EMPTY_SNAPSHOT);
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [activeChannel, setActiveChannel] = useState<DashboardSnapshot['channel']>('codex');
  const [activeTab, setActiveTab] = useState<'tasks' | 'trends' | 'projects' | 'skills'>('tasks');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snapshotReady = Boolean(snapshot.timestamp);

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

  // Load initial settings and snapshot
  useEffect(() => {
    async function init() {
      if (isWidgetWindow) return;
      try {
        const s = await fetchSettings();
        setSettings(s);
        setActiveChannel(s.default_channel || 'codex');

        const snap = await fetchDashboardSnapshot(s.default_channel || 'codex', s.timezone);
        setSnapshot(snap);
        setError(null);
      } catch (err) {
        setError(`初始化失败：${err instanceof Error ? err.message : String(err)}`);
      }
    }
    init();
  }, []);

  // The widget is a separate webview. Refresh its settings and snapshot so
  // style/scale/quota changes made in the main window become visible without
  // restarting the desktop widget.
  useEffect(() => {
    if (!isWidgetWindow) return;
    let disposed = false;
    const refreshWidget = async () => {
      try {
        const currentSettings = await fetchSettings();
        if (!currentSettings.widget_enabled) return;
        const currentSnapshot = await fetchDashboardSnapshot(
          currentSettings.default_channel || 'codex',
          currentSettings.timezone,
        );
        if (!disposed) {
          setSettings(currentSettings);
          setActiveChannel(currentSettings.default_channel || 'codex');
          setSnapshot(currentSnapshot);
        }
      } catch (err) {
        if (!disposed) setError(`悬浮窗刷新失败：${err instanceof Error ? err.message : String(err)}`);
      }
    };
    void refreshWidget();
    const timer = window.setInterval(refreshWidget, 60_000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [isWidgetWindow]);

  const handleWindowCommand = async (command: () => Promise<void>, label: string) => {
    try {
      await command();
    } catch (err) {
      setError(`${label}失败：${err instanceof Error ? err.message : String(err)}`);
    }
  };

  // Handle Channel Change
  const handleChannelChange = async (ch: string) => {
    const nextChannel = ch as DashboardSnapshot['channel'];
    const previousChannel = activeChannel;
    setActiveChannel(nextChannel);
    setIsRefreshing(true);
    try {
      const snap = await fetchDashboardSnapshot(nextChannel, settings.timezone);
      setSnapshot(snap);
      setError(null);
    } catch (err) {
      setActiveChannel(previousChannel);
      setError(`切换渠道失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsRefreshing(false);
    }
  };

  // Handle Refresh
  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      const snap = await triggerRefresh(activeChannel);
      setSnapshot(snap);
      setError(null);
    } catch (err) {
      setError(`刷新失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsRefreshing(false);
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
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-[var(--bg-canvas)] text-[var(--text-primary)]">
      {/* 1. Global Top Navigation */}
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
        onClose={() => handleWindowCommand(closeMainWindow, '关闭窗口')}
        lastUpdated={snapshot.timestamp}
      />

      {/* Main Content Area */}
      <main className="dashboard-main flex-1 overflow-y-auto p-4 space-y-4 max-w-7xl mx-auto w-full">
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
          <div role="status" className="px-4 py-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs flex items-center justify-between gap-3">
            <div>
              <div className="font-semibold text-amber-300">尚未发现可统计的本地会话</div>
              <div className="text-[11px] text-[var(--text-secondary)] mt-0.5">
                首次运行时请先使用 Codex 或 Antigravity 产生会话；如果你确认已有数据，请打开“数据源诊断”查看路径和错误原因。
              </div>
            </div>
            <button
              type="button"
              onClick={() => setIsSettingsOpen(true)}
              className="shrink-0 px-2.5 py-1.5 rounded-lg border border-amber-400/30 text-amber-300 hover:bg-amber-500/10"
            >
              查看诊断
            </button>
          </div>
        )}

        {/* Row 1: Quota Compass + 4 Token Metric Cards */}
        <div className="dashboard-hero">
          {/* Quota Compass (Scheme C) */}
          <div className="min-w-0">
            <QuotaCompass
              quota={snapshot.quota}
              quotaMode={settings.quota_mode}
              onToggleQuotaMode={handleToggleQuotaMode}
            />
          </div>

          {/* 4 Token Metric Cards */}
          <div className="min-w-0">
            <TokenMetricCards tokens={snapshot.tokens} unavailable={!snapshotReady} />
          </div>
        </div>

        {/* Row 2: In-place Tab Switcher Bar */}
        <div className="flex items-center justify-between border-b border-[var(--border-default)] pb-1">
          <div role="tablist" aria-label="仪表盘内容" className="flex items-center gap-1">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  id={`dashboard-tab-${tab.id}`}
                  aria-selected={isActive}
                  aria-controls={`dashboard-panel-${tab.id}`}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all relative ${
                    isActive
                      ? 'text-teal-400 bg-teal-500/10 border border-teal-500/30 shadow-sm'
                      : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-card)]'
                  }`}
                >
                  <Icon aria-hidden="true" className="w-4 h-4" />
                  <span>{tab.label}</span>
                  {tab.id === 'tasks' && snapshot.tasks.length > 0 && (
                    <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-[var(--bg-subtle)] font-mono text-[var(--text-muted)]">
                      {snapshot.tasks.length}
                    </span>
                  )}
                  {tab.id === 'projects' && snapshot.projects.length > 0 && (
                    <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-[var(--bg-subtle)] font-mono text-[var(--text-muted)]">
                      {snapshot.projects.length}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Quick channel info badge */}
          <div className="text-[11px] text-[var(--text-muted)] flex items-center gap-2">
            <span>当前时区: <strong className="font-mono text-[var(--text-primary)]">{settings.timezone}</strong></span>
          </div>
        </div>

        {/* Row 3: Tab Content Panels */}
        <div id={`dashboard-panel-${activeTab}`} role="tabpanel" aria-labelledby={`dashboard-tab-${activeTab}`} className="min-h-[360px]">
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
            setIsRefreshing(true);
            try {
              const snap = await fetchDashboardSnapshot(activeChannel, s.timezone);
              setSnapshot(snap);
              setError(null);
            } catch (err) {
              setError(`时区切换后刷新失败：${err instanceof Error ? err.message : String(err)}`);
            } finally {
              setIsRefreshing(false);
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

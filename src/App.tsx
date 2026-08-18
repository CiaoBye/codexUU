import React, { useState, useEffect } from 'react';
import { DashboardSnapshot, AppSettings } from './types';
import {
  fetchDashboardSnapshot,
  fetchSettings,
  triggerRefresh,
  updateSettings,
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
  const [activeChannel, setActiveChannel] = useState<string>('codex');
  const [activeTab, setActiveTab] = useState<'tasks' | 'trends' | 'projects' | 'skills'>('tasks');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  // Handle Channel Change
  const handleChannelChange = async (ch: string) => {
    setActiveChannel(ch);
    setIsRefreshing(true);
    try {
      const snap = await fetchDashboardSnapshot(ch, settings.timezone);
      setSnapshot(snap);
      setError(null);
    } catch (err) {
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
      <DesktopStatusWidget
        quota={snapshot.quota}
        tokens={snapshot.tokens}
        style={settings.widget_style}
        scale={settings.widget_scale}
        quotaMode={settings.quota_mode}
        onToggleQuotaMode={handleToggleQuotaMode}
      />
    );
  }

  const tabs = [
    { id: 'tasks', label: '今日任务', icon: ListTodo },
    { id: 'trends', label: '用量趋势', icon: TrendingUp },
    { id: 'projects', label: '项目排行', icon: Award },
    { id: 'skills', label: 'Skill & 工具', icon: Wrench },
  ];

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-[var(--bg-canvas)] text-[var(--text-primary)] select-none">
      {/* 1. Global Top Navigation */}
      <TopNav
        channel={activeChannel}
        onChannelChange={handleChannelChange}
        isRefreshing={isRefreshing}
        onRefresh={handleRefresh}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onOpenExport={() => setActiveTab('projects')}
        theme={settings.theme}
        onToggleTheme={handleToggleTheme}
        lastUpdated={snapshot.timestamp}
      />

      {/* Main Content Area */}
      <main className="flex-1 overflow-y-auto p-4 space-y-4 max-w-7xl mx-auto w-full">
        {error && (
          <div className="px-4 py-2 rounded-xl bg-red-500/10 border border-red-500/30 text-red-300 text-xs">
            {error}
          </div>
        )}

        {/* Row 1: Quota Compass + 4 Token Metric Cards */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
          {/* Quota Compass (Scheme C) */}
          <div className="lg:col-span-4 xl:col-span-3">
            <QuotaCompass
              quota={snapshot.quota}
              quotaMode={settings.quota_mode}
              onToggleQuotaMode={handleToggleQuotaMode}
            />
          </div>

          {/* 4 Token Metric Cards */}
          <div className="lg:col-span-8 xl:col-span-9">
            <TokenMetricCards tokens={snapshot.tokens} />
          </div>
        </div>

        {/* Row 2: In-place Tab Switcher Bar */}
        <div className="flex items-center justify-between border-b border-[var(--border-default)] pb-1">
          <div className="flex items-center gap-1">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all relative ${
                    isActive
                      ? 'text-teal-400 bg-teal-500/10 border border-teal-500/30 shadow-sm'
                      : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-card)]'
                  }`}
                >
                  <Icon className="w-4 h-4" />
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
        <div className="min-h-[420px]">
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
        onSaveSettings={(s) => {
          setSettings(s);
          applyTheme(s.theme);
        }}
        sourcesHealth={snapshot.sources_health}
      />
    </div>
  );
};

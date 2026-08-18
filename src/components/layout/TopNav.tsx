import React from 'react';
import {
  RefreshCw,
  Settings as SettingsIcon,
  Download,
  Minus,
  X,
  Sun,
  Moon,
  Sparkles,
  Bot,
  Layers,
} from 'lucide-react';
import { minimizeMainWindow, closeMainWindow } from '../../api';

interface TopNavProps {
  channel: string;
  onChannelChange: (ch: string) => void;
  isRefreshing: boolean;
  onRefresh: () => void;
  onOpenSettings: () => void;
  onOpenExport: () => void;
  theme: string;
  onToggleTheme: () => void;
  lastUpdated?: string;
}

export const TopNav: React.FC<TopNavProps> = ({
  channel,
  onChannelChange,
  isRefreshing,
  onRefresh,
  onOpenSettings,
  onOpenExport,
  theme,
  onToggleTheme,
  lastUpdated,
}) => {
  const channels = [
    { id: 'codex', label: 'Codex 官方', icon: Bot },
    { id: 'antigravity', label: 'Antigravity', icon: Sparkles },
    { id: 'all', label: '全部聚合', icon: Layers },
  ];

  return (
    <header className="h-14 border-b border-[var(--border-default)] bg-[var(--bg-elevated)] px-4 flex items-center justify-between select-none shrink-0" data-tauri-drag-region>
      {/* Left: Brand + Title */}
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-teal-500/10 border border-teal-500/30 flex items-center justify-center text-teal-400 font-bold text-base shadow-sm">
          UU
        </div>
        <div className="flex flex-col">
          <div className="flex items-center gap-1.5">
            <span className="font-bold text-sm tracking-tight text-[var(--text-primary)]">CodexUU</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-teal-500/15 text-teal-400 font-medium border border-teal-500/20">
              v{__APP_VERSION__}
            </span>
          </div>
          <span className="text-[11px] text-[var(--text-muted)] -mt-0.5">本地 AI 编程控制台</span>
        </div>
      </div>

      {/* Center: Channel Selector Segmented Control */}
      <div className="flex items-center p-1 bg-[var(--bg-card)] border border-[var(--border-default)] rounded-xl shadow-inner">
        {channels.map((c) => {
          const Icon = c.icon;
          const isActive = channel === c.id;
          return (
            <button
              key={c.id}
              onClick={() => onChannelChange(c.id)}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                isActive
                  ? 'bg-teal-500/15 text-teal-300 border border-teal-500/30 shadow-sm'
                  : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)]'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{c.label}</span>
            </button>
          );
        })}
      </div>

      {/* Right: Actions + Window controls */}
      <div className="flex items-center gap-2">
        {lastUpdated && (
          <span className="text-[11px] text-[var(--text-muted)] hidden md:inline-block mr-1">
            更新于 {lastUpdated.slice(11, 16)}
          </span>
        )}

        {/* Refresh button */}
        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          title="刷新数据"
          className="p-1.5 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-card)] border border-transparent hover:border-[var(--border-default)] transition"
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin text-teal-400' : ''}`} />
        </button>

        {/* Export button */}
        <button
          onClick={onOpenExport}
          title="导出用量与项目"
          className="p-1.5 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-card)] border border-transparent hover:border-[var(--border-default)] transition"
        >
          <Download className="w-4 h-4" />
        </button>

        {/* Theme toggle */}
        <button
          onClick={onToggleTheme}
          title={theme === 'dark' ? '切换为浅色主题' : '切换为深色主题'}
          className="p-1.5 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-card)] border border-transparent hover:border-[var(--border-default)] transition"
        >
          {theme === 'dark' ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-indigo-400" />}
        </button>

        {/* Settings button */}
        <button
          onClick={onOpenSettings}
          title="设置"
          className="p-1.5 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-card)] border border-transparent hover:border-[var(--border-default)] transition"
        >
          <SettingsIcon className="w-4 h-4" />
        </button>

        <div className="h-4 w-px bg-[var(--border-default)] mx-1" />

        {/* Window controls */}
        <button
          onClick={() => minimizeMainWindow()}
          title="最小化"
          className="p-1.5 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-card)] transition"
        >
          <Minus className="w-4 h-4" />
        </button>
        <button
          onClick={() => closeMainWindow()}
          title="关闭"
          className="p-1.5 rounded-lg text-[var(--text-secondary)] hover:text-red-400 hover:bg-red-500/10 transition"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
};

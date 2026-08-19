import React from 'react';
import {
  Settings as SettingsIcon,
  Award,
  Minus,
  X,
  Sun,
  Moon,
  Sparkles,
  Bot,
  Layers,
  Maximize2,
  Minimize2,
} from 'lucide-react';
import { startWindowDrag } from '../../api';

interface TopNavProps {
  channel: string;
  onChannelChange: (ch: string) => void;
  isRefreshing: boolean;
  onRefresh: () => void;
  onOpenSettings: () => void;
  onOpenExport: () => void;
  theme: string;
  effectiveTheme: 'dark' | 'light';
  onToggleTheme: () => void;
  onMinimize: () => void | Promise<void>;
  onToggleMaximize: () => void | Promise<void>;
  onClose: () => void | Promise<void>;
  isMaximized?: boolean;
  lastUpdated?: string;
}

const iconButtonClass =
  'p-1.5 min-w-8 min-h-8 rounded-md text-[var(--text-primary)] hover:bg-[var(--bg-card)] border border-transparent hover:border-[var(--border-default)] transition';

function stopWindowDrag(event: React.MouseEvent) {
  event.stopPropagation();
}

function BrandMark() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="28" height="28" className="w-7 h-7 rounded-lg shrink-0" aria-hidden="true">
      <defs>
        <linearGradient id="codexuu-brand-bg" x1="8" y1="6" x2="56" y2="58" gradientUnits="userSpaceOnUse">
          <stop stopColor="#147a76" />
          <stop offset="0.55" stopColor="#2c9f9b" />
          <stop offset="1" stopColor="#4d9fff" />
        </linearGradient>
        <linearGradient id="codexuu-brand-shine" x1="18" y1="18" x2="46" y2="48" gradientUnits="userSpaceOnUse">
          <stop stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#D7F4F2" />
        </linearGradient>
      </defs>
      <rect x="4" y="4" width="56" height="56" rx="17" fill="url(#codexuu-brand-bg)" />
      <path d="M17 27.5C20.5 18.2 32.2 14 41.3 18.2c4.4 2 7.6 5.5 9.2 9.6" fill="none" stroke="#CDEDEA" strokeWidth="3.4" strokeLinecap="round" opacity=".88" />
      <path d="M16.5 34.2C20 44 31.5 49 41.1 45.2c4.3-1.7 7.8-5 9.7-9.2" fill="none" stroke="#9ED7FF" strokeWidth="3.4" strokeLinecap="round" opacity=".74" />
      <path d="M21 27v8.2C21 42 25.5 46 32 46s11-4 11-10.8V27" fill="none" stroke="url(#codexuu-brand-shine)" strokeWidth="5" strokeLinecap="round" />
      <circle cx="50" cy="22" r="3.2" fill="#FFFFFF" />
      <circle cx="14.5" cy="39" r="2.3" fill="#DDF5FF" opacity=".95" />
    </svg>
  );
}

export const TopNav: React.FC<TopNavProps> = ({
  channel,
  onChannelChange,
  isRefreshing,
  onRefresh,
  onOpenSettings,
  onOpenExport,
  theme: _theme,
  effectiveTheme,
  onToggleTheme,
  onMinimize,
  onToggleMaximize,
  onClose,
  isMaximized = false,
  lastUpdated,
}) => {
  const channels = [
    { id: 'codex', label: 'Codex 官方', icon: Bot },
    { id: 'antigravity', label: 'Antigravity', icon: Sparkles },
    { id: 'all', label: '全部聚合', icon: Layers },
  ];

  return (
    <header
      className="h-12 border-b border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 flex items-center justify-between gap-3 select-none shrink-0"
      data-tauri-drag-region
      onMouseDown={startWindowDrag}
      onDoubleClick={(event) => {
        const target = event.target as HTMLElement;
        if (target.closest('[data-no-drag]')) return;
        void onToggleMaximize();
      }}
    >
      <div className="flex items-center gap-3 min-w-0">
        <BrandMark />
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="font-bold text-sm tracking-tight text-[var(--text-primary)]">CodexUU</span>
          <span className="text-[11px] px-1.5 py-0.5 rounded-full bg-[color-mix(in_srgb,var(--accent-brand)_16%,transparent)] text-[var(--accent-brand)] font-medium border border-[color-mix(in_srgb,var(--accent-brand)_28%,transparent)]">
            v{__APP_VERSION__}{import.meta.env.DEV ? '-dev' : ''}
          </span>
        </div>
        <div
          className="flex items-center p-0.5 bg-[var(--bg-card)] border border-[var(--border-default)] rounded-lg"
          data-no-drag
          data-tauri-drag-region="false"
          onMouseDown={stopWindowDrag}
        >
          {channels.map((c) => {
            const Icon = c.icon;
            const isActive = channel === c.id;
            return (
              <button
                key={c.id}
                type="button"
                aria-pressed={isActive}
                aria-label={`切换到${c.label}`}
                // Channel buttons stay enabled during a refresh so users can
                // switch quickly; the latest-wins guard drops stale responses.
                onClick={() => onChannelChange(c.id)}
                className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                  isActive
                    ? 'ui-selected'
                    : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)]'
                }`}
              >
                <Icon aria-hidden="true" className="w-3.5 h-3.5" />
                <span>{c.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div
        className="flex items-center gap-1.5"
        data-no-drag
        data-tauri-drag-region="false"
        onMouseDown={stopWindowDrag}
      >
        {lastUpdated && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={isRefreshing}
            aria-label="重新读取本地数据"
            aria-busy={isRefreshing}
            title="重新读取本地数据"
            className="text-[11px] font-mono text-[var(--text-muted)] hover:text-[var(--text-primary)] hidden md:inline-block mr-1 px-1.5 py-1 rounded-md"
          >
            {lastUpdated.slice(11, 16)}
          </button>
        )}

        <button type="button" onClick={onOpenExport} aria-label="打开项目排行" title="打开项目排行" className={iconButtonClass}>
          <Award aria-hidden="true" className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={onToggleTheme}
          aria-label={effectiveTheme === 'dark' ? '切换为浅色主题' : '切换为深色主题'}
          title={effectiveTheme === 'dark' ? '切换为浅色主题' : '切换为深色主题'}
          className={iconButtonClass}
        >
          {effectiveTheme === 'dark'
            ? <Sun aria-hidden="true" className="w-4 h-4 text-[var(--warning)]" />
            : <Moon aria-hidden="true" className="w-4 h-4 text-[var(--quota-7d)]" />}
        </button>
        <button type="button" onClick={onOpenSettings} aria-label="打开设置" title="设置" className={iconButtonClass}>
          <SettingsIcon aria-hidden="true" className="w-4 h-4" />
        </button>

        <div className="h-4 w-px bg-[var(--border-default)] mx-1" />

        <button type="button" onClick={onMinimize} aria-label="最小化窗口" title="最小化" className={iconButtonClass}>
          <Minus aria-hidden="true" className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => void onToggleMaximize()}
          aria-label={isMaximized ? '还原窗口' : '最大化窗口'}
          title={isMaximized ? '还原' : '最大化'}
          className={iconButtonClass}
        >
          {isMaximized ? <Minimize2 aria-hidden="true" className="w-4 h-4" /> : <Maximize2 aria-hidden="true" className="w-4 h-4" />}
        </button>
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭窗口"
          title="关闭"
          className="p-1.5 min-w-8 min-h-8 rounded-md text-[var(--text-secondary)] hover:text-[var(--danger)] hover:bg-[color-mix(in_srgb,var(--danger)_12%,transparent)] transition"
        >
          <X aria-hidden="true" className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
};

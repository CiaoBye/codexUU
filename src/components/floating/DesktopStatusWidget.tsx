import React from 'react';
import { QuotaSnapshot, TokenPeriods } from '../../types';
import { formatTokens } from '../dashboard/TokenMetricCards';
import { showMainWindow } from '../../api';

interface DesktopStatusWidgetProps {
  quota: QuotaSnapshot;
  tokens: TokenPeriods;
  style: 'ring' | 'capsule' | 'tracks' | 'disc' | 'gauge';
  scale: number;
  quotaMode: 'used' | 'remaining';
  onToggleQuotaMode: () => void;
}

export const DesktopStatusWidget: React.FC<DesktopStatusWidgetProps> = ({
  quota,
  tokens,
  style,
  scale,
  quotaMode,
  onToggleQuotaMode,
}) => {
  const isUsedMode = quotaMode === 'used';
  const ratio7d = isUsedMode
    ? quota.seven_day_used_ratio
    : quota.seven_day_remaining_ratio;
  const ratio5h = isUsedMode
    ? quota.five_hour_used_ratio
    : quota.five_hour_remaining_ratio;

  const pct7d = ratio7d == null ? null : Math.round(ratio7d * 100);
  const pct5h = ratio5h == null ? null : Math.round(ratio5h * 100);

  const handleClickCenter = (e: React.MouseEvent) => {
    e.stopPropagation();
    onToggleQuotaMode();
  };

  const handleDoubleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    void showMainWindow().catch((error) => console.error('显示主窗口失败', error));
  };

  // SVG Ring params
  const r7d = 36;
  const c7d = 2 * Math.PI * r7d;
  const off7d = ratio7d == null ? c7d : c7d * (1 - ratio7d);

  const r5h = 27;
  const c5h = 2 * Math.PI * r5h;
  const off5h = ratio5h == null ? c5h : c5h * (1 - ratio5h);
  const widgetTransformStyle: React.CSSProperties = {
    transform: `scale(${scale})`,
    transformOrigin: 'top left',
  };

  return (
    <div
      data-tauri-drag-region
      data-widget-scale={scale}
      role="group"
      aria-label="CodexUU 桌面状态悬浮窗"
      className="w-full h-full p-1.5 cursor-move font-sans flex items-start justify-start bg-transparent"
      onDoubleClick={handleDoubleClick}
      title="按住拖拽移动，双击还原主界面，点击中心切换已用/剩余"
    >
      {/* 1. Minimal Ring */}
      {style === 'ring' && (
        <div
          data-tauri-drag-region
          style={widgetTransformStyle}
          className="w-24 h-24 rounded-full bg-[var(--bg-elevated)]/95 backdrop-blur-xl border border-[var(--border-strong)] shadow-2xl flex items-center justify-center relative p-1"
        >
          <svg aria-hidden="true" width="84" height="84" className={`origin-center pointer-events-none ${isUsedMode ? 'rotate-90' : 'rotate-90 -scale-x-100'}`}>
            <circle cx="42" cy="42" r={r7d} fill="transparent" stroke="var(--border-default)" strokeWidth="6" opacity="0.4" />
            <circle cx="42" cy="42" r={r7d} fill="transparent" stroke="var(--quota-7d)" strokeWidth="6" strokeDasharray={c7d} strokeDashoffset={off7d} strokeLinecap="round" />
            {quota.has_five_hour && (
              <>
                <circle cx="42" cy="42" r={r5h} fill="transparent" stroke="var(--border-default)" strokeWidth="5" opacity="0.4" />
                <circle cx="42" cy="42" r={r5h} fill="transparent" stroke="var(--quota-5h)" strokeWidth="5" strokeDasharray={c5h} strokeDashoffset={off5h} strokeLinecap="round" />
              </>
            )}
          </svg>
          <button
            type="button"
            onClick={handleClickCenter}
            aria-label={`切换额度显示口径，当前为${isUsedMode ? '已用' : '剩余'}`}
            aria-pressed={!isUsedMode}
            className="absolute inset-0 flex flex-col items-center justify-center text-center cursor-pointer group z-10"
            title="点击切换 已用/剩余"
          >
            <span className="text-[11px] font-black text-purple-400 font-mono group-hover:scale-110 transition-transform">
              {pct7d == null ? '--' : `${pct7d}%`}
            </span>
            <span className="text-[8px] text-[var(--text-muted)] font-mono">
              {formatTokens(tokens.today.total)}
            </span>
          </button>
        </div>
      )}

      {/* 2. Status Capsule */}
      {style === 'capsule' && (
        <div
          data-tauri-drag-region
          style={widgetTransformStyle}
          className="w-56 h-12 rounded-full bg-[var(--bg-elevated)]/95 backdrop-blur-xl border border-[var(--border-strong)] shadow-2xl px-3 flex items-center justify-between"
        >
          <div data-tauri-drag-region className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleClickCenter}
              aria-label={`切换额度显示口径，当前为${isUsedMode ? '已用' : '剩余'}`}
              aria-pressed={!isUsedMode}
              className="w-8 h-8 rounded-full bg-purple-500/20 border border-purple-500/30 flex items-center justify-center text-[10px] font-bold text-purple-300 font-mono cursor-pointer hover:bg-purple-500/30 transition"
              title="点击切换 已用/剩余"
            >
              {pct7d == null ? '--' : `${pct7d}%`}
            </button>
            <div data-tauri-drag-region className="flex flex-col">
              <span data-tauri-drag-region className="text-[10px] font-bold text-[var(--text-primary)]">CodexUU</span>
              <span data-tauri-drag-region className="text-[9px] text-[var(--text-muted)]">{quota.seven_day_reset_at || '未知'}</span>
            </div>
          </div>
          <div data-tauri-drag-region className="text-right">
            <div data-tauri-drag-region className="text-xs font-bold font-mono text-teal-400">{formatTokens(tokens.today.total)}</div>
            <div data-tauri-drag-region className="text-[8px] text-[var(--text-muted)]">今日 Token</div>
          </div>
        </div>
      )}

      {/* 3. Dual Track Card */}
      {style === 'tracks' && (
        <button
          type="button"
          data-tauri-drag-region
          style={widgetTransformStyle}
          onClick={handleClickCenter}
          aria-label={`切换额度显示口径，当前为${isUsedMode ? '已用' : '剩余'}`}
          aria-pressed={!isUsedMode}
          className="w-60 bg-[var(--bg-elevated)]/95 backdrop-blur-xl border border-[var(--border-strong)] rounded-2xl p-2.5 shadow-2xl space-y-1.5 text-left cursor-pointer"
        >
          <div data-tauri-drag-region className="flex items-center justify-between text-[10px]">
            <span data-tauri-drag-region className="font-bold text-[var(--text-primary)]">额度状态</span>
            <span data-tauri-drag-region className="font-mono text-teal-400 font-bold">{formatTokens(tokens.today.total)}</span>
          </div>
          <div data-tauri-drag-region className="space-y-1 text-[9px]">
            <div data-tauri-drag-region className="flex items-center justify-between">
              <span data-tauri-drag-region className="text-purple-400">7D 额度</span>
              <span data-tauri-drag-region className="font-mono text-[var(--text-primary)]">{pct7d == null ? '--' : `${pct7d}%`}</span>
            </div>
            <div data-tauri-drag-region className="h-1.5 w-full bg-[var(--bg-subtle)] rounded-full overflow-hidden">
              <div style={{ width: `${pct7d ?? 0}%` }} className="h-full bg-purple-500 rounded-full" />
            </div>
            {quota.has_five_hour && (
              <>
                <div data-tauri-drag-region className="flex items-center justify-between">
                  <span data-tauri-drag-region className="text-blue-400">5H 额度</span>
                  <span data-tauri-drag-region className="font-mono text-[var(--text-primary)]">{pct5h == null ? '--' : `${pct5h}%`}</span>
                </div>
                <div data-tauri-drag-region className="h-1.5 w-full bg-[var(--bg-subtle)] rounded-full overflow-hidden">
                  <div style={{ width: `${pct5h ?? 0}%` }} className="h-full bg-blue-500 rounded-full" />
                </div>
              </>
            )}
          </div>
        </button>
      )}

      {/* 4. Info Disc */}
      {style === 'disc' && (
        <div
          data-tauri-drag-region
          style={widgetTransformStyle}
          className="w-28 h-28 rounded-full bg-[var(--bg-elevated)]/95 backdrop-blur-xl border border-[var(--border-strong)] shadow-2xl flex flex-col items-center justify-center p-2 text-center"
        >
          <button
            type="button"
            onClick={handleClickCenter}
            aria-label={`切换额度显示口径，当前为${isUsedMode ? '已用' : '剩余'}`}
            aria-pressed={!isUsedMode}
            className="cursor-pointer group"
            title="点击切换 已用/剩余"
          >
            <span className="text-xs font-black text-purple-400 font-mono group-hover:scale-110 inline-block transition">{pct7d == null ? '--' : `${pct7d}%`}</span>
            <span className="text-[9px] text-[var(--text-muted)] block">{isUsedMode ? '已用' : '剩余'}</span>
          </button>
          <div className="w-10 h-px bg-[var(--border-default)] my-1 pointer-events-none" />
          <span data-tauri-drag-region className="text-[10px] font-bold font-mono text-teal-400">{formatTokens(tokens.today.total)}</span>
          <span data-tauri-drag-region className="text-[8px] text-[var(--text-muted)]">今日用量</span>
        </div>
      )}

      {/* 5. Gauge Meter */}
      {style === 'gauge' && (
        <div
          data-tauri-drag-region
          style={widgetTransformStyle}
          className="w-56 h-16 rounded-2xl bg-[var(--bg-elevated)]/95 backdrop-blur-xl border border-[var(--border-strong)] shadow-2xl p-2 flex items-center justify-between"
        >
          <div data-tauri-drag-region className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleClickCenter}
              aria-label={`切换额度显示口径，当前为${isUsedMode ? '已用' : '剩余'}`}
              aria-pressed={!isUsedMode}
              className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/30 flex flex-col items-center justify-center cursor-pointer hover:bg-purple-500/20 transition"
              title="点击切换 已用/剩余"
            >
              <span className="text-xs font-black text-purple-400 font-mono">{pct7d == null ? '--' : `${pct7d}%`}</span>
              <span className="text-[7px] text-purple-300">7D</span>
            </button>
            <div data-tauri-drag-region className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/30 flex flex-col items-center justify-center">
              <span className="text-xs font-black text-blue-400 font-mono">{pct5h == null ? '--' : `${pct5h}%`}</span>
              <span className="text-[7px] text-blue-300">5H</span>
            </div>
          </div>
          <div data-tauri-drag-region className="text-right">
            <div data-tauri-drag-region className="text-xs font-mono font-bold text-teal-400">{formatTokens(tokens.today.total)}</div>
            <div data-tauri-drag-region className="text-[9px] text-[var(--text-muted)]">当日 Token</div>
          </div>
        </div>
      )}
    </div>
  );
};

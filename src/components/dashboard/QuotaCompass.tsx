import React from 'react';
import { QuotaSnapshot } from '../../types';
import { AlertCircle } from 'lucide-react';

interface QuotaCompassProps {
  quota: QuotaSnapshot;
  quotaMode: 'used' | 'remaining';
  onToggleQuotaMode: () => void;
}

export const QuotaCompass: React.FC<QuotaCompassProps> = ({
  quota,
  quotaMode,
  onToggleQuotaMode,
}) => {
  const isUsedMode = quotaMode === 'used';

  // Extract ratios (null when no real data is available)
  const ratio5h = isUsedMode
    ? quota.five_hour_used_ratio
    : quota.five_hour_remaining_ratio;
  const ratio7d = isUsedMode
    ? quota.seven_day_used_ratio
    : quota.seven_day_remaining_ratio;

  const pct5h = ratio5h == null ? null : Math.round(ratio5h * 100);
  const pct7d = ratio7d == null ? null : Math.round(ratio7d * 100);

  // SVG parameters tuned for perfect fit without clipping
  const size = 140;
  const center = size / 2;
  const strokeWidth = 8.5;

  const rOuter = 56;
  const cOuter = 2 * Math.PI * rOuter;
  const offsetOuter = ratio7d == null ? cOuter : cOuter * (1 - ratio7d);

  const rInner = 42;
  const cInner = 2 * Math.PI * rInner;
  const offsetInner = ratio5h == null ? cInner : cInner * (1 - ratio5h);

  const isUnavailable = quota.status === 'unavailable'
    || quota.status === 'not_applicable'
    || (!quota.has_seven_day && !quota.has_five_hour);
  const healthDotClass = isUnavailable
    ? 'bg-red-400'
    : quota.status === 'degraded' || quota.status === 'stale' || quota.status === 'refreshing'
      ? 'bg-amber-400'
      : 'bg-emerald-400 animate-pulse';
  const ringDirectionClass = isUsedMode ? 'rotate-90' : 'rotate-90 -scale-x-100';

  return (
    <div className="bg-[var(--bg-card)] border border-[var(--border-default)] rounded-xl p-3.5 flex flex-col justify-between shadow-sm relative overflow-hidden min-h-[232px]">
      {/* Top Title Bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-semibold text-[var(--text-primary)]">额度使用情况</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-medium">
            {isUsedMode ? '已用口径' : '剩余口径'}
          </span>
        </div>
        <div className="flex items-center gap-1 text-[11px] text-[var(--text-muted)]">
          <span className={`w-1.5 h-1.5 rounded-full ${healthDotClass}`} />
          <span className="truncate max-w-[100px]">{quota.source}</span>
        </div>
      </div>

      {/* Center Compass Circle Area */}
      <div className="flex items-center justify-center relative my-0.5">
        {isUnavailable ? (
          <div className="flex flex-col items-center justify-center py-4 text-center text-[var(--text-muted)]">
            <AlertCircle aria-hidden="true" className="w-7 h-7 text-[var(--text-muted)] mb-1 opacity-60" />
            <span className="text-xs">无官方额度限制</span>
            <span className="text-[10px] text-[var(--text-secondary)] mt-0.5">{quota.source}</span>
          </div>
        ) : (
          <button
            type="button"
            aria-label={`切换额度口径，当前为${isUsedMode ? '已用' : '剩余'}`}
            aria-pressed={!isUsedMode}
            className="relative cursor-pointer group flex items-center justify-center p-0 border-0 bg-transparent"
            onClick={onToggleQuotaMode}
            title="点击切换 已用 / 剩余 额度口径"
          >
            <svg aria-hidden="true" width={size} height={size} data-quota-direction={isUsedMode ? 'used-left' : 'remaining-right'} className={`origin-center ${ringDirectionClass}`}>
              {/* Outer track background (7D) */}
              <circle
                cx={center}
                cy={center}
                r={rOuter}
                fill="transparent"
                stroke="var(--border-default)"
                strokeWidth={strokeWidth}
                className="opacity-40"
              />
              {/* Outer progress ring (7D - Purple) */}
              <circle
                cx={center}
                cy={center}
                r={rOuter}
                fill="transparent"
                stroke="var(--quota-7d)"
                strokeWidth={strokeWidth}
                strokeDasharray={cOuter}
                strokeDashoffset={offsetOuter}
                strokeLinecap="round"
                className="transition-all duration-700 ease-out"
              />

              {/* Inner track background (5H) */}
              {quota.has_five_hour && (
                <>
                  <circle
                    cx={center}
                    cy={center}
                    r={rInner}
                    fill="transparent"
                    stroke="var(--border-default)"
                    strokeWidth={strokeWidth}
                    className="opacity-40"
                  />
                  {/* Inner progress ring (5H - Blue) */}
                  <circle
                    cx={center}
                    cy={center}
                    r={rInner}
                    fill="transparent"
                    stroke="var(--quota-5h)"
                    strokeWidth={strokeWidth}
                    strokeDasharray={cInner}
                    strokeDashoffset={offsetInner}
                    strokeLinecap="round"
                    className="transition-all duration-700 ease-out"
                  />
                </>
              )}
            </svg>

            {/* Compass Center Labels */}
            <div className="absolute inset-0 flex flex-col items-center justify-center text-center select-none pointer-events-none group-hover:scale-105 transition-transform">
              {quota.has_five_hour ? (
                <div className="flex flex-col items-center">
                  <div className="flex items-baseline gap-0.5">
                    <span className="text-[9px] text-blue-400 font-medium">5H:</span>
                    <span className="text-xs font-bold text-blue-400">{pct5h == null ? '--' : `${pct5h}%`}</span>
                  </div>
                  <div className="w-6 h-px bg-[var(--border-default)] my-0.5" />
                  <div className="flex items-baseline gap-0.5">
                    <span className="text-[9px] text-purple-400 font-medium">7D:</span>
                    <span className="text-sm font-bold text-purple-400">{pct7d == null ? '--' : `${pct7d}%`}</span>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center">
                  <span className="text-[10px] text-purple-300 font-medium">{isUsedMode ? '7D 已用' : '7D 剩余'}</span>
                  <span className="text-xl font-black text-purple-400 tracking-tight">{pct7d == null ? '--' : `${pct7d}%`}</span>
                </div>
              )}
            </div>
          </button>
        )}
      </div>

      {/* Bottom Reset Time Info Bar */}
      {!isUnavailable && (
        <div className="grid grid-cols-2 gap-1.5 pt-2 border-t border-[var(--border-default)] text-[10px]">
          {quota.has_five_hour && (
            <div className="flex items-center gap-1 text-[var(--text-secondary)]">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0" />
              <span>5H:</span>
              <span className="font-mono text-[var(--text-primary)] font-medium truncate">
                {quota.five_hour_reset_at ?? '未知'}
              </span>
            </div>
          )}
          <div className={`flex items-center gap-1 text-[var(--text-secondary)] ${!quota.has_five_hour ? 'col-span-2 justify-center' : ''}`}>
            <span className="w-1.5 h-1.5 rounded-full bg-purple-400 shrink-0" />
            <span>7D 重置:</span>
            <span className="font-mono text-[var(--text-primary)] font-medium truncate">
              {quota.seven_day_reset_at ?? '未知'}
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

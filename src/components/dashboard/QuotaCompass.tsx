import React, { useEffect, useMemo, useState } from 'react';
import { QuotaFamily, QuotaSnapshot } from '../../types';
import { nextTabId, prevTabId, isTabListNavKey } from '../../lib/rovingTabs';

interface QuotaCompassProps {
  quota: QuotaSnapshot;
  quotaMode: 'used' | 'remaining';
  onToggleQuotaMode: () => void;
}

function pickRatio(used: number | null, remaining: number | null, isUsedMode: boolean): number | null {
  return isUsedMode ? used : remaining;
}

function familyButtonLabel(family: QuotaFamily): string {
  if (family.id === 'gemini') return 'Gemini';
  if (family.id === 'claude') return 'Claude';
  return family.label;
}

function DualRing({
  hasFiveHour,
  hasSevenDay,
  ratio5h,
  ratio7d,
  reset5h,
  reset7d,
  isUsedMode,
  onToggleQuotaMode,
}: {
  hasFiveHour: boolean;
  hasSevenDay: boolean;
  ratio5h: number | null;
  ratio7d: number | null;
  reset5h: string | null;
  reset7d: string | null;
  isUsedMode: boolean;
  onToggleQuotaMode: () => void;
}) {
  const pct5h = ratio5h == null ? null : Math.round(ratio5h * 100);
  const pct7d = ratio7d == null ? null : Math.round(ratio7d * 100);
  const size = 156;
  const center = size / 2;
  const strokeWidth = 10;
  const rOuter = 64;
  const cOuter = 2 * Math.PI * rOuter;
  const offsetOuter = ratio7d == null ? cOuter : cOuter * (1 - ratio7d);
  const rInner = 48;
  const cInner = 2 * Math.PI * rInner;
  const offsetInner = ratio5h == null ? cInner : cInner * (1 - ratio5h);
  const ringDirectionClass = isUsedMode ? 'rotate-90' : 'rotate-90 -scale-x-100';

  return (
    <>
      <div className="flex items-center justify-center relative">
        <button
          type="button"
          aria-label={`切换额度口径，当前为${isUsedMode ? '已用' : '剩余'}`}
          aria-pressed={!isUsedMode}
          className="relative cursor-pointer group flex items-center justify-center min-w-[156px] min-h-[156px] p-0 border-0 bg-transparent"
          onClick={onToggleQuotaMode}
          title="切换已用 / 剩余"
        >
          <svg aria-hidden="true" width={size} height={size} className={`origin-center ${ringDirectionClass}`}>
            {hasSevenDay && (
              <>
                <circle cx={center} cy={center} r={rOuter} fill="transparent" stroke="var(--border-default)" strokeWidth={strokeWidth} className="opacity-40" />
                <circle cx={center} cy={center} r={rOuter} fill="transparent" stroke="var(--quota-7d)" strokeWidth={strokeWidth} strokeDasharray={cOuter} strokeDashoffset={offsetOuter} strokeLinecap="round" className="transition-all duration-700 ease-out" />
              </>
            )}
            {hasFiveHour && (
              <>
                <circle cx={center} cy={center} r={rInner} fill="transparent" stroke="var(--border-default)" strokeWidth={strokeWidth} className="opacity-40" />
                <circle cx={center} cy={center} r={rInner} fill="transparent" stroke="var(--quota-5h)" strokeWidth={strokeWidth} strokeDasharray={cInner} strokeDashoffset={offsetInner} strokeLinecap="round" className="transition-all duration-700 ease-out" />
              </>
            )}
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center select-none pointer-events-none">
            {hasFiveHour ? (
              <div className="flex flex-col items-center">
                <span className="text-sm font-bold text-[var(--quota-5h)]">{pct5h == null ? '--' : `${pct5h}%`}</span>
                <div className="w-7 h-px bg-[var(--border-default)] my-0.5" />
                <span className="text-xl font-bold text-[var(--quota-7d)]">{pct7d == null ? '--' : `${pct7d}%`}</span>
              </div>
            ) : (
              <span className="text-3xl font-black text-[var(--quota-7d)] tracking-tight">{pct7d == null ? '--' : `${pct7d}%`}</span>
            )}
          </div>
        </button>
      </div>
      <div className="flex items-center justify-center gap-3 pt-1 text-[11px] text-[var(--text-secondary)]">
        {hasFiveHour && (
          <div className="flex items-center gap-1 min-w-0">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--quota-5h)] shrink-0" />
            <span>5H</span>
            {reset5h && <span className="font-medium text-[var(--text-primary)] truncate">{reset5h}</span>}
          </div>
        )}
        {hasSevenDay && (
          <div className="flex items-center gap-1 min-w-0">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--quota-7d)] shrink-0" />
            <span>7D</span>
            {reset7d && <span className="font-medium text-[var(--text-primary)] truncate">{reset7d}</span>}
          </div>
        )}
      </div>
    </>
  );
}

export const QuotaCompass: React.FC<QuotaCompassProps> = ({
  quota,
  quotaMode,
  onToggleQuotaMode,
}) => {
  const isUsedMode = quotaMode === 'used';
  const families = useMemo(
    () => (quota.families ?? []).filter((family) => family.has_five_hour || family.has_seven_day),
    [quota.families],
  );
  const hasFamilies = families.length > 0;
  const [familyId, setFamilyId] = useState(families[0]?.id ?? 'gemini');

  useEffect(() => {
    if (!families.some((family) => family.id === familyId)) {
      setFamilyId(families[0]?.id ?? 'gemini');
    }
  }, [families, familyId]);

  const activeFamily = families.find((family) => family.id === familyId) ?? families[0];
  const isUnavailable = !hasFamilies
    && (quota.status === 'unavailable'
      || quota.status === 'refreshing'
      || (!quota.has_seven_day && !quota.has_five_hour));
  const healthDotClass = isUnavailable
    ? 'bg-[var(--danger)]'
    : quota.status === 'degraded' || quota.status === 'stale' || quota.status === 'refreshing'
      ? 'bg-[var(--warning)]'
      : 'bg-[var(--success)] animate-pulse';

  return (
    <div className="bg-[var(--bg-card)] border border-[var(--border-default)] rounded-lg px-3 py-2 flex flex-col gap-1 min-h-0">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="text-xs font-semibold text-[var(--text-primary)]">额度</span>
          {/* Non-interactive label: the single quota-mode toggle entry is the
              center ring click (below), which keeps one focus target. */}
          <span
            className="text-[11px] px-1.5 py-0.5 rounded-full ui-selected font-medium"
            aria-label={`当前额度口径为${isUsedMode ? '已用' : '剩余'}，点击圆心切换`}
          >
            {isUsedMode ? '已用' : '剩余'}
          </span>
        </div>
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${healthDotClass}`} title={quota.source} />
      </div>

      {hasFamilies && families.length > 1 && (
        <div
          role="tablist"
          aria-label="额度模型家族"
          className="flex items-center gap-1 p-0.5 rounded-md bg-[var(--bg-subtle)] border border-[var(--border-default)]"
          onKeyDown={(event: React.KeyboardEvent<HTMLElement>) => {
            if (!isTabListNavKey(event.key)) return;
            event.preventDefault();
            const familyIds = families.map((f) => f.id);
            const next = event.key === 'ArrowRight'
              ? nextTabId(familyIds, familyId)
              : event.key === 'ArrowLeft'
                ? prevTabId(familyIds, familyId)
                : event.key === 'Home'
                  ? familyIds[0]
                  : familyIds[familyIds.length - 1];
            setFamilyId(next);
            document.getElementById(`quota-family-tab-${next}`)?.focus();
          }}
        >
          {families.map((family) => {
            const selected = family.id === activeFamily?.id;
            return (
              <button
                key={family.id}
                type="button"
                role="tab"
                id={`quota-family-tab-${family.id}`}
                tabIndex={selected ? 0 : -1}
                aria-selected={selected}
                // Only the selected family's panel is rendered.
                {...(selected ? { 'aria-controls': 'quota-family-panel' } : {})}
                onClick={() => setFamilyId(family.id)}
                className={`flex-1 px-2 py-1 rounded-md text-xs font-semibold transition ${
                  selected
                    ? 'bg-[var(--bg-card)] text-[var(--text-primary)] shadow-sm border border-[var(--border-default)]'
                    : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                }`}
              >
                {familyButtonLabel(family)}
              </button>
            );
          })}
        </div>
      )}

      <div className="flex-1 flex flex-col justify-center min-h-0">
      {isUnavailable ? (
        <DualRing
          hasFiveHour={false}
          hasSevenDay
          ratio5h={null}
          ratio7d={null}
          reset5h={null}
          reset7d={quota.status === 'refreshing' ? '查询中' : null}
          isUsedMode={isUsedMode}
          onToggleQuotaMode={onToggleQuotaMode}
        />
      ) : activeFamily ? (
        <DualRing
          hasFiveHour={activeFamily.has_five_hour}
          hasSevenDay={activeFamily.has_seven_day}
          ratio5h={pickRatio(activeFamily.five_hour_used_ratio, activeFamily.five_hour_remaining_ratio, isUsedMode)}
          ratio7d={pickRatio(activeFamily.seven_day_used_ratio, activeFamily.seven_day_remaining_ratio, isUsedMode)}
          reset5h={activeFamily.five_hour_reset_at}
          reset7d={activeFamily.seven_day_reset_at}
          isUsedMode={isUsedMode}
          onToggleQuotaMode={onToggleQuotaMode}
        />
      ) : (
        <DualRing
          hasFiveHour={quota.has_five_hour}
          hasSevenDay={quota.has_seven_day}
          ratio5h={pickRatio(quota.five_hour_used_ratio, quota.five_hour_remaining_ratio, isUsedMode)}
          ratio7d={pickRatio(quota.seven_day_used_ratio, quota.seven_day_remaining_ratio, isUsedMode)}
          reset5h={quota.five_hour_reset_at}
          reset7d={quota.seven_day_reset_at}
          isUsedMode={isUsedMode}
          onToggleQuotaMode={onToggleQuotaMode}
        />
      )}
      </div>
    </div>
  );
};

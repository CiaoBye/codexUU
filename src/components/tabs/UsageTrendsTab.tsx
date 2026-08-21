import React, { useEffect, useMemo, useState } from 'react';
import { DailyActivity, ModelUsage } from '../../types';
import { formatTokens } from '../dashboard/TokenMetricCards';
import { fillDailyRange, TrendPeriod } from '../../lib/trendRange';
import { isTabListNavKey, nextTabId, prevTabId } from '../../lib/rovingTabs';
import { TrendingUp, DollarSign, Cpu } from 'lucide-react';

const HEATMAP_LEVELS = [0, 1, 2, 3, 4] as const;
const TREND_PERIODS: TrendPeriod[] = ['daily', 'weekly', 'monthly', 'all'];
const TREND_PERIOD_LABELS: Record<TrendPeriod, string> = {
  daily: '每日',
  weekly: '本周',
  monthly: '本月',
  all: '累计',
};

function heatmapColor(level: number): string {
  if (level === 0) return 'var(--bg-subtle)';
  return `color-mix(in srgb, var(--accent-brand) ${18 + level * 17}%, var(--bg-elevated))`;
}

interface UsageTrendsTabProps {
  dailyActivities: DailyActivity[];
  models: ModelUsage[];
  today: string;
}

export const UsageTrendsTab: React.FC<UsageTrendsTabProps> = ({
  dailyActivities,
  models,
  today,
}) => {
  const [period, setPeriod] = useState<TrendPeriod>('daily');
  const [metricMode, setMetricMode] = useState<'tokens' | 'cost'>('tokens');
  const [focusedHeatmapLabel, setFocusedHeatmapLabel] = useState<string | null>(null);

  const safeToday = today && !Number.isNaN(new Date(today + 'T00:00:00Z').getTime())
    ? today
    : new Date().toISOString().slice(0, 10);

  const activities = useMemo(
    () => fillDailyRange(dailyActivities, period, safeToday),
    [dailyActivities, period, safeToday],
  );

  // Keep the displayed peak truthful while retaining a non-zero scale for an all-zero chart.
  const metricValues = activities
    .map((a) => (metricMode === 'tokens' ? a.tokens.total : a.cost_usd))
    .filter((value) => Number.isFinite(value));
  const dataMaxVal = Math.max(...metricValues, 0);
  const chartMaxVal = dataMaxVal || 1;
  const peakLabel = activities.length === 0
    ? '暂无'
    : metricMode === 'tokens'
    ? formatTokens(dataMaxVal)
    : `$${dataMaxVal.toFixed(2)}`;
  const topScaleLabel = dataMaxVal === 0
    ? '0'
    : metricMode === 'tokens'
    ? formatTokens(dataMaxVal)
    : `$${Math.round(dataMaxVal)}`;

  // Scheme B date range calculation
  const firstDate = activities[0]?.date.slice(5) || safeToday.slice(5);
  const lastDate = activities[activities.length - 1]?.date.slice(5) || safeToday.slice(5);
  const rangeLabel = period === 'all'
    ? '全部记录'
    : firstDate === lastDate
    ? lastDate
    : `${firstDate} - ${lastDate}`;

  // SVG dimensions for trend chart
  const svgWidth = 540;
  const svgHeight = 160;
  const paddingX = 40;
  const paddingY = 24;

  const modelTokens = models.reduce((sum, model) => sum + model.tokens.total, 0);
  const pricedTokens = models
    .filter((model) => model.pricing_status === 'exact')
    .reduce((sum, model) => sum + model.tokens.total, 0);
  const pricingCoverage = modelTokens > 0 ? Math.round((pricedTokens / modelTokens) * 100) : 0;

  const points = activities.map((a, i) => {
    const x = paddingX + (i / Math.max(activities.length - 1, 1)) * (svgWidth - paddingX * 2);
    const rawVal = metricMode === 'tokens' ? a.tokens.total : a.cost_usd;
    const val = Number.isFinite(rawVal) ? Math.max(rawVal, 0) : 0;
    const y = svgHeight - paddingY - (val / chartMaxVal) * (svgHeight - paddingY * 2);
    return { x, y, a };
  });

  const pathD = points.length > 0
    ? `M ${points[0].x} ${points[0].y} ` + points.slice(1).map((p) => `L ${p.x} ${p.y}`).join(' ')
    : '';

  const areaD = points.length > 0
    ? `${pathD} L ${points[points.length - 1].x} ${svgHeight - paddingY} L ${points[0].x} ${svgHeight - paddingY} Z`
    : '';
  const chartDescriptionId = 'usage-trends-chart-description';
  const heatmapActivities = activities.slice(-365);
  const heatmapRangeLabel = heatmapActivities.length === 0
    ? '暂无日期'
    : `${heatmapActivities[0].date} 至 ${heatmapActivities[heatmapActivities.length - 1].date}`;
  useEffect(() => {
    setFocusedHeatmapLabel(null);
  }, [heatmapRangeLabel, metricMode]);
  const heatmapMaxValue = Math.max(
    ...heatmapActivities.map((activity) => (
      metricMode === 'tokens' ? activity.tokens.total : activity.cost_usd
    )),
    0,
  );
  const heatmapLeadingSlots = heatmapActivities.length > 0
    ? (new Date(`${heatmapActivities[0].date}T00:00:00Z`).getUTCDay() + 6) % 7
    : 0;
  const heatmapCells = heatmapActivities.map((activity) => {
    const rawValue = metricMode === 'tokens' ? activity.tokens.total : activity.cost_usd;
    const value = Number.isFinite(rawValue) ? Math.max(rawValue, 0) : 0;
    const intensity = value <= 0 || heatmapMaxValue <= 0
      ? 0
      : Math.max(1, Math.min(4, Math.ceil((value / heatmapMaxValue) * 4)));
    const valueLabel = metricMode === 'tokens'
      ? `Token ${formatTokens(value)}`
      : `API 等效价值 $${value.toFixed(2)}`;
    const label = `${activity.date}，${valueLabel}，强度 ${intensity}/4`;
    return { activity, intensity, label };
  });
  const heatmapWeekCount = Math.max(1, Math.ceil((heatmapLeadingSlots + heatmapCells.length) / 7));
  const heatmapMonthTicks = Array.from({ length: heatmapWeekCount }, (_, weekIndex) => {
    const firstDateIndex = Math.max(0, weekIndex * 7 - heatmapLeadingSlots);
    const weekActivities = heatmapActivities.slice(firstDateIndex, firstDateIndex + 7);
    const monthStarts = weekActivities.filter((activity, index) => (
      index === 0
        ? weekIndex === 0
        : activity.date.slice(0, 7) !== weekActivities[index - 1].date.slice(0, 7)
    ));
    const labelDate = monthStarts[monthStarts.length - 1]?.date;
    return labelDate
      ? { weekIndex, label: `${labelDate.slice(0, 4)}-${labelDate.slice(5, 7)}` }
      : null;
  }).filter((tick): tick is { weekIndex: number; label: string } => tick !== null);

  const handleHeatmapKeyDown = (
    event: React.KeyboardEvent<HTMLSpanElement>,
    index: number,
  ) => {
    let nextIndex = index;
    if (event.key === 'ArrowDown') nextIndex += 1;
    else if (event.key === 'ArrowUp') nextIndex -= 1;
    else if (event.key === 'ArrowRight') nextIndex += 7;
    else if (event.key === 'ArrowLeft') nextIndex -= 7;
    else if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = heatmapCells.length - 1;
    else return;

    event.preventDefault();
    nextIndex = Math.max(0, Math.min(heatmapCells.length - 1, nextIndex));
    const gridCells = event.currentTarget
      .closest('[role="grid"]')
      ?.querySelectorAll<HTMLElement>('[role="gridcell"]');
    const target = gridCells?.item(nextIndex);
    if (!target || target === event.currentTarget) return;
    event.currentTarget.tabIndex = -1;
    target.tabIndex = 0;
    target.focus();
  };

  const handlePeriodKeyDown = (
    event: React.KeyboardEvent<HTMLButtonElement>,
    currentPeriod: TrendPeriod,
  ) => {
    if (!isTabListNavKey(event.key)) return;
    event.preventDefault();
    const nextPeriod = event.key === 'ArrowRight'
      ? nextTabId(TREND_PERIODS, currentPeriod)
      : event.key === 'ArrowLeft'
        ? prevTabId(TREND_PERIODS, currentPeriod)
        : event.key === 'Home'
          ? TREND_PERIODS[0]
          : TREND_PERIODS[TREND_PERIODS.length - 1];
    setPeriod(nextPeriod as TrendPeriod);
    document.getElementById(`usage-trend-period-${nextPeriod}`)?.focus();
  };

  return (
    <div className="h-full min-h-0 overflow-y-auto space-y-3 pr-1 flex flex-col">
      {/* Scheme B Date Range Bar */}
      <div className="dashboard-panel-card p-2.5 flex items-center justify-between">
        {/* Left: Period buttons */}
        <div className="flex items-center gap-3">
          <div role="tablist" aria-orientation="horizontal" aria-label="趋势统计范围" className="flex items-center p-0.5 bg-[var(--bg-subtle)] border border-[var(--border-default)] rounded-lg text-xs">
            {TREND_PERIODS.map((p) => {
              return (
                <button
                  key={p}
                  type="button"
                  role="tab"
                  id={`usage-trend-period-${p}`}
                  tabIndex={period === p ? 0 : -1}
                  aria-selected={period === p}
                  onClick={() => setPeriod(p)}
                  onKeyDown={(event) => handlePeriodKeyDown(event, p)}
                  className={`px-3 py-1 rounded-md font-medium transition ${
                    period === p
                      ? 'ui-selected'
                      : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                  }`}
                >
                  {TREND_PERIOD_LABELS[p]}
                </button>
              );
            })}
          </div>

          <div className="text-xs font-mono text-[var(--text-primary)] font-bold">
            {rangeLabel}
          </div>
        </div>

        {/* Right: Metric switcher */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            aria-pressed={metricMode === 'cost'}
            aria-label={metricMode === 'tokens' ? '切换到 API 等效价值' : '切换到 Token 消耗'}
            onClick={() => setMetricMode(metricMode === 'tokens' ? 'cost' : 'tokens')}
            className="flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium bg-[var(--bg-subtle)] border border-[var(--border-default)] hover:border-[color-mix(in_srgb,var(--accent-brand)_40%,transparent)] text-[var(--text-primary)] transition"
          >
            {metricMode === 'tokens' ? <TrendingUp aria-hidden="true" className="w-3.5 h-3.5 text-[var(--accent-brand)]" /> : <DollarSign aria-hidden="true" className="w-3.5 h-3.5 text-[var(--warning)]" />}
            <span>{metricMode === 'tokens' ? 'Token' : '$'}</span>
          </button>
        </div>
      </div>

      <section
        aria-labelledby="usage-heatmap-title"
        aria-describedby="usage-heatmap-range usage-heatmap-focus"
        className="dashboard-panel-card order-2 p-3"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
          <div>
            <h3 id="usage-heatmap-title" className="text-sm font-bold text-[var(--text-primary)]">
              连续自然日热力图
            </h3>
            <p className="text-xs leading-relaxed text-[var(--text-muted)] mt-0.5">
              每格数字为 0–4 强度；0 表示无用量，4 表示热力图峰值。最多展示最近 365 天。
            </p>
            <p id="usage-heatmap-range" className="text-[11px] text-[var(--text-secondary)] mt-1 font-mono">
              日期范围：{heatmapRangeLabel}
            </p>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
            <span>低</span>
            <ul aria-label="热力图强度图例" className="flex items-center gap-1">
              {HEATMAP_LEVELS.map((level) => (
                <li
                  key={level}
                  className="w-6 h-6 rounded-md border border-[var(--border-default)] flex items-center justify-center font-mono font-bold"
                  style={{
                    backgroundColor: heatmapColor(level),
                    color: level >= 3 ? 'var(--on-accent)' : 'var(--text-primary)',
                  }}
                >
                  {level}
                </li>
              ))}
            </ul>
            <span>高</span>
          </div>
        </div>

        <div className="flex gap-2 overflow-x-auto pb-1">
          <div aria-hidden="true" className="grid grid-rows-7 gap-1 shrink-0 pt-5 text-[9px] text-[var(--text-muted)]">
            {['一', '二', '三', '四', '五', '六', '日'].map((weekday) => (
              <span key={weekday} className="h-7 flex items-center justify-center">{weekday}</span>
            ))}
          </div>
          <div className="min-w-max">
            <div
              aria-hidden="true"
              className="grid gap-1 h-4 mb-1 text-[9px] text-[var(--text-muted)] font-mono"
              style={{ gridTemplateColumns: `repeat(${heatmapWeekCount}, 1.75rem)` }}
            >
              {heatmapMonthTicks.map(({ weekIndex, label }) => (
                <span key={`${label}-${weekIndex}`} style={{ gridColumn: weekIndex + 1 }}>
                  {label}
                </span>
              ))}
            </div>
            <div
              role="grid"
              aria-label="连续自然日热力图"
              className="grid grid-flow-col grid-rows-7 gap-1"
              style={{ gridAutoColumns: '1.75rem' }}
            >
              {Array.from({ length: heatmapLeadingSlots }, (_, index) => (
                <span key={`heatmap-leading-${index}`} aria-hidden="true" className="h-7 w-7" />
              ))}
              {heatmapCells.map(({ activity, intensity, label }, index) => (
                <span
                  key={activity.date}
                  role="gridcell"
                  tabIndex={index === 0 ? 0 : -1}
                  aria-label={label}
                  title={label}
                  onFocus={(event) => {
                    setFocusedHeatmapLabel(label);
                    event.currentTarget
                      .closest('[role="grid"]')
                      ?.querySelectorAll<HTMLElement>('[role="gridcell"]')
                      .forEach((cell) => { cell.tabIndex = cell === event.currentTarget ? 0 : -1; });
                  }}
                  onKeyDown={(event) => handleHeatmapKeyDown(event, index)}
                  className="h-7 w-7 rounded-md border border-[var(--border-default)] flex items-center justify-center text-[10px] font-mono font-bold select-none"
                  style={{
                    backgroundColor: heatmapColor(intensity),
                    color: intensity >= 3 ? 'var(--on-accent)' : 'var(--text-primary)',
                  }}
                >
                  {intensity}
                </span>
              ))}
            </div>
          </div>
        </div>
        <p id="usage-heatmap-focus" aria-live="polite" className="mt-2 min-h-4 text-[11px] text-[var(--text-secondary)]">
          {focusedHeatmapLabel ? `当前日期：${focusedHeatmapLabel}` : '聚焦任意日期查看详细用量'}
        </p>
      </section>

      {/* Trend chart and model ranking */}
      <div className="order-1 grid grid-cols-1 lg:grid-cols-3 gap-3">
        {/* Left 2 Cols: 0-baseline trend chart */}
        <div className="dashboard-panel-card lg:col-span-2 p-4 flex flex-col justify-between min-h-[320px]">
          <div className="flex items-center justify-between">
            <h3
              aria-label={`趋势 · ${metricMode === 'tokens' ? 'Token' : 'API 等效价值'}`}
              className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5"
            >
              <TrendingUp aria-hidden="true" className="w-4 h-4 text-[var(--accent-brand)]" />
              <span>趋势</span>
              <span className="text-xs text-[var(--text-muted)]">
                · {metricMode === 'tokens' ? 'Token' : 'API 等效价值'}
              </span>
            </h3>
            <span className="text-xs text-[var(--text-muted)]">
              峰值: {peakLabel}
            </span>
          </div>

          {/* SVG Line Chart */}
          <div className="flex-1 flex items-center justify-center my-2 relative">
            <svg
              viewBox={`0 0 ${svgWidth} ${svgHeight}`}
              role="img"
              aria-label={`${rangeLabel} ${metricMode === 'tokens' ? 'Token' : 'API 等效价值'}趋势图`}
              aria-describedby={chartDescriptionId}
              className="w-full h-full"
            >
              <title>{`${rangeLabel} ${metricMode === 'tokens' ? 'Token' : 'API 等效价值'}趋势图`}</title>
              <defs>
                <linearGradient id="trendGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--accent-brand)" stopOpacity="0.35" />
                  <stop offset="100%" stopColor="var(--accent-brand)" stopOpacity="0.0" />
                </linearGradient>
              </defs>

              {/* Grid Lines */}
              <line x1={paddingX} y1={paddingY} x2={svgWidth - paddingX} y2={paddingY} stroke="var(--border-default)" strokeDasharray="3 3" opacity="0.4" />
              <line x1={paddingX} y1={(svgHeight - paddingY + paddingY) / 2} x2={svgWidth - paddingX} y2={(svgHeight - paddingY + paddingY) / 2} stroke="var(--border-default)" strokeDasharray="3 3" opacity="0.4" />
              <line x1={paddingX} y1={svgHeight - paddingY} x2={svgWidth - paddingX} y2={svgHeight - paddingY} stroke="var(--border-default)" opacity="0.8" />

              {/* Baseline 0 text */}
              <text x={paddingX - 6} y={svgHeight - paddingY + 3} textAnchor="end" fill="var(--text-muted)" fontSize="10">0</text>
              <text x={paddingX - 6} y={paddingY + 4} textAnchor="end" fill="var(--text-muted)" fontSize="10">
                {topScaleLabel}
              </text>

              {/* Area & Line */}
              {points.length > 0 && <path d={areaD} fill="url(#trendGradient)" />}
              {points.length > 0 && <path d={pathD} fill="none" stroke="var(--accent-brand)" strokeWidth="2.5" strokeLinecap="round" />}

              {/* Data points */}
              {points.map((p) => (
                <g key={p.a.date}>
                  <circle cx={p.x} cy={p.y} r="3.5" fill="var(--bg-canvas)" stroke="var(--accent-brand)" strokeWidth="2" />
                  <title>{`${p.a.date}：${metricMode === 'tokens' ? formatTokens(p.a.tokens.total) : `$${p.a.cost_usd.toFixed(2)}`}`}</title>
                  <text x={p.x} y={svgHeight - paddingY + 14} textAnchor="middle" fill="var(--text-muted)" fontSize="9">
                    {p.a.date.slice(5)}
                  </text>
                </g>
              ))}
            </svg>
            {activities.length === 0 && (
              <span className="absolute text-xs text-[var(--text-muted)]">暂无</span>
            )}
          </div>

          <p id={chartDescriptionId} className="sr-only">
            图表从零基线展示连续自然日数据；缺失日期已按零补全。当前峰值为 {peakLabel}。
          </p>

          <details className="mt-1 text-[11px] text-[var(--text-secondary)]">
            <summary className="cursor-pointer select-none hover:text-[var(--text-primary)]">查看趋势明细</summary>
            <div className="mt-2 overflow-x-auto rounded-lg border border-[var(--border-default)]">
              <table aria-label="用量趋势明细" className="w-full text-left">
                <thead className="sticky top-0 bg-[var(--bg-elevated)] text-[var(--text-muted)]">
                  <tr>
                    <th scope="col" className="px-2 py-1 font-medium">日期</th>
                    <th scope="col" className="px-2 py-1 font-medium">Token</th>
                    <th scope="col" className="px-2 py-1 font-medium">价值</th>
                  </tr>
                </thead>
                <tbody>
                  {activities.map((activity) => (
                    <tr key={activity.date} className="border-t border-[var(--border-default)]/60">
                      <th scope="row" className="px-2 py-1 font-medium">{activity.date}</th>
                      <td className="px-2 py-1 font-mono">{formatTokens(activity.tokens.total)}</td>
                      <td className="px-2 py-1 font-mono">${activity.cost_usd.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </div>

        {/* Right 1 Col: Model ranking & API equivalent cost */}
        <div className="dashboard-panel-card p-4 flex flex-col justify-between min-h-[320px]">
          <div className="flex items-center justify-between pb-2 border-b border-[var(--border-default)]">
            <h3 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-1.5">
              <Cpu aria-hidden="true" className="w-4 h-4 text-[var(--quota-7d)]" />
              <span>模型消耗排行</span>
          </h3>
            <span className="text-xs text-[var(--text-muted)]">{models.length}</span>
          </div>

          {/* Model items scroll list */}
          <div className="flex-1 space-y-2 py-2 pr-1">
            {models.map((m) => (
              <div
                key={m.model_id}
                className="p-2 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-default)] flex items-center justify-between text-xs"
              >
                <div>
                  <div className="font-semibold text-[var(--text-primary)] truncate max-w-[120px]">
                    {m.model_id}
                  </div>
                  <div className="text-[11px] text-[var(--text-muted)] mt-0.5">
                    {m.sessions} 会话 · {m.turns} 回合
                  </div>
                </div>

                <div className="text-right">
                  <div className="font-mono font-bold text-[var(--accent-brand)]">
                    {formatTokens(m.tokens.total)}
                  </div>
                  <div className="text-[11px] font-mono text-[var(--token-output)]">
                    {m.pricing_status === 'exact' ? `$${m.cost_usd.toFixed(2)}` : '未计价'}
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="pt-2 border-t border-[var(--border-default)] text-[11px] text-[var(--text-muted)] flex justify-between">
            <span>定价状态: {pricingCoverage === 100 ? '官方精确匹配' : '部分模型未计价'}</span>
            <span>覆盖率 {pricingCoverage}%</span>
          </div>
        </div>
      </div>
    </div>
  );
};

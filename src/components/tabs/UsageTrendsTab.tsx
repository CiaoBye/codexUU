import React, { useMemo, useState } from 'react';
import { DailyActivity, ModelUsage } from '../../types';
import { formatTokens } from '../dashboard/TokenMetricCards';
import { fillDailyRange, TrendPeriod } from '../../lib/trendRange';
import { TrendingUp, DollarSign, Cpu } from 'lucide-react';

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

  return (
    <div className="space-y-3">
      {/* Scheme B Date Range Bar */}
      <div className="bg-[var(--bg-card)] border border-[var(--border-default)] rounded-xl p-2.5 flex items-center justify-between shadow-sm">
        {/* Left: Period buttons */}
        <div className="flex items-center gap-3">
          <div role="tablist" aria-label="趋势统计范围" className="flex items-center p-0.5 bg-[var(--bg-subtle)] border border-[var(--border-default)] rounded-lg text-xs">
            {(['daily', 'weekly', 'monthly', 'all'] as const).map((p) => {
              const labels = { daily: '每日', weekly: '本周', monthly: '本月', all: '累计' };
              return (
                <button
                  key={p}
                  type="button"
                  role="tab"
                  aria-selected={period === p}
                  onClick={() => setPeriod(p)}
                  className={`px-3 py-1 rounded-md font-medium transition ${
                    period === p
                      ? 'ui-selected'
                      : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                  }`}
                >
                  {labels[p]}
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

      {/* Main Trends & Heatmap Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {/* Left 2 Cols: 0-baseline trend chart */}
        <div className="lg:col-span-2 bg-[var(--bg-card)] border border-[var(--border-default)] rounded-xl p-4 flex flex-col justify-between shadow-sm min-h-[320px]">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5">
              <TrendingUp aria-hidden="true" className="w-4 h-4 text-[var(--accent-brand)]" />
              <span>趋势</span>
            </h4>
            <span className="text-[11px] text-[var(--text-muted)]">
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
            <div className="mt-2 max-h-28 overflow-auto rounded-lg border border-[var(--border-default)]">
              <table className="w-full text-left">
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
        <div className="bg-[var(--bg-card)] border border-[var(--border-default)] rounded-xl p-4 flex flex-col justify-between shadow-sm min-h-[320px]">
          <div className="flex items-center justify-between pb-2 border-b border-[var(--border-default)]">
            <h4 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5">
              <Cpu aria-hidden="true" className="w-4 h-4 text-[var(--quota-7d)]" />
              <span>模型消耗排行</span>
            </h4>
            <span className="text-[10px] text-[var(--text-muted)]">{models.length}</span>
          </div>

          {/* Model items scroll list */}
          <div className="flex-1 overflow-y-auto space-y-2 py-2 pr-1">
            {models.map((m) => (
              <div
                key={m.model_id}
                className="p-2 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-default)] flex items-center justify-between text-xs"
              >
                <div>
                  <div className="font-semibold text-[var(--text-primary)] truncate max-w-[120px]">
                    {m.model_id}
                  </div>
                  <div className="text-[10px] text-[var(--text-muted)] mt-0.5">
                    {m.sessions} 会话 · {m.turns} 回合
                  </div>
                </div>

                <div className="text-right">
                  <div className="font-mono font-bold text-[var(--accent-brand)]">
                    {formatTokens(m.tokens.total)}
                  </div>
                  <div className="text-[10px] font-mono text-[var(--token-output)]">
                    {m.pricing_status === 'exact' ? `$${m.cost_usd.toFixed(2)}` : '未计价'}
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="pt-2 border-t border-[var(--border-default)] text-[10px] text-[var(--text-muted)] flex justify-between">
            <span>定价状态: {pricingCoverage === 100 ? '官方精确匹配' : '部分模型未计价'}</span>
            <span>覆盖率 {pricingCoverage}%</span>
          </div>
        </div>
      </div>
    </div>
  );
};

import React, { useState } from 'react';
import { DailyActivity, ModelUsage } from '../../types';
import { formatTokens } from '../dashboard/TokenMetricCards';
import { TrendingUp, DollarSign, Cpu } from 'lucide-react';

interface UsageTrendsTabProps {
  dailyActivities: DailyActivity[];
  models: ModelUsage[];
  today: string;
}

const DAY_MS = 24 * 60 * 60 * 1000;

function dateInRange(dateStr: string, period: 'daily' | 'weekly' | 'monthly' | 'all', todayStr: string): boolean {
  if (period === 'all') return true;

  const today = new Date(todayStr + 'T00:00:00Z');
  const d = new Date(dateStr + 'T00:00:00Z');
  if (d > today) return false;

  if (period === 'daily') {
    return today.getTime() - d.getTime() <= 6 * DAY_MS;
  }

  if (period === 'weekly') {
    const day = today.getUTCDay();
    const diffToMonday = day === 0 ? 6 : day - 1;
    const monday = new Date(today);
    monday.setUTCDate(today.getUTCDate() - diffToMonday);
    return d >= monday && d <= today;
  }

  // monthly
  const first = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), 1));
  return d >= first && d <= today;
}

export const UsageTrendsTab: React.FC<UsageTrendsTabProps> = ({
  dailyActivities,
  models,
  today,
}) => {
  const [period, setPeriod] = useState<'daily' | 'weekly' | 'monthly' | 'all'>('daily');
  const [metricMode, setMetricMode] = useState<'tokens' | 'cost'>('tokens');

  const safeToday = today && !Number.isNaN(new Date(today + 'T00:00:00Z').getTime())
    ? today
    : new Date().toISOString().slice(0, 10);

  const activities = dailyActivities.filter((a) => dateInRange(a.date, period, safeToday));

  // Calculate maximum for 0-baseline chart
  const maxVal = Math.max(
    ...activities.map((a) => (metricMode === 'tokens' ? a.tokens.total : a.cost_usd)),
    1
  );

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
    const val = metricMode === 'tokens' ? a.tokens.total : a.cost_usd;
    const y = svgHeight - paddingY - (val / maxVal) * (svgHeight - paddingY * 2);
    return { x, y, a };
  });

  const pathD = points.length > 0
    ? `M ${points[0].x} ${points[0].y} ` + points.slice(1).map((p) => `L ${p.x} ${p.y}`).join(' ')
    : '';

  const areaD = points.length > 0
    ? `${pathD} L ${points[points.length - 1].x} ${svgHeight - paddingY} L ${points[0].x} ${svgHeight - paddingY} Z`
    : '';

  return (
    <div className="space-y-3 select-none">
      {/* Scheme B Date Range Bar */}
      <div className="bg-[var(--bg-card)] border border-[var(--border-default)] rounded-xl p-2.5 flex items-center justify-between shadow-sm">
        {/* Left: Period buttons */}
        <div className="flex items-center gap-3">
          <div className="flex items-center p-0.5 bg-[var(--bg-subtle)] border border-[var(--border-default)] rounded-lg text-xs">
            {(['daily', 'weekly', 'monthly', 'all'] as const).map((p) => {
              const labels = { daily: '每日', weekly: '本周', monthly: '本月', all: '累计' };
              return (
                <button
                  key={p}
                  onClick={() => setPeriod(p)}
                  className={`px-3 py-1 rounded-md font-medium transition ${
                    period === p
                      ? 'bg-teal-500/20 text-teal-300 border border-teal-500/30'
                      : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                  }`}
                >
                  {labels[p]}
                </button>
              );
            })}
          </div>

          <div className="text-xs text-[var(--text-secondary)] font-medium">
            <span>统计范围: </span>
            <span className="font-mono text-[var(--text-primary)] font-bold">{rangeLabel}</span>
          </div>
        </div>

        {/* Right: Metric switcher */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setMetricMode(metricMode === 'tokens' ? 'cost' : 'tokens')}
            className="flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium bg-[var(--bg-subtle)] border border-[var(--border-default)] hover:border-teal-500/40 text-[var(--text-primary)] transition"
          >
            {metricMode === 'tokens' ? <TrendingUp className="w-3.5 h-3.5 text-teal-400" /> : <DollarSign className="w-3.5 h-3.5 text-amber-400" />}
            <span>{metricMode === 'tokens' ? '指标: Token 消耗' : '指标: API 等效价值 ($)'}</span>
          </button>
        </div>
      </div>

      {/* Main Trends & Heatmap Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {/* Left 2 Cols: 0-baseline trend chart */}
        <div className="lg:col-span-2 bg-[var(--bg-card)] border border-[var(--border-default)] rounded-2xl p-4 flex flex-col justify-between shadow-sm h-[320px]">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5">
              <TrendingUp className="w-4 h-4 text-teal-400" />
              <span>趋势折线图 (0 基线)</span>
            </h4>
            <span className="text-[11px] text-[var(--text-muted)]">
              峰值: {metricMode === 'tokens' ? formatTokens(maxVal) : `$${maxVal.toFixed(2)}`}
            </span>
          </div>

          {/* SVG Line Chart */}
          <div className="flex-1 flex items-center justify-center my-2 relative">
            <svg viewBox={`0 0 ${svgWidth} ${svgHeight}`} className="w-full h-full">
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
                {metricMode === 'tokens' ? formatTokens(maxVal) : `$${Math.round(maxVal)}`}
              </text>

              {/* Area & Line */}
              {points.length > 0 && <path d={areaD} fill="url(#trendGradient)" />}
              {points.length > 0 && <path d={pathD} fill="none" stroke="var(--accent-brand)" strokeWidth="2.5" strokeLinecap="round" />}

              {/* Data points */}
              {points.map((p, i) => (
                <g key={i}>
                  <circle cx={p.x} cy={p.y} r="3.5" fill="var(--bg-canvas)" stroke="var(--accent-brand)" strokeWidth="2" />
                  <text x={p.x} y={svgHeight - paddingY + 14} textAnchor="middle" fill="var(--text-muted)" fontSize="9">
                    {p.a.date.slice(5)}
                  </text>
                </g>
              ))}
            </svg>
            {activities.length === 0 && (
              <span className="absolute text-xs text-[var(--text-muted)]">暂无可用活动数据</span>
            )}
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-[var(--border-default)] text-[11px] text-[var(--text-secondary)]">
            <span>连续自然日统计</span>
            <span>缺失日期按 0 补全</span>
          </div>
        </div>

        {/* Right 1 Col: Model ranking & API equivalent cost */}
        <div className="bg-[var(--bg-card)] border border-[var(--border-default)] rounded-2xl p-4 flex flex-col justify-between shadow-sm h-[320px]">
          <div className="flex items-center justify-between pb-2 border-b border-[var(--border-default)]">
            <h4 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5">
              <Cpu className="w-4 h-4 text-purple-400" />
              <span>模型消耗排行</span>
            </h4>
            <span className="text-[10px] text-[var(--text-muted)]">官方单价估算</span>
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
                  <div className="font-mono font-bold text-teal-400">
                    {formatTokens(m.tokens.total)}
                  </div>
                  <div className="text-[10px] font-mono text-amber-400">
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

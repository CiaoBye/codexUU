import React from 'react';
import { TokenPeriods, TokenBreakdown } from '../../types';
import { Zap, Calendar, TrendingUp, Archive } from 'lucide-react';

interface TokenMetricCardsProps {
  tokens: TokenPeriods;
  unavailable?: boolean;
}

export function formatTokens(num: number): string {
  if (num >= 1_000_000_000) {
    return (num / 1_000_000_000).toFixed(2) + 'B';
  }
  if (num >= 1_000_000) {
    return (num / 1_000_000).toFixed(2) + 'M';
  }
  if (num >= 1_000) {
    return (num / 1_000).toFixed(1) + 'k';
  }
  return num.toString();
}

interface SingleCardProps {
  title: string;
  subtitle: string;
  icon: React.ElementType;
  breakdown: TokenBreakdown;
  colorClass: string;
  unavailable?: boolean;
}

const SingleCard: React.FC<SingleCardProps> = ({
  title,
  subtitle,
  icon: Icon,
  breakdown,
  colorClass,
  unavailable = false,
}) => {
  const total = breakdown.total || 1;
  const pctUncached = (breakdown.uncached_input / total) * 100;
  const pctCached = (breakdown.cached_input / total) * 100;
  const pctOutput = (breakdown.output / total) * 100;
  const displayTotal = unavailable ? '--' : formatTokens(breakdown.total);

  return (
    <div className="bg-[var(--bg-card)] border border-[var(--border-default)] rounded-xl p-4 flex flex-col justify-between shadow-sm relative overflow-hidden min-h-[232px]">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={`p-1.5 rounded-lg ${colorClass} bg-opacity-15 border border-opacity-30`}>
            <Icon aria-hidden="true" className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-semibold text-[var(--text-primary)]">{title}</h3>
            <span className="text-[10px] text-[var(--text-muted)]">{subtitle}</span>
          </div>
        </div>
      </div>

      {/* Main Big Number */}
      <div className="my-2">
        <div className="text-2xl font-extrabold font-mono tracking-tight text-[var(--text-primary)]">
          {displayTotal}
        </div>
        <div className="text-[11px] text-[var(--text-muted)] mt-0.5">
          {unavailable ? '等待真实快照' : `${breakdown.total.toLocaleString()} tokens`}
        </div>
      </div>

      {/* Tri-color Segmented Breakdown Bar */}
      <div className="space-y-1.5">
        <div className="h-2 w-full bg-[var(--bg-subtle)] rounded-full overflow-hidden flex gap-0.5 p-0.5">
          <div
            style={{ width: `${pctUncached}%` }}
            className="h-full bg-[var(--token-uncached)] rounded-l-full transition-all duration-500"
            title={`未缓存输入: ${formatTokens(breakdown.uncached_input)} (${Math.round(pctUncached)}%)`}
          />
          <div
            style={{ width: `${pctCached}%` }}
            className="h-full bg-[var(--token-cached)] transition-all duration-500"
            title={`缓存输入: ${formatTokens(breakdown.cached_input)} (${Math.round(pctCached)}%)`}
          />
          <div
            style={{ width: `${pctOutput}%` }}
            className="h-full bg-[var(--token-output)] rounded-r-full transition-all duration-500"
            title={`输出: ${formatTokens(breakdown.output)} (${Math.round(pctOutput)}%)`}
          />
        </div>

        {/* Legend */}
        <div className="grid grid-cols-3 gap-1 text-[10px] text-[var(--text-secondary)]">
          <div className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--token-uncached)] shrink-0" />
            <span className="truncate">未缓存: {formatTokens(breakdown.uncached_input)}</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--token-cached)] shrink-0" />
            <span className="truncate">缓存: {formatTokens(breakdown.cached_input)}</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--token-output)] shrink-0" />
            <span className="truncate">输出: {formatTokens(breakdown.output)}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export const TokenMetricCards: React.FC<TokenMetricCardsProps> = ({ tokens, unavailable = false }) => {
  return (
    <div className="dashboard-token-grid">
      <SingleCard
        title="今日用量"
        subtitle="当日自然日统计"
        icon={Zap}
        breakdown={tokens.today}
        colorClass="text-[var(--token-output)] bg-amber-500/10 border-amber-500/30"
        unavailable={unavailable}
      />
      <SingleCard
        title="本周用量"
        subtitle="周一至周日"
        icon={Calendar}
        breakdown={tokens.week}
        colorClass="text-blue-400 bg-blue-500/10 border-blue-500/30"
        unavailable={unavailable}
      />
      <SingleCard
        title="本月用量"
        subtitle="当月自然月"
        icon={TrendingUp}
        breakdown={tokens.month}
        colorClass="text-purple-400 bg-purple-500/10 border-purple-500/30"
        unavailable={unavailable}
      />
      <SingleCard
        title="累计记录"
        subtitle="本机全部历史"
        icon={Archive}
        breakdown={tokens.all_time}
        colorClass="text-teal-400 bg-teal-500/10 border-teal-500/30"
        unavailable={unavailable}
      />
    </div>
  );
};

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
  icon: React.ElementType;
  breakdown: TokenBreakdown;
  colorClass: string;
  unavailable?: boolean;
}

const SingleCard: React.FC<SingleCardProps> = ({
  title,
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
    <div className="bg-[var(--bg-card)] border border-[var(--border-default)] rounded-lg px-3 py-2.5 flex flex-col gap-2 min-h-0">
      <div className="flex items-center gap-1.5">
        <Icon aria-hidden="true" className={`w-3.5 h-3.5 ${colorClass}`} />
        <h3 className="text-xs font-semibold text-[var(--text-secondary)]">{title}</h3>
      </div>

      <div className="text-2xl font-extrabold font-mono tracking-tight text-[var(--text-primary)] leading-none">
        {displayTotal}
      </div>

      <div
        className="h-1.5 w-full bg-[var(--bg-subtle)] rounded-full overflow-hidden flex"
        title={`未缓存 ${formatTokens(breakdown.uncached_input)} · 缓存 ${formatTokens(breakdown.cached_input)} · 输出 ${formatTokens(breakdown.output)}`}
      >
        <div
          style={{ width: `${pctUncached}%` }}
          className="h-full bg-[var(--token-uncached)]"
        />
        <div
          style={{ width: `${pctCached}%` }}
          className="h-full bg-[var(--token-cached)]"
        />
        <div
          style={{ width: `${pctOutput}%` }}
          className="h-full bg-[var(--token-output)]"
        />
      </div>
    </div>
  );
};

export const TokenMetricCards: React.FC<TokenMetricCardsProps> = ({ tokens, unavailable = false }) => {
  return (
    <div className="dashboard-token-grid">
      <SingleCard
        title="今日用量"
        icon={Zap}
        breakdown={tokens.today}
        colorClass="text-[var(--token-output)]"
        unavailable={unavailable}
      />
      <SingleCard
        title="本周用量"
        icon={Calendar}
        breakdown={tokens.week}
        colorClass="text-[var(--quota-5h)]"
        unavailable={unavailable}
      />
      <SingleCard
        title="本月用量"
        icon={TrendingUp}
        breakdown={tokens.month}
        colorClass="text-[var(--quota-7d)]"
        unavailable={unavailable}
      />
      <SingleCard
        title="累计记录"
        icon={Archive}
        breakdown={tokens.all_time}
        colorClass="text-[var(--accent-brand)]"
        unavailable={unavailable}
      />
    </div>
  );
};

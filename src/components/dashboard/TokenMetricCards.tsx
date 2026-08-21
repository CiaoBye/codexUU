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
    <div className="dashboard-metric-card px-3 py-2.5 flex flex-col justify-between gap-2 min-h-0">
      <div className="flex items-center gap-1.5">
        <Icon aria-hidden="true" className={`w-3.5 h-3.5 ${colorClass}`} />
        <h3 className="text-xs font-semibold text-[var(--text-secondary)]">{title}</h3>
      </div>

      <div className="text-2xl font-extrabold font-mono tracking-tight text-[var(--text-primary)] leading-none">
        {displayTotal}
      </div>

      <div
        role="img"
        className="h-1.5 w-full bg-[var(--bg-subtle)] rounded-full overflow-hidden flex"
        aria-label={`Token 构成：未缓存 ${formatTokens(breakdown.uncached_input)}，缓存 ${formatTokens(breakdown.cached_input)}，输出 ${formatTokens(breakdown.output)}`}
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
      <div className="grid grid-cols-3 gap-1 text-[10px] leading-none text-[var(--text-muted)]" aria-label="Token 构成图例">
        <span className="flex items-center gap-1 min-w-0" title={`未缓存 ${formatTokens(breakdown.uncached_input)}`}>
          <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full bg-[var(--token-uncached)] shrink-0" />
          <span className="truncate">未缓存</span>
          <span className="font-mono text-[9px] text-[var(--text-secondary)] shrink-0">{formatTokens(breakdown.uncached_input)}</span>
        </span>
        <span className="flex items-center gap-1 min-w-0" title={`缓存 ${formatTokens(breakdown.cached_input)}`}>
          <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full bg-[var(--token-cached)] shrink-0" />
          <span className="truncate">缓存</span>
          <span className="font-mono text-[9px] text-[var(--text-secondary)] shrink-0">{formatTokens(breakdown.cached_input)}</span>
        </span>
        <span className="flex items-center gap-1 min-w-0" title={`输出 ${formatTokens(breakdown.output)}`}>
          <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full bg-[var(--token-output)] shrink-0" />
          <span className="truncate">输出</span>
          <span className="font-mono text-[9px] text-[var(--text-secondary)] shrink-0">{formatTokens(breakdown.output)}</span>
        </span>
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

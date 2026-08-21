import React from 'react';
import { ModelUsage, TokenPeriods, TokenBreakdown } from '../../types';
import { Zap, Calendar, TrendingUp, Archive } from 'lucide-react';
import { useAnimatedNumber } from '../../lib/motion';

interface TokenMetricCardsProps {
  tokens: TokenPeriods;
  models?: ModelUsage[];
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
  const animatedTotal = useAnimatedNumber(unavailable ? 0 : breakdown.total);

  return (
    <div className="dashboard-metric-card px-3 py-2.5 flex flex-col justify-between gap-2 min-h-0">
      <div className="flex items-center gap-1.5">
        <Icon aria-hidden="true" className={`w-3.5 h-3.5 ${colorClass}`} />
        <h3 className="text-xs font-semibold text-[var(--text-secondary)]">{title}</h3>
      </div>

      <div className="text-2xl font-extrabold font-mono tracking-tight text-[var(--text-primary)] leading-none">
        {unavailable ? '--' : formatTokens(Math.round(animatedTotal))}
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

function ApiValueCard({ models = [], unavailable = false }: { models?: ModelUsage[]; unavailable?: boolean }) {
  const estimatedValue = models.reduce((sum, model) => sum + (Number.isFinite(model.cost_usd) ? model.cost_usd : 0), 0);
  const pricedTokens = models
    .filter((model) => model.pricing_status === 'exact')
    .reduce((sum, model) => sum + model.tokens.total, 0);
  const totalTokens = models.reduce((sum, model) => sum + model.tokens.total, 0);
  const coverage = totalTokens > 0 ? Math.round((pricedTokens / totalTokens) * 100) : 0;
  const animatedValue = useAnimatedNumber(unavailable ? 0 : estimatedValue, 520);

  return (
    <div className="dashboard-value-strip" aria-label="API 等效价值">
      <div>
        <div className="dashboard-value-label">API 等效价值</div>
        <div className="dashboard-value-caption">按已识别模型公开价格估算</div>
      </div>
      <div className="dashboard-value-number">
        {unavailable ? '--' : `$${animatedValue.toFixed(2)}`}
      </div>
      <div className="dashboard-value-meta">
        <span>计价覆盖 {unavailable ? '--' : `${coverage}%`}</span>
        <span>{models.length} 个模型</span>
      </div>
    </div>
  );
}

export const TokenMetricCards: React.FC<TokenMetricCardsProps> = ({ tokens, models = [], unavailable = false }) => {
  return (
    <div className="dashboard-token-stack">
      <div className="dashboard-token-grid">
        <SingleCard title="今日用量" icon={Zap} breakdown={tokens.today} colorClass="text-[var(--token-output)]" unavailable={unavailable} />
        <SingleCard title="本周用量" icon={Calendar} breakdown={tokens.week} colorClass="text-[var(--quota-5h)]" unavailable={unavailable} />
        <SingleCard title="本月用量" icon={TrendingUp} breakdown={tokens.month} colorClass="text-[var(--quota-7d)]" unavailable={unavailable} />
        <SingleCard title="累计记录" icon={Archive} breakdown={tokens.all_time} colorClass="text-[var(--accent-brand)]" unavailable={unavailable} />
      </div>
      <ApiValueCard models={models} unavailable={unavailable} />
    </div>
  );
};

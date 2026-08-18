import React, { useState } from 'react';
import { ProjectRankingItem } from '../../types';
import { formatTokens } from '../dashboard/TokenMetricCards';
import { Award, PieChart, Clock, Download } from 'lucide-react';
import { exportData } from '../../api';

interface ProjectRankingTabProps {
  projects: ProjectRankingItem[];
  channel: string;
}

export const ProjectRankingTab: React.FC<ProjectRankingTabProps> = ({
  projects,
  channel,
}) => {
  const [exportNotice, setExportNotice] = useState<string | null>(null);

  const totalTokens = projects.reduce((sum, p) => sum + p.tokens.total, 0) || 1;
  const maxProjectTokens = Math.max(...projects.map((p) => p.tokens.total), 1);

  // Concentrations
  const top1Tokens = projects[0]?.tokens.total || 0;
  const top3Tokens = projects.slice(0, 3).reduce((sum, p) => sum + p.tokens.total, 0);
  const top1Pct = Math.round((top1Tokens / totalTokens) * 100);
  const top3Pct = Math.round((top3Tokens / totalTokens) * 100);
  const recentProject = projects.reduce<ProjectRankingItem | undefined>(
    (latest, project) => !latest || project.last_active_at > latest.last_active_at ? project : latest,
    undefined,
  );

  const handleExport = async (format: 'json' | 'csv' | 'markdown') => {
    try {
      const res = await exportData(format, channel);
      const mime = format === 'json' ? 'application/json' : format === 'csv' ? 'text/csv' : 'text/markdown';
      const blob = new Blob([res], { type: `${mime};charset=utf-8` });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `codexuu-projects-${channel}.${format === 'markdown' ? 'md' : format}`;
      a.click();
      URL.revokeObjectURL(url);
      setExportNotice(`已导出 ${format.toUpperCase()} 文件！`);
    } catch (err) {
      setExportNotice(`导出失败：${err instanceof Error ? err.message : String(err)}`);
    }
    setTimeout(() => setExportNotice(null), 3000);
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 h-[420px] select-none">
      {/* Left 2 Cols: Project Ranking Table */}
      <div className="lg:col-span-2 bg-[var(--bg-card)] border border-[var(--border-default)] rounded-2xl p-4 flex flex-col justify-between shadow-sm overflow-hidden">
        {/* Header with export */}
        <div className="flex items-center justify-between pb-2 border-b border-[var(--border-default)]">
          <div className="flex items-center gap-2">
            <h4 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5">
              <Award className="w-4 h-4 text-amber-400" />
              <span>项目用量排行</span>
            </h4>
            <span className="text-[11px] text-[var(--text-muted)]">真实有效目录 · 累计</span>
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={() => handleExport('json')}
              className="flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-medium bg-[var(--bg-subtle)] border border-[var(--border-default)] hover:border-teal-500/40 text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition"
            >
              <Download className="w-3 h-3" />
              JSON
            </button>
            <button
              onClick={() => handleExport('csv')}
              className="flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-medium bg-[var(--bg-subtle)] border border-[var(--border-default)] hover:border-teal-500/40 text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition"
            >
              <Download className="w-3 h-3" />
              CSV
            </button>
            <button
              onClick={() => handleExport('markdown')}
              className="flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-medium bg-[var(--bg-subtle)] border border-[var(--border-default)] hover:border-teal-500/40 text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition"
            >
              <Download className="w-3 h-3" />
              MD
            </button>
          </div>
        </div>

        {/* Project List Scrollable */}
        <div className="flex-1 overflow-y-auto space-y-2 py-2 pr-1">
          {projects.map((p) => {
            const pct = Math.max(4, Math.round((p.tokens.total / maxProjectTokens) * 100));
            return (
              <div
                key={p.path || p.name}
                className="p-2.5 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-default)] hover:border-teal-500/30 transition group shadow-sm"
              >
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <div className="flex items-center gap-2">
                    <span className={`w-5 h-5 rounded-md flex items-center justify-center font-bold text-[11px] ${
                      p.rank === 1 ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30' :
                      p.rank === 2 ? 'bg-slate-300/20 text-slate-200 border border-slate-300/30' :
                      p.rank === 3 ? 'bg-amber-700/20 text-amber-500 border border-amber-700/30' :
                      'bg-[var(--bg-subtle)] text-[var(--text-secondary)]'
                    }`}>
                      {p.rank}
                    </span>
                    <span className="font-bold text-[var(--text-primary)] group-hover:text-teal-400 transition-colors">
                      {p.name}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-medium">
                      {p.primary_model}
                    </span>
                  </div>

                  <div className="flex items-center gap-3 font-mono">
                    <span className="text-teal-400 font-bold">{formatTokens(p.tokens.total)}</span>
                    <span className="text-amber-400 text-[11px]">${p.cost_usd.toFixed(2)}</span>
                  </div>
                </div>

                {/* Relative Token Proportion Bar */}
                <div className="w-full h-1.5 bg-[var(--bg-subtle)] rounded-full overflow-hidden mb-1.5">
                  <div
                    style={{ width: `${pct}%` }}
                    className="h-full bg-gradient-to-r from-teal-500 to-blue-500 rounded-full transition-all duration-500"
                  />
                </div>

                {/* Sub info */}
                <div className="flex items-center justify-between text-[10px] text-[var(--text-muted)]">
                  <span className="truncate max-w-[280px] font-mono opacity-80">{p.path}</span>
                  <div className="flex items-center gap-2">
                    <span>{p.sessions} 会话</span>
                    <span>活跃: {p.last_active_at}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer Notice */}
        <div className="pt-2 border-t border-[var(--border-default)] text-[10px] text-[var(--text-muted)] flex justify-between">
          <span>{exportNotice || '已过滤临时及已删除目录 · 本机真实有效记录'}</span>
          <span>按 Token 降序排列</span>
        </div>
      </div>

      {/* Right 1 Col: Activity Overview Summary */}
      <div className="bg-[var(--bg-card)] border border-[var(--border-default)] rounded-2xl p-4 flex flex-col justify-between shadow-sm">
        <div className="pb-2 border-b border-[var(--border-default)]">
          <h4 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5">
            <PieChart className="w-4 h-4 text-teal-400" />
            <span>活动概览指标</span>
          </h4>
          <span className="text-[10px] text-[var(--text-muted)]">当前口径统计汇总</span>
        </div>

        <div className="space-y-3 py-3">
          {/* Card 1: Active project count */}
          <div className="p-3 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-default)]">
            <span className="text-[11px] text-[var(--text-secondary)]">活跃项目数</span>
            <div className="text-xl font-bold font-mono text-[var(--text-primary)] mt-1">
              {projects.length} <span className="text-xs font-normal text-[var(--text-muted)]">个项目</span>
            </div>
          </div>

          {/* Card 2: Top 1 / Top 3 Concentration */}
          <div className="p-3 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-default)]">
            <span className="text-[11px] text-[var(--text-secondary)]">用量集中度</span>
            <div className="grid grid-cols-2 gap-2 mt-1.5">
              <div>
                <span className="text-[10px] text-[var(--text-muted)]">Top 1 占比</span>
                <div className="text-base font-bold font-mono text-teal-400">{top1Pct}%</div>
              </div>
              <div>
                <span className="text-[10px] text-[var(--text-muted)]">Top 3 占比</span>
                <div className="text-base font-bold font-mono text-purple-400">{top3Pct}%</div>
              </div>
            </div>
          </div>

          {/* Card 3: Most Recently Active */}
          <div className="p-3 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-default)]">
            <div className="flex items-center gap-1 text-[11px] text-[var(--text-secondary)]">
              <Clock className="w-3.5 h-3.5 text-blue-400" />
              <span>最近活跃项目</span>
            </div>
            <div className="font-semibold text-xs text-[var(--text-primary)] mt-1 truncate">
              {recentProject?.name || '暂无项目'}
            </div>
            <div className="text-[10px] text-[var(--text-muted)] mt-0.5">
              {recentProject?.last_active_at || '—'}
            </div>
          </div>
        </div>

        <div className="pt-2 border-t border-[var(--border-default)] text-[10px] text-[var(--text-muted)] text-center">
          所有口径跟随顶栏渠道同步切换
        </div>
      </div>
    </div>
  );
};

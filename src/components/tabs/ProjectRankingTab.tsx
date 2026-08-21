import React, { useState } from 'react';
import { ProjectRankingItem } from '../../types';
import { formatTokens } from '../dashboard/TokenMetricCards';
import { formatModelLabel } from '../../lib/modelLabel';
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
  const [isExporting, setIsExporting] = useState(false);

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
    if (isExporting) return;
    setIsExporting(true);
    let anchor: HTMLAnchorElement | null = null;
    try {
      const res = await exportData(format, channel);
      const mime = format === 'json' ? 'application/json' : format === 'csv' ? 'text/csv' : 'text/markdown';
      const blob = new Blob([res], { type: `${mime};charset=utf-8` });
      const url = URL.createObjectURL(blob);
      // Mount the anchor into the DOM before clicking so the download starts
      // reliably in the Tauri webview, then remove it and delay revoking the
      // object URL so the download is not cut short.
      anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `codexuu-projects-${channel}.${format === 'markdown' ? 'md' : format}`;
      anchor.style.display = 'none';
      document.body.appendChild(anchor);
      anchor.click();
      window.setTimeout(() => {
        URL.revokeObjectURL(url);
        anchor?.remove();
      }, 1000);
      setExportNotice(`已导出 ${format.toUpperCase()} 文件！`);
    } catch (err) {
      setExportNotice(`导出失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsExporting(false);
    }
    setTimeout(() => setExportNotice(null), 3000);
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 dashboard-data-panel">
      {/* Left 2 Cols: Project Ranking Table */}
      <div className="dashboard-panel-card lg:col-span-2 p-4 flex flex-col justify-between overflow-hidden">
        {/* Header with export */}
        <div className="flex items-center justify-between pb-2 border-b border-[var(--border-default)]">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-1.5">
              <Award aria-hidden="true" className="w-4 h-4 text-[var(--warning)]" />
              <span>项目用量排行</span>
            </h3>
          </div>

          <div className="flex items-center gap-1">
            <button
              type="button"
              aria-label="导出项目排行 JSON"
              aria-busy={isExporting}
              disabled={isExporting}
              onClick={() => handleExport('json')}
              className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium bg-[var(--bg-subtle)] border border-[var(--border-default)] hover:border-[color-mix(in_srgb,var(--accent-brand)_40%,transparent)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition disabled:opacity-50 disabled:cursor-wait"
            >
              <Download aria-hidden="true" className="w-3 h-3" />
              JSON
            </button>
            <button
              type="button"
              aria-label="导出项目排行 CSV"
              aria-busy={isExporting}
              disabled={isExporting}
              onClick={() => handleExport('csv')}
              className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium bg-[var(--bg-subtle)] border border-[var(--border-default)] hover:border-[color-mix(in_srgb,var(--accent-brand)_40%,transparent)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition disabled:opacity-50 disabled:cursor-wait"
            >
              <Download aria-hidden="true" className="w-3 h-3" />
              CSV
            </button>
            <button
              type="button"
              aria-label="导出项目排行 Markdown"
              aria-busy={isExporting}
              disabled={isExporting}
              onClick={() => handleExport('markdown')}
              className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium bg-[var(--bg-subtle)] border border-[var(--border-default)] hover:border-[color-mix(in_srgb,var(--accent-brand)_40%,transparent)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition disabled:opacity-50 disabled:cursor-wait"
            >
              <Download aria-hidden="true" className="w-3 h-3" />
              MD
            </button>
          </div>
        </div>

        {/* Project List Scrollable */}
        <div className="flex-1 overflow-y-auto space-y-2 py-2 pr-1">
          {projects.length === 0 && (
            <div className="flex h-full min-h-40 items-center justify-center text-xs text-[var(--text-muted)] text-center">
              暂无仍存在的项目目录
            </div>
          )}
          {projects.map((p) => {
            const pct = Math.max(4, Math.round((p.tokens.total / maxProjectTokens) * 100));
            return (
              <div
                key={p.path || p.name}
                className="p-2.5 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border-default)] hover:border-[color-mix(in_srgb,var(--accent-brand)_30%,transparent)] transition group"
              >
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <div className="flex items-center gap-2">
                    <span className={`w-5 h-5 rounded-md flex items-center justify-center font-bold text-[11px] ${
                      p.rank === 1 ? 'ui-chip-warning' :
                      p.rank === 2 ? 'bg-[var(--bg-subtle)] text-[var(--text-secondary)] border border-[var(--border-default)]' :
                      p.rank === 3 ? 'text-[var(--token-output)] bg-[color-mix(in_srgb,var(--token-output)_14%,transparent)] border border-[color-mix(in_srgb,var(--token-output)_32%,transparent)]' :
                      'bg-[var(--bg-subtle)] text-[var(--text-secondary)]'
                    }`}>
                      {p.rank}
                    </span>
                    <span className="font-bold text-[var(--text-primary)] group-hover:text-[var(--accent-brand)] transition-colors truncate max-w-[180px]" title={p.name}>
                      {p.name}
                    </span>
                    <span className="text-xs px-1.5 py-0.5 rounded ui-chip-7d font-medium whitespace-nowrap" title={p.primary_model}>
                      {formatModelLabel(p.primary_model)}
                    </span>
                  </div>

                  <div className="flex items-center gap-3 font-mono">
                    <span className="text-[var(--accent-brand)] font-bold">{formatTokens(p.tokens.total)}</span>
                    <span className="text-[var(--token-output)] text-xs">${p.cost_usd.toFixed(2)}</span>
                  </div>
                </div>

                {/* Relative Token Proportion Bar */}
                <div className="w-full h-1.5 bg-[var(--bg-subtle)] rounded-full overflow-hidden mb-1.5">
                  <div
                    style={{ width: `${pct}%` }}
                    className="h-full bg-[var(--accent-brand)] rounded-full transition-all duration-500"
                  />
                </div>

                {/* Sub info */}
                <div className="flex items-center justify-between text-xs text-[var(--text-muted)]">
                  <span className="truncate max-w-[280px] font-mono opacity-80" title={p.path} aria-label={`项目路径：${p.path}`}>{p.path}</span>
                  <div className="flex items-center gap-2">
                    <span>{p.sessions} 会话</span>
                    <span>活跃: {p.last_active_at}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {exportNotice && (
          <div className="pt-2 border-t border-[var(--border-default)] text-[11px] text-[var(--text-muted)]">
            <span role="status" aria-live="polite">{exportNotice}</span>
          </div>
        )}
      </div>

      {/* Right 1 Col: Activity Overview Summary */}
      <div className="dashboard-panel-card p-4 flex flex-col justify-start">
        <div className="pb-2 border-b border-[var(--border-default)]">
          <h3 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-1.5">
            <PieChart aria-hidden="true" className="w-4 h-4 text-[var(--accent-brand)]" />
            <span>活动概览</span>
          </h3>
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
                <span className="text-[11px] text-[var(--text-muted)]">Top 1 占比</span>
                <div className="text-base font-bold font-mono text-[var(--accent-brand)]">{top1Pct}%</div>
              </div>
              <div>
                <span className="text-[11px] text-[var(--text-muted)]">Top 3 占比</span>
                <div className="text-base font-bold font-mono text-[var(--quota-7d)]">{top3Pct}%</div>
              </div>
            </div>
          </div>

          {/* Card 3: Most Recently Active */}
          <div className="p-3 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-default)]">
            <div className="flex items-center gap-1 text-[11px] text-[var(--text-secondary)]">
              <Clock aria-hidden="true" className="w-3.5 h-3.5 text-[var(--quota-5h)]" />
              <span>最近活跃项目</span>
            </div>
            <div className="font-semibold text-xs text-[var(--text-primary)] mt-1 truncate">
              {recentProject?.name || '暂无项目'}
            </div>
            <div className="text-[11px] text-[var(--text-muted)] mt-0.5">
              {recentProject?.last_active_at || '—'}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
};

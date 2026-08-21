import React, { useMemo, useState } from 'react';
import { SkillUsageItem } from '../../types';
import { Wrench, Sparkles, Calendar, Folder } from 'lucide-react';

interface SkillUsageTabProps {
  skillsAndTools: SkillUsageItem[];
}

export const SkillUsageTab: React.FC<SkillUsageTabProps> = ({
  skillsAndTools,
}) => {
  const [filterKind, setFilterKind] = useState<'all' | 'tool' | 'skill'>('all');

  const tools = useMemo(() => skillsAndTools.filter((s) => s.kind === 'tool'), [skillsAndTools]);
  const skills = useMemo(() => skillsAndTools.filter((s) => s.kind === 'skill'), [skillsAndTools]);

  const visibleColumns = useMemo(() => {
    const sortByCount = (items: SkillUsageItem[]) => [...items].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
    if (filterKind === 'tool') return [{ kind: 'tool' as const, title: '工具使用 TOP20', items: sortByCount(tools) }];
    if (filterKind === 'skill') return [{ kind: 'skill' as const, title: 'Skill 使用 TOP20', items: sortByCount(skills) }];
    return [
      { kind: 'skill' as const, title: 'Skill 使用 TOP20', items: sortByCount(skills) },
      { kind: 'tool' as const, title: '工具使用 TOP20', items: sortByCount(tools) },
    ];
  }, [filterKind, skillsAndTools, skills, tools]);

  const filteredCount = filterKind === 'all' ? skillsAndTools.length : filterKind === 'tool' ? tools.length : skills.length;

  return (
    <div className="dashboard-panel-card p-4 flex flex-col justify-between dashboard-data-panel">
      {/* Header with Segmented Filter */}
      <div className="flex items-center justify-between pb-2 border-b border-[var(--border-default)]">
        <h3 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-1.5">
          <Wrench aria-hidden="true" className="w-4 h-4 text-[var(--accent-brand)]" />
          <span>Skill 与工具</span>
        </h3>

        {/* Filter Segmented Control */}
        <div
          role="group"
          aria-label="Skill 与工具筛选"
          className="flex items-center p-0.5 bg-[var(--bg-subtle)] border border-[var(--border-default)] rounded-lg text-xs"
        >
          <button
            type="button"
            aria-pressed={filterKind === 'all'}
            onClick={() => setFilterKind('all')}
            className={`px-3 py-1 rounded-md font-medium transition ${
              filterKind === 'all'
                ? 'ui-selected'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
          >
            全部 ({skillsAndTools.length})
          </button>
          <button
            type="button"
            aria-pressed={filterKind === 'tool'}
            onClick={() => setFilterKind('tool')}
            className={`px-3 py-1 rounded-md font-medium transition ${
              filterKind === 'tool'
                ? 'ui-chip-5h'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
          >
            工具 ({tools.length})
          </button>
          <button
            type="button"
            aria-pressed={filterKind === 'skill'}
            onClick={() => setFilterKind('skill')}
            className={`px-3 py-1 rounded-md font-medium transition ${
              filterKind === 'skill'
                ? 'ui-chip-7d'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
          >
            Skill 技能 ({skills.length})
          </button>
        </div>
      </div>

      {/* Two ranked rails mirror the Mac layout while preserving the Windows data model. */}
      <div className={`dashboard-skill-grid flex-1 min-h-0 overflow-y-auto py-2 pr-1 ${visibleColumns.length === 1 ? 'is-single' : ''}`}>
        {visibleColumns.map((column) => {
          const isSkill = column.kind === 'skill';
          const maxCount = Math.max(...column.items.map((item) => item.count), 1);
          const Icon = isSkill ? Sparkles : Wrench;
          return (
            <section key={column.kind} className="dashboard-skill-column" aria-labelledby={`skill-column-${column.kind}`}>
              <div className="flex items-center justify-between gap-2 px-1 pb-2 border-b border-[var(--border-default)]">
                <h4 id={`skill-column-${column.kind}`} className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-1.5">
                  <Icon aria-hidden="true" className={`w-4 h-4 ${isSkill ? 'text-[var(--quota-7d)]' : 'text-[var(--quota-5h)]'}`} />
                  {column.title}
                </h4>
                <span className="text-[11px] text-[var(--text-muted)]">{column.items.length}</span>
              </div>
              {column.items.length === 0 ? (
                <div className="flex min-h-32 items-center justify-center text-xs text-[var(--text-muted)] text-center" role="status">
                  暂无{isSkill ? ' Skill' : '工具'}记录
                </div>
              ) : (
                <div className="space-y-2 pt-2">
                  {column.items.slice(0, 20).map((item) => {
                    const width = Math.max(4, Math.round((item.count / maxCount) * 100));
                    return (
                      <div key={item.name} className="dashboard-skill-row group" title={`${item.name}：${item.count} 次调用`}>
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0 flex items-center gap-2">
                            <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${isSkill ? 'ui-chip-7d' : 'ui-chip-5h'}`}>
                              <Icon aria-hidden="true" className="w-3.5 h-3.5" />
                            </span>
                            <div className="min-w-0">
                              <div className="truncate text-xs font-bold font-mono text-[var(--text-primary)]">{item.name}</div>
                              <div className="truncate text-[11px] text-[var(--text-muted)]">
                                <Calendar aria-hidden="true" className="mr-0.5 inline-block h-3 w-3" />{item.active_days} 天
                                <span className="mx-1">·</span>
                                <Folder aria-hidden="true" className="mr-0.5 inline-block h-3 w-3" />{item.project_count} 项目
                                <span className="mx-1">·</span>{item.last_used_at}
                              </div>
                            </div>
                          </div>
                          <div className="shrink-0 text-right">
                            <div className="font-mono text-sm font-extrabold text-[var(--text-primary)]">{item.count} <span className="text-[11px] font-normal text-[var(--text-muted)]">次</span></div>
                            <div className="text-[10px] text-[var(--text-muted)]">调用</div>
                          </div>
                        </div>
                        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--bg-subtle)]">
                          <div className={`h-full rounded-full transition-all duration-500 ${isSkill ? 'bg-[var(--quota-7d)]' : 'bg-[var(--quota-5h)]'}`} style={{ width: `${width}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          );
        })}
      </div>

      <div className="pt-2 border-t border-[var(--border-default)] text-xs text-[var(--text-muted)]">
        {filteredCount} 项
      </div>
    </div>
  );
};

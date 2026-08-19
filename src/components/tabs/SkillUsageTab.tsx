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

  const filteredItems = useMemo(() => filterKind === 'all'
    ? skillsAndTools
    : filterKind === 'tool'
    ? tools
    : skills, [filterKind, skillsAndTools, skills, tools]);

  return (
    <div className="bg-[var(--bg-card)] border border-[var(--border-default)] rounded-xl p-4 flex flex-col justify-between shadow-sm dashboard-data-panel">
      {/* Header with Segmented Filter */}
      <div className="flex items-center justify-between pb-2 border-b border-[var(--border-default)]">
        <h4 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5">
          <Wrench aria-hidden="true" className="w-4 h-4 text-[var(--accent-brand)]" />
          <span>Skill 与工具</span>
        </h4>

        {/* Filter Segmented Control */}
        <div className="flex items-center p-0.5 bg-[var(--bg-subtle)] border border-[var(--border-default)] rounded-lg text-xs">
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

      {/* Grid of Skill & Tool Cards */}
      <div className="flex-1 overflow-y-auto py-2 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5 pr-1">
        {filteredItems.length === 0 && (
          <div className="col-span-full flex items-center justify-center py-12 text-xs text-[var(--text-muted)]">
            暂无
          </div>
        )}
        {filteredItems.map((item) => {
          const isSkill = item.kind === 'skill';
          return (
            <div
              key={item.name}
              className="p-3 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border-default)] hover:border-[color-mix(in_srgb,var(--accent-brand)_30%,transparent)] transition flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-1.5 truncate max-w-[160px]">
                    {isSkill ? (
                      <Sparkles aria-hidden="true" className="w-3.5 h-3.5 text-[var(--quota-7d)] shrink-0" />
                    ) : (
                      <Wrench aria-hidden="true" className="w-3.5 h-3.5 text-[var(--quota-5h)] shrink-0" />
                    )}
                    <span className="font-bold text-xs text-[var(--text-primary)] truncate font-mono">
                      {item.name}
                    </span>
                  </div>

                  <span className={`text-[11px] px-1.5 py-0.5 rounded font-medium border ${
                    isSkill
                      ? 'ui-chip-7d'
                      : 'ui-chip-5h'
                  }`}>
                    {isSkill ? 'Skill' : 'Tool'}
                  </span>
                </div>

                <div className="flex items-baseline gap-1 my-1">
                  <span className="text-xl font-extrabold font-mono text-[var(--text-primary)]">
                    {item.count}
                  </span>
                  <span className="text-[11px] text-[var(--text-muted)]">次调用</span>
                </div>
              </div>

              {/* Sub details */}
              <div className="flex items-center justify-between pt-2 border-t border-[var(--border-default)]/60 text-[11px] text-[var(--text-muted)]">
                <div className="flex items-center gap-2">
                  <span className="flex items-center gap-0.5">
                    <Calendar aria-hidden="true" className="w-3 h-3" />
                    {item.active_days} 天
                  </span>
                  <span className="flex items-center gap-0.5">
                    <Folder aria-hidden="true" className="w-3 h-3" />
                    {item.project_count} 项目
                  </span>
                </div>
                <span>{item.last_used_at}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="pt-2 border-t border-[var(--border-default)] text-[11px] text-[var(--text-muted)]">
        {filteredItems.length} 项
      </div>
    </div>
  );
};

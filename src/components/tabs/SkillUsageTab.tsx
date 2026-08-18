import React, { useState } from 'react';
import { SkillUsageItem } from '../../types';
import { Wrench, Sparkles, Calendar, Folder, CheckCircle } from 'lucide-react';

interface SkillUsageTabProps {
  skillsAndTools: SkillUsageItem[];
}

export const SkillUsageTab: React.FC<SkillUsageTabProps> = ({
  skillsAndTools,
}) => {
  const [filterKind, setFilterKind] = useState<'all' | 'tool' | 'skill'>('all');

  const tools = skillsAndTools.filter((s) => s.kind === 'tool');
  const skills = skillsAndTools.filter((s) => s.kind === 'skill');

  const filteredItems = filterKind === 'all'
    ? skillsAndTools
    : filterKind === 'tool'
    ? tools
    : skills;

  return (
    <div className="bg-[var(--bg-card)] border border-[var(--border-default)] rounded-2xl p-4 flex flex-col justify-between shadow-sm h-[420px] select-none">
      {/* Header with Segmented Filter */}
      <div className="flex items-center justify-between pb-2 border-b border-[var(--border-default)]">
        <div className="flex items-center gap-2">
          <h4 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5">
            <Wrench className="w-4 h-4 text-teal-400" />
            <span>Skill 与工具真实调用</span>
          </h4>
          <span className="text-[11px] text-[var(--text-muted)]">
            仅统计显式 Function / Tool Call 事件
          </span>
        </div>

        {/* Filter Segmented Control */}
        <div className="flex items-center p-0.5 bg-[var(--bg-subtle)] border border-[var(--border-default)] rounded-lg text-xs">
          <button
            onClick={() => setFilterKind('all')}
            className={`px-3 py-1 rounded-md font-medium transition ${
              filterKind === 'all'
                ? 'bg-teal-500/20 text-teal-300 border border-teal-500/30'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
          >
            全部 ({skillsAndTools.length})
          </button>
          <button
            onClick={() => setFilterKind('tool')}
            className={`px-3 py-1 rounded-md font-medium transition ${
              filterKind === 'tool'
                ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
          >
            工具 ({tools.length})
          </button>
          <button
            onClick={() => setFilterKind('skill')}
            className={`px-3 py-1 rounded-md font-medium transition ${
              filterKind === 'skill'
                ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
          >
            Skill 技能 ({skills.length})
          </button>
        </div>
      </div>

      {/* Grid of Skill & Tool Cards */}
      <div className="flex-1 overflow-y-auto py-2 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5 pr-1">
        {filteredItems.map((item, idx) => {
          const isSkill = item.kind === 'skill';
          return (
            <div
              key={item.name}
              className="p-3 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-default)] hover:border-teal-500/30 transition shadow-sm flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-1.5 truncate max-w-[160px]">
                    {isSkill ? (
                      <Sparkles className="w-3.5 h-3.5 text-purple-400 shrink-0" />
                    ) : (
                      <Wrench className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                    )}
                    <span className="font-bold text-xs text-[var(--text-primary)] truncate font-mono">
                      {item.name}
                    </span>
                  </div>

                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium border ${
                    isSkill
                      ? 'bg-purple-500/10 text-purple-400 border-purple-500/20'
                      : 'bg-blue-500/10 text-blue-400 border-blue-500/20'
                  }`}>
                    {isSkill ? 'Skill' : 'Tool'}
                  </span>
                </div>

                <div className="flex items-baseline gap-1 my-1">
                  <span className="text-xl font-extrabold font-mono text-[var(--text-primary)]">
                    {item.count}
                  </span>
                  <span className="text-[10px] text-[var(--text-muted)]">次调用</span>
                </div>
              </div>

              {/* Sub details */}
              <div className="flex items-center justify-between pt-2 border-t border-[var(--border-default)]/60 text-[10px] text-[var(--text-muted)]">
                <div className="flex items-center gap-2">
                  <span className="flex items-center gap-0.5">
                    <Calendar className="w-3 h-3" />
                    {item.active_days} 天
                  </span>
                  <span className="flex items-center gap-0.5">
                    <Folder className="w-3 h-3" />
                    {item.project_count} 项目
                  </span>
                </div>
                <span>{item.last_used_at}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer Info */}
      <div className="pt-2 border-t border-[var(--border-default)] text-[10px] text-[var(--text-muted)] flex justify-between">
        <span>不按调用次数分摊总金额 · 保持真实调用物理记录</span>
        <span>共统计 {filteredItems.length} 个独立项</span>
      </div>
    </div>
  );
};

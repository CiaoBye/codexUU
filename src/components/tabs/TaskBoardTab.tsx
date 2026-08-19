import React, { useMemo } from 'react';
import { TaskItem } from '../../types';
import { PlayCircle, Clock, CalendarClock, CheckCircle2, Bot, Sparkles, Folder } from 'lucide-react';

interface TaskBoardTabProps {
  tasks: TaskItem[];
}

export const TaskBoardTab: React.FC<TaskBoardTabProps> = ({ tasks }) => {
  const columns = useMemo(() => [
    {
      id: 'running',
      title: '进行中',
      icon: PlayCircle,
      color: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
      dotColor: 'bg-blue-400 animate-pulse',
      items: tasks.filter((t) => t.status === 'running'),
    },
    {
      id: 'pending',
      title: '待处理',
      icon: Clock,
      color: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
      dotColor: 'bg-amber-400',
      items: tasks.filter((t) => t.status === 'pending'),
    },
    {
      id: 'scheduled',
      title: '定时任务',
      icon: CalendarClock,
      color: 'text-purple-400 bg-purple-500/10 border-purple-500/30',
      dotColor: 'bg-purple-400',
      items: tasks.filter((t) => t.status === 'scheduled'),
    },
    {
      id: 'completed',
      title: '已完成',
      icon: CheckCircle2,
      color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
      dotColor: 'bg-emerald-400',
      items: tasks.filter((t) => t.status === 'completed'),
    },
  ], [tasks]);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 dashboard-data-panel">
      {columns.map((col) => {
        const Icon = col.icon;
        return (
          <div
            key={col.id}
            className="bg-[var(--bg-card)] border border-[var(--border-default)] rounded-2xl p-3 flex flex-col h-full shadow-sm overflow-hidden"
          >
            {/* Column Header */}
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-[var(--border-default)]">
              <div className="flex items-center gap-1.5">
                <div className={`p-1 rounded-md ${col.color}`}>
                  <Icon aria-hidden="true" className="w-3.5 h-3.5" />
                </div>
                <span className="text-xs font-bold text-[var(--text-primary)]">{col.title}</span>
              </div>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-[var(--bg-subtle)] text-[var(--text-secondary)] font-mono font-medium">
                {col.items.length}
              </span>
            </div>

            {/* Column Task Cards Scrollable List */}
            <div className="flex-1 overflow-y-auto space-y-2 pr-1">
              {col.items.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-48 text-center text-[var(--text-muted)]">
                  <span className="text-xs opacity-60">暂无任务</span>
                </div>
              ) : (
                col.items.map((task) => (
                  <div
                    key={task.id}
                    className="p-2.5 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-default)] transition group shadow-sm"
                  >
                    {/* Project & Channel Tag */}
                    <div className="flex items-center justify-between mb-1.5 text-[10px]">
                      <div className="flex items-center gap-1 text-[var(--text-muted)] truncate max-w-[140px]">
                        <Folder aria-hidden="true" className="w-3 h-3 shrink-0" />
                        <span className="truncate">{task.project_name}</span>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        {task.channel === 'antigravity' ? (
                          <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-medium">
                            <Sparkles aria-hidden="true" className="w-2.5 h-2.5" />
                            Antigravity
                          </span>
                        ) : task.channel === 'all' ? (
                          <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-teal-500/10 text-teal-400 border border-teal-500/20 font-medium">
                            Codex + Antigravity
                          </span>
                        ) : (
                          <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 font-medium">
                            <Bot aria-hidden="true" className="w-2.5 h-2.5" />
                            Codex
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Task Title */}
                    <p className="text-xs font-medium text-[var(--text-primary)] line-clamp-2 leading-snug group-hover:text-teal-400 transition-colors">
                      {task.title}
                    </p>

                    {/* Footer Time & Status */}
                    <div className="flex items-center justify-between mt-2 pt-1.5 border-t border-[var(--border-default)]/60 text-[10px] text-[var(--text-muted)]">
                      <span>{task.updated_at}</span>
                      <div className="flex items-center gap-1">
                        <span className={`w-1.5 h-1.5 rounded-full ${col.dotColor}`} />
                        <span>{col.title} · {task.thread_count} 线程</span>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

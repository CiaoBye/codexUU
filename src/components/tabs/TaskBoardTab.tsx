import React, { useMemo } from 'react';
import { TaskItem } from '../../types';
import { PlayCircle, Clock, CalendarClock, CheckCircle2, Folder } from 'lucide-react';

interface TaskBoardTabProps {
  tasks: TaskItem[];
}

export const TaskBoardTab: React.FC<TaskBoardTabProps> = ({ tasks }) => {
  const columns = useMemo(() => [
    {
      id: 'running',
      title: '进行中',
      icon: PlayCircle,
      color: 'text-[var(--quota-5h)]',
      items: tasks.filter((t) => t.status === 'running'),
    },
    {
      id: 'pending',
      title: '待处理',
      icon: Clock,
      color: 'text-[var(--warning)]',
      items: tasks.filter((t) => t.status === 'pending'),
    },
    {
      id: 'scheduled',
      title: '定时任务',
      icon: CalendarClock,
      color: 'text-[var(--quota-7d)]',
      items: tasks.filter((t) => t.status === 'scheduled'),
    },
    {
      id: 'completed',
      title: '已完成',
      icon: CheckCircle2,
      color: 'text-[var(--success)]',
      items: tasks.filter((t) => t.status === 'completed'),
    },
  ], [tasks]);

  return (
    <div className="grid grid-cols-4 gap-2 h-full min-h-0 dashboard-data-panel">
      {columns.map((col) => {
        const Icon = col.icon;
        const isEmpty = col.items.length === 0;
        return (
          <section
            key={col.id}
            aria-label={col.title}
            className={`flex flex-col h-full min-h-0 overflow-hidden rounded-lg p-2 ${
              isEmpty
                ? ''
                : 'bg-[var(--bg-card)] border border-[var(--border-default)]'
            }`}
          >
            <div className="flex items-center justify-between gap-1 pb-1.5 mb-1.5 shrink-0">
              <div className="flex items-center gap-1.5 min-w-0">
                <Icon aria-hidden="true" className={`w-3.5 h-3.5 ${col.color}`} />
                <span className="text-xs font-semibold text-[var(--text-primary)] truncate">{col.title}</span>
              </div>
              <span className="text-[11px] font-mono text-[var(--text-muted)] tabular-nums">
                {col.items.length}
              </span>
            </div>

            <div className="flex-1 overflow-y-auto space-y-1.5 min-h-0">
              {col.items.map((task) => (
                <div
                  key={task.id}
                  className="px-2 py-1.5 rounded-md bg-[var(--bg-elevated)] border border-[var(--border-default)]"
                >
                  <div className="flex items-center gap-1.5 text-[11px]">
                    <Folder aria-hidden="true" className="w-3 h-3 shrink-0 text-[var(--text-muted)]" />
                    <span className="truncate text-[var(--text-muted)]">{task.project_name}</span>
                    {task.channel === 'antigravity' ? (
                      <span className="ml-auto px-1 py-px rounded ui-chip-7d font-medium shrink-0">AG</span>
                    ) : task.channel === 'all' ? (
                      <span className="ml-auto px-1 py-px rounded ui-selected font-medium shrink-0">全部</span>
                    ) : (
                      <span className="ml-auto px-1 py-px rounded ui-chip-5h font-medium shrink-0">Codex</span>
                    )}
                  </div>

                  <p className="mt-1 text-xs font-medium text-[var(--text-primary)] line-clamp-1 leading-snug">
                    {task.title}
                  </p>

                  <div className="mt-1 flex items-center justify-between text-[11px] text-[var(--text-muted)]">
                    <span className="truncate">{task.updated_at}</span>
                    <span className="font-mono tabular-nums shrink-0 ml-2">{task.thread_count}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
};

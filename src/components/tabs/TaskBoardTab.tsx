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
            aria-labelledby={`task-column-${col.id}-title`}
            className="dashboard-task-column flex flex-col h-full min-h-0 overflow-hidden p-2"
          >
            <div className="flex items-center justify-between gap-1 pb-1.5 mb-1.5 shrink-0">
              <div className="flex items-center gap-1.5 min-w-0">
                <Icon aria-hidden="true" className={`w-3.5 h-3.5 ${col.color}`} />
                <h3 id={`task-column-${col.id}-title`} className="text-sm font-semibold text-[var(--text-primary)] truncate">{col.title}</h3>
              </div>
              <span className="text-xs font-mono text-[var(--text-muted)] tabular-nums">
                {col.items.length}
              </span>
            </div>

            <div className={`dashboard-task-column-body flex-1 min-h-0 ${isEmpty ? 'flex items-center justify-center border border-dashed border-[var(--border-default)]' : 'overflow-y-auto space-y-1.5'}`}>
              {isEmpty ? (
                <p className="px-2 text-center text-xs text-[var(--text-muted)]" role="status">
                  暂无{col.title}任务
                </p>
              ) : col.items.map((task) => (
                <div
                  key={task.id}
                  className="px-2 py-1.5 rounded-md bg-[var(--bg-elevated)] border border-[var(--border-default)]"
                  title={task.title}
                >
                  <div className="flex items-center gap-1.5 text-xs">
                    <Folder aria-hidden="true" className="w-3 h-3 shrink-0 text-[var(--text-muted)]" />
                    <span className="truncate text-[var(--text-muted)]" title={`${task.project_name}\n${task.project_path}`}>
                      {task.project_name}
                    </span>
                    {task.channel === 'antigravity' ? (
                      <span className="ml-auto px-1 py-px rounded ui-chip-7d font-medium shrink-0">AG</span>
                    ) : task.channel === 'all' ? (
                      <span className="ml-auto px-1 py-px rounded ui-selected font-medium shrink-0">全部</span>
                    ) : (
                      <span className="ml-auto px-1 py-px rounded ui-chip-5h font-medium shrink-0">Codex</span>
                    )}
                  </div>

                  <p className="mt-1 text-xs font-medium text-[var(--text-primary)] line-clamp-2 leading-snug min-h-[2rem]">
                    {task.title}
                  </p>

                  <div className="mt-1 flex items-center justify-between text-xs text-[var(--text-muted)]">
                    <span className="truncate" title={task.updated_at}>{task.updated_at}</span>
                    <span className="font-mono tabular-nums shrink-0 ml-2" aria-label={`${task.thread_count} 个线程`}>
                      {task.thread_count}
                    </span>
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

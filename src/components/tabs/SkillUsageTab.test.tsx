import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { SkillUsageTab } from './SkillUsageTab';
import type { SkillUsageItem } from '../../types';

const items: SkillUsageItem[] = [
  {
    name: 'exec',
    kind: 'tool',
    count: 3,
    active_days: 2,
    project_count: 1,
    last_used_at: '今天 15:00',
  },
  {
    name: 'browser',
    kind: 'skill',
    count: 1,
    active_days: 1,
    project_count: 1,
    last_used_at: '今天 14:00',
  },
];

describe('SkillUsageTab filter semantics', () => {
  it('exposes the filter buttons as an accessible group and preserves pressed state', () => {
    render(<SkillUsageTab skillsAndTools={items} />);

    const group = screen.getByRole('group', { name: 'Skill 与工具筛选' });
    expect(group).toBeDefined();

    const allButton = screen.getByRole('button', { name: '全部 (2)' });
    const toolButton = screen.getByRole('button', { name: '工具 (1)' });
    const skillButton = screen.getByRole('button', { name: 'Skill 技能 (1)' });
    expect(allButton.getAttribute('aria-pressed')).toBe('true');
    expect(toolButton.getAttribute('aria-pressed')).toBe('false');
    expect(skillButton.getAttribute('aria-pressed')).toBe('false');

    fireEvent.click(toolButton);
    expect(toolButton.getAttribute('aria-pressed')).toBe('true');
    expect(allButton.getAttribute('aria-pressed')).toBe('false');
  });
});

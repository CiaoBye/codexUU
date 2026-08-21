import React from 'react';
import { describe, expect, it } from 'vitest';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { UsageTrendsTab } from './UsageTrendsTab';
import type { DailyActivity } from '../../types';

function activity(date: string, total: number): DailyActivity {
  return {
    date,
    tokens: {
      uncached_input: total,
      cached_input: 0,
      output: 0,
      total,
    },
    cost_usd: total / 100,
    sessions: total > 0 ? 1 : 0,
  };
}

describe('UsageTrendsTab continuous natural-day heatmap', () => {
  it('shows numeric intensity, keyboard labels, and an accessible detail table', () => {
    render(
      <UsageTrendsTab
        dailyActivities={[
          activity('2026-08-18', 25),
          activity('2026-08-20', 100),
        ]}
        models={[]}
        today="2026-08-20"
      />,
    );

    const heatmap = screen.getByRole('grid', { name: '连续自然日热力图' });
    const cells = within(heatmap).getAllByRole('gridcell');
    expect(cells).toHaveLength(7);
    expect(cells[0].getAttribute('tabindex')).toBe('0');
    expect(cells.slice(1).every((cell) => cell.getAttribute('tabindex') === '-1')).toBe(true);

    act(() => {
      cells[0].focus();
      fireEvent.keyDown(cells[0], { key: 'ArrowDown' });
    });
    expect(document.activeElement).toBe(cells[1]);
    expect(cells[0].getAttribute('tabindex')).toBe('-1');
    expect(cells[1].getAttribute('tabindex')).toBe('0');

    const missingDay = within(heatmap).getByRole('gridcell', {
      name: '2026-08-19，Token 0，强度 0/4',
    });
    expect(missingDay.getAttribute('title')).toBe('2026-08-19，Token 0，强度 0/4');
    expect(missingDay.textContent).toBe('0');

    const peakDay = within(heatmap).getByRole('gridcell', {
      name: '2026-08-20，Token 100，强度 4/4',
    });
    expect(peakDay.textContent).toBe('4');

    expect(screen.getByText('日期范围：2026-08-14 至 2026-08-20')).toBeDefined();
    expect(screen.getByText(/当前日期：2026-08-15/)).toBeDefined();

    const legend = screen.getByRole('list', { name: '热力图强度图例' });
    expect(within(legend).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      '0',
      '1',
      '2',
      '3',
      '4',
    ]);
    expect(screen.getByRole('table', { name: '用量趋势明细' })).toBeDefined();
  });

  it('puts the primary trend chart before the heatmap visually and labels the metric', () => {
    const { container } = render(
      <UsageTrendsTab
        dailyActivities={[activity('2026-08-20', 100)]}
        models={[]}
        today="2026-08-20"
      />,
    );

    expect(screen.getByRole('img', { name: /趋势图/ }).closest('.order-1')).not.toBeNull();
    expect(screen.getByRole('heading', { name: '趋势 · Token' })).toBeDefined();
    expect(container.querySelector('[role="grid"]')?.closest('.order-2')).not.toBeNull();
  });

  it('uses roving tabindex for the trend range tabs and exposes month ticks', () => {
    render(
      <UsageTrendsTab
        dailyActivities={[
          activity('2026-07-25', 25),
          activity('2026-08-20', 100),
        ]}
        models={[]}
        today="2026-08-20"
      />,
    );

    const rangeTabs = within(screen.getByRole('tablist', { name: '趋势统计范围' })).getAllByRole('tab');
    expect(rangeTabs.map((tab) => tab.getAttribute('tabindex'))).toEqual(['0', '-1', '-1', '-1']);

    act(() => {
      rangeTabs[0].focus();
      fireEvent.keyDown(rangeTabs[0], { key: 'ArrowRight' });
    });
    expect(document.activeElement).toBe(rangeTabs[1]);
    expect(rangeTabs[0].getAttribute('tabindex')).toBe('-1');
    expect(rangeTabs[1].getAttribute('tabindex')).toBe('0');
    expect(rangeTabs[1].getAttribute('aria-selected')).toBe('true');

    act(() => fireEvent.keyDown(rangeTabs[1], { key: 'End' }));
    expect(document.activeElement).toBe(rangeTabs[3]);
    expect(rangeTabs[3].getAttribute('tabindex')).toBe('0');
    expect(rangeTabs[3].getAttribute('aria-selected')).toBe('true');

    expect(screen.getByText('2026-07')).toBeDefined();
    expect(screen.getByText('2026-08')).toBeDefined();
  });
});

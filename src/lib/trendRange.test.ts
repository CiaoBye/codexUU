import { describe, expect, it } from 'vitest';
import { DailyActivity } from '../types';
import { fillDailyRange } from './trendRange';

function activity(date: string, total: number): DailyActivity {
  return {
    date,
    tokens: {
      uncached_input: total,
      cached_input: 0,
      output: 0,
      total,
    },
    cost_usd: 0,
    sessions: total > 0 ? 1 : 0,
  };
}

describe('fillDailyRange', () => {
  it('fills missing days in the last 7-day window with zeros', () => {
    const filled = fillDailyRange(
      [activity('2026-08-19', 10), activity('2026-08-17', 4)],
      'daily',
      '2026-08-19',
    );
    expect(filled.map((item) => item.date)).toEqual([
      '2026-08-13',
      '2026-08-14',
      '2026-08-15',
      '2026-08-16',
      '2026-08-17',
      '2026-08-18',
      '2026-08-19',
    ]);
    expect(filled.find((item) => item.date === '2026-08-18')?.tokens.total).toBe(0);
    expect(filled.find((item) => item.date === '2026-08-19')?.tokens.total).toBe(10);
  });

  it('fills from Monday through today for the weekly window', () => {
    // 2026-08-19 is Wednesday, so Monday is 2026-08-17.
    const filled = fillDailyRange([activity('2026-08-19', 1)], 'weekly', '2026-08-19');
    expect(filled.map((item) => item.date)).toEqual([
      '2026-08-17',
      '2026-08-18',
      '2026-08-19',
    ]);
  });
});

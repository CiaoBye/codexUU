import { DailyActivity } from '../types';

export type TrendPeriod = 'daily' | 'weekly' | 'monthly' | 'all';

export function utcDate(dateStr: string): Date {
  return new Date(`${dateStr}T00:00:00Z`);
}

export function formatUtcDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function addUtcDays(date: Date, days: number): Date {
  const next = new Date(date.getTime());
  next.setUTCDate(next.getUTCDate() + days);
  return next;
}

export function rangeStart(period: TrendPeriod, todayStr: string, earliestDate?: string): Date {
  const today = utcDate(todayStr);
  if (period === 'daily') {
    return addUtcDays(today, -6);
  }
  if (period === 'weekly') {
    const day = today.getUTCDay();
    const diffToMonday = day === 0 ? 6 : day - 1;
    return addUtcDays(today, -diffToMonday);
  }
  if (period === 'monthly') {
    return new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), 1));
  }
  if (earliestDate) {
    const earliest = utcDate(earliestDate);
    return earliest < today ? earliest : today;
  }
  return today;
}

const EMPTY_TOKENS = {
  uncached_input: 0,
  cached_input: 0,
  output: 0,
  total: 0,
};

export function fillDailyRange(
  dailyActivities: DailyActivity[],
  period: TrendPeriod,
  todayStr: string,
): DailyActivity[] {
  const byDate = new Map(dailyActivities.map((activity) => [activity.date, activity]));
  const earliest = dailyActivities
    .map((activity) => activity.date)
    .sort()[0];
  const start = rangeStart(period, todayStr, earliest);
  const today = utcDate(todayStr);
  if (Number.isNaN(start.getTime()) || Number.isNaN(today.getTime()) || start > today) {
    return [];
  }

  const filled: DailyActivity[] = [];
  for (let cursor = start; cursor <= today; cursor = addUtcDays(cursor, 1)) {
    const date = formatUtcDate(cursor);
    filled.push(
      byDate.get(date) ?? {
        date,
        tokens: { ...EMPTY_TOKENS },
        cost_usd: 0,
        sessions: 0,
      },
    );
  }
  return filled;
}

export function dateInRange(
  dateStr: string,
  period: TrendPeriod,
  todayStr: string,
): boolean {
  if (period === 'all') return dateStr <= todayStr;
  const today = utcDate(todayStr);
  const date = utcDate(dateStr);
  if (Number.isNaN(date.getTime()) || date > today) return false;
  return date >= rangeStart(period, todayStr) && date <= today;
}

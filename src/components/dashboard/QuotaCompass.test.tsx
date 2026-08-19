import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { QuotaCompass } from './QuotaCompass';
import type { QuotaSnapshot } from '../../types';

function quotaWithFamilies(): QuotaSnapshot {
  return {
    five_hour_used_ratio: null,
    five_hour_remaining_ratio: null,
    five_hour_reset_at: null,
    seven_day_used_ratio: null,
    seven_day_remaining_ratio: null,
    seven_day_reset_at: null,
    has_five_hour: false,
    has_seven_day: false,
    source: 'test',
    status: 'healthy',
    last_updated: '',
    families: [
      {
        id: 'gemini',
        label: 'Gemini',
        five_hour_used_ratio: 0.1,
        five_hour_remaining_ratio: 0.9,
        five_hour_reset_at: null,
        seven_day_used_ratio: 0.2,
        seven_day_remaining_ratio: 0.8,
        seven_day_reset_at: null,
        has_five_hour: true,
        has_seven_day: true,
      },
      {
        id: 'claude',
        label: 'Claude',
        five_hour_used_ratio: 0.3,
        five_hour_remaining_ratio: 0.7,
        five_hour_reset_at: null,
        seven_day_used_ratio: 0.4,
        seven_day_remaining_ratio: 0.6,
        seven_day_reset_at: null,
        has_five_hour: true,
        has_seven_day: true,
      },
    ],
  };
}

const noop = () => {};

describe('QuotaCompass accessibility', () => {
  it('renders exactly one quota-mode toggle: the center ring', () => {
    render(<QuotaCompass quota={quotaWithFamilies()} quotaMode="used" onToggleQuotaMode={noop} />);
    // Only a single interactive quota-mode toggle should be focusable.
    const toggles = screen.getAllByLabelText(/切换额度口径/);
    expect(toggles.length).toBe(1);
  });

  it('the family tablist uses roving tabindex and arrow keys', () => {
    render(<QuotaCompass quota={quotaWithFamilies()} quotaMode="used" onToggleQuotaMode={noop} />);
    const gemini = screen.getByRole('tab', { name: 'Gemini' });
    const claude = screen.getByRole('tab', { name: 'Claude' });
    expect(gemini.getAttribute('tabindex')).toBe('0');
    expect(claude.getAttribute('tabindex')).toBe('-1');

    fireEvent.keyDown(gemini, { key: 'ArrowRight' });
    expect(claude.getAttribute('aria-selected')).toBe('true');
    expect(claude.getAttribute('tabindex')).toBe('0');
    expect(gemini.getAttribute('tabindex')).toBe('-1');

    fireEvent.keyDown(claude, { key: 'ArrowLeft' });
    expect(gemini.getAttribute('aria-selected')).toBe('true');
  });

  it('only the selected family tab carries aria-controls', () => {
    render(<QuotaCompass quota={quotaWithFamilies()} quotaMode="used" onToggleQuotaMode={noop} />);
    const gemini = screen.getByRole('tab', { name: 'Gemini' });
    const claude = screen.getByRole('tab', { name: 'Claude' });
    expect(gemini.getAttribute('aria-controls')).toBe('quota-family-panel');
    expect(claude.getAttribute('aria-controls')).toBeNull();
  });
});

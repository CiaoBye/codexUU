import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { TokenMetricCards } from './TokenMetricCards';

describe('TokenMetricCards', () => {
  it('shows the numeric split for uncached, cached, and output tokens', () => {
    render(
      <TokenMetricCards
        tokens={{
          today: { uncached_input: 1_000_000, cached_input: 2_000_000, output: 3_000, total: 3_003_000 },
          week: { uncached_input: 4_000_000, cached_input: 5_000_000, output: 6_000, total: 9_006_000 },
          month: { uncached_input: 7_000_000, cached_input: 8_000_000, output: 9_000, total: 15_009_000 },
          all_time: { uncached_input: 10_000_000, cached_input: 11_000_000, output: 12_000, total: 21_012_000 },
        }}
      />,
    );

    expect(screen.getByText('1.00M')).toBeTruthy();
    expect(screen.getByText('2.00M')).toBeTruthy();
    expect(screen.getByText('3.0k')).toBeTruthy();
    expect(screen.getByTitle('缓存 2.00M')).toBeTruthy();
  });
});

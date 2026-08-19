import { describe, it, expect } from 'vitest';
import { formatModelLabel } from './modelLabel';

describe('formatModelLabel', () => {
  it('turns machine ids into readable names', () => {
    expect(formatModelLabel('gemini-3.1-pro-low')).toBe('Gemini 3.1 Pro');
    expect(formatModelLabel('claude-opus-4-6-thinking')).toBe('Claude Opus 4.6');
    expect(formatModelLabel('unknown')).toBe('未知模型');
  });
});

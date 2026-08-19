import { describe, it, expect } from 'vitest';
import { createLatestWins } from './requestGuard';

describe('createLatestWins', () => {
  it('lets the newest request commit and discards stale ones', () => {
    const guard = createLatestWins();
    const first = guard.next();
    const second = guard.next();

    // First request resolves after the second — it must not commit.
    expect(second.isCurrent()).toBe(true);
    first.commit(() => 'stale');
    expect(second.result).toBeUndefined();

    expect(first.isCurrent()).toBe(false);
    second.commit(() => 'fresh');
    expect(second.result).toBe('fresh');
  });

  it('commits atomically: the result is only set for the active request', () => {
    const guard = createLatestWins();
    const a = guard.next();
    const b = guard.next();
    a.commit(() => 'A');
    expect(b.result).toBeUndefined();
    b.commit(() => 'B');
    expect(b.result).toBe('B');
  });

  it('does not run a stale commit callback at all', () => {
    const guard = createLatestWins();
    const a = guard.next();
    guard.next();
    let sideEffect = 0;
    a.commit(() => { sideEffect += 1; return 'x'; });
    expect(sideEffect).toBe(0);
  });
});

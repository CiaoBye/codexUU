/**
 * Latest-wins guard for async request ordering.
 *
 * When multiple fetches (init, channel switch, refresh, timezone refetch,
 * widget polling) can be in flight at once, only the newest one should be
 * allowed to commit its result to the UI. Older in-flight responses must be
 * dropped so a slow stale response never overwrites a fresher snapshot.
 *
 * Usage:
 *   const guard = createLatestWins();
 *   ...
 *   const token = guard.next();
 *   const data = await fetch();
 *   token.commit(() => ({ ...data })); // no-op if a newer token exists
 */
export interface RequestToken {
  /** True only while this token is still the most recent. */
  isCurrent(): boolean;
  /**
   * Run `commit` (which produces the UI mutation) only if this token is still
   * the latest. The produced value is stored on `result` for tests/observers.
   */
  commit<T>(commit: () => T): T | undefined;
  /** The value produced by the most recent successful commit (empty until then). */
  readonly result: unknown;
}

export interface LatestWinsGuard {
  next(): RequestToken;
}

export function createLatestWins(): LatestWinsGuard {
  let sequence = 0;
  let latest = 0;
  let committedValue: unknown;

  return {
    next() {
      latest = ++sequence;
      const mySequence = latest;
      return {
        isCurrent() {
          return mySequence === latest;
        },
        commit<T>(commit: () => T): T | undefined {
          if (mySequence !== latest) return undefined;
          const value = commit();
          committedValue = value;
          return value;
        },
        get result(): unknown {
          return committedValue;
        },
      };
    },
  };
}

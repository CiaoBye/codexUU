import { describe, it, expect, beforeEach } from 'vitest';
import { EMPTY_SNAPSHOT } from '../api';
import {
  readCachedSnapshot,
  writeCachedSnapshot,
  clearCachedSnapshot,
  legacyKeyName,
} from './snapshotCache';

describe('snapshotCache (channel-scoped)', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  function snapshotFor(channel: 'codex' | 'antigravity' | 'all', total: number) {
    return {
      ...EMPTY_SNAPSHOT,
      channel,
      timestamp: '2026-08-19 16:51:00',
      tokens: {
        ...EMPTY_SNAPSHOT.tokens,
        all_time: { uncached_input: total, cached_input: 0, output: 0, total },
      },
    };
  }

  it('stores each channel under its own key', () => {
    writeCachedSnapshot(snapshotFor('codex', 10));
    writeCachedSnapshot(snapshotFor('antigravity', 20));
    expect(readCachedSnapshot('codex')?.tokens.all_time.total).toBe(10);
    expect(readCachedSnapshot('antigravity')?.tokens.all_time.total).toBe(20);
    expect(readCachedSnapshot('all')).toBeNull();
  });

  it('never returns another channel from the requested channel', () => {
    writeCachedSnapshot(snapshotFor('antigravity', 99));
    expect(readCachedSnapshot('codex')).toBeNull();
  });

  it('migrates the legacy single-key snapshot into the channel it belongs to', () => {
    const legacy = snapshotFor('codex', 42);
    sessionStorage.setItem(legacyKeyName(), JSON.stringify(legacy));
    expect(readCachedSnapshot('codex')?.tokens.all_time.total).toBe(42);
    // Legacy entry is removed after migration to avoid future ambiguity.
    expect(sessionStorage.getItem(legacyKeyName())).toBeNull();
  });

  it('ignores empty snapshots without a timestamp', () => {
    writeCachedSnapshot(EMPTY_SNAPSHOT);
    expect(readCachedSnapshot('codex')).toBeNull();
  });

  it('clears only the requested channel', () => {
    writeCachedSnapshot(snapshotFor('codex', 1));
    writeCachedSnapshot(snapshotFor('all', 2));
    clearCachedSnapshot('codex');
    expect(readCachedSnapshot('codex')).toBeNull();
    expect(readCachedSnapshot('all')?.tokens.all_time.total).toBe(2);
  });
});

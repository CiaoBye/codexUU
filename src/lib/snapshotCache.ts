import { DashboardSnapshot } from '../types';

const LEGACY_STORAGE_KEY = 'codexuu.last-snapshot';
const KEY_NAMESPACE = 'codexuu.last-snapshot:';
export const legacyKeyName = (): string => LEGACY_STORAGE_KEY;

function keyFor(channel: DashboardSnapshot['channel']): string {
  return `${KEY_NAMESPACE}${channel}`;
}

function isSnapshot(value: unknown): value is DashboardSnapshot {
  if (!value || typeof value !== 'object') return false;
  const snapshot = value as DashboardSnapshot;
  return Boolean(
    snapshot.timestamp
    && snapshot.tokens
    && typeof snapshot.tokens.all_time?.total === 'number',
  );
}

function normalizeSnapshot(snapshot: DashboardSnapshot): DashboardSnapshot {
  // Snapshots written before the per-provider quota map was introduced are
  // still valid. Rehydrate the compatibility map at the cache boundary so
  // every consumer can rely on the current shape.
  if (snapshot.quotas && typeof snapshot.quotas === 'object' && !Array.isArray(snapshot.quotas)) return snapshot;
  return {
    ...snapshot,
    quotas: { [snapshot.channel]: snapshot.quota },
  };
}

/**
 * Read the cached snapshot for one channel.
 *
 * The cache is channel-scoped so the first frame of a channel never shows data
 * that belongs to another channel. Any legacy single-key snapshot (written by
 * older versions) is migrated into its own channel key and then removed.
 */
export function readCachedSnapshot(
  channel: DashboardSnapshot['channel'],
): DashboardSnapshot | null {
  try {
    const raw = sessionStorage.getItem(keyFor(channel));
    if (raw) {
      const parsed: unknown = JSON.parse(raw);
      if (isSnapshot(parsed) && parsed.channel === channel) return normalizeSnapshot(parsed);
    }
  } catch {
    // Fall through to legacy migration below.
  }

  // Migrate the legacy single-key snapshot written by versions < 1.3.14.
  try {
    const legacyRaw = sessionStorage.getItem(LEGACY_STORAGE_KEY);
    if (!legacyRaw) return null;
    const parsed: unknown = JSON.parse(legacyRaw);
    if (!isSnapshot(parsed)) {
      sessionStorage.removeItem(LEGACY_STORAGE_KEY);
      return null;
    }
    const legacyChannel = parsed.channel;
    const normalized = normalizeSnapshot(parsed);
    if (legacyChannel === channel) {
      sessionStorage.removeItem(LEGACY_STORAGE_KEY);
      return normalized;
    }
    // The legacy snapshot belongs to a different channel — keep it there, do
    // not leak it into the requested channel's first frame.
    sessionStorage.setItem(keyFor(legacyChannel), JSON.stringify(normalized));
    sessionStorage.removeItem(LEGACY_STORAGE_KEY);
    return null;
  } catch {
    return null;
  }
}

export function writeCachedSnapshot(snapshot: DashboardSnapshot): void {
  if (!snapshot.timestamp) return;
  try {
    sessionStorage.setItem(keyFor(snapshot.channel), JSON.stringify(snapshot));
  } catch {
    // Ignore quota / private-mode failures; live fetch remains the source of truth.
  }
}

export function clearCachedSnapshot(channel: DashboardSnapshot['channel']): void {
  try {
    sessionStorage.removeItem(keyFor(channel));
  } catch {
    // Ignore.
  }
}

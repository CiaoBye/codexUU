/**
 * Minimal roving-tabindex helpers for ARIA tablists.
 *
 * A tablist with roving tabindex keeps only the selected tab focusable
 * (tabIndex 0) and the others out of the sequential focus order (tabIndex -1),
 * so keyboard users navigate tabs with the arrow keys instead of tabbing
 * through every tab. These helpers are pure so they are easy to test and reuse
 * across the dashboard tablist and the quota-family tablist.
 */

const NAV_KEYS = new Set(['ArrowRight', 'ArrowLeft', 'Home', 'End']);

/** True for keys that drive roving navigation (not selection keys like Enter). */
export function isTabListNavKey(key: string): boolean {
  return NAV_KEYS.has(key);
}

/** The id to select when moving focus/selection one tab forward (wrapping). */
export function nextTabId(ids: string[], currentId: string): string {
  const index = ids.indexOf(currentId);
  if (index === -1) return ids[0];
  return ids[(index + 1) % ids.length];
}

/** The id to select when moving focus/selection one tab backward (wrapping). */
export function prevTabId(ids: string[], currentId: string): string {
  const index = ids.indexOf(currentId);
  if (index === -1) return ids[ids.length - 1];
  return ids[(index - 1 + ids.length) % ids.length];
}

/**
 * aria-controls may only point at a panel that actually exists in the DOM.
 * Only the active tab's panel is rendered, so only the active tab should carry
 * an aria-controls attribute.
 */
export function ariaControlsOnlyOnActive(tabId: string, activeId: string): boolean {
  return tabId === activeId;
}

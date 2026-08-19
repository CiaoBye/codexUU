import { describe, it, expect } from 'vitest';
import {
  nextTabId,
  prevTabId,
  isTabListNavKey,
  ariaControlsOnlyOnActive,
} from './rovingTabs';

describe('rovingTabs', () => {
  const ids = ['tasks', 'trends', 'projects', 'skills'];

  it('moves forward with ArrowRight and wraps past the last tab', () => {
    expect(nextTabId(ids, 'trends')).toBe('projects');
    expect(nextTabId(ids, 'skills')).toBe('tasks'); // wrap
  });

  it('moves backward with ArrowLeft and wraps before the first tab', () => {
    expect(prevTabId(ids, 'projects')).toBe('trends');
    expect(prevTabId(ids, 'tasks')).toBe('skills'); // wrap
  });

  it('recognises only the horizontal navigation keys and Home/End', () => {
    expect(isTabListNavKey('ArrowRight')).toBe(true);
    expect(isTabListNavKey('ArrowLeft')).toBe(true);
    expect(isTabListNavKey('Home')).toBe(true);
    expect(isTabListNavKey('End')).toBe(true);
    expect(isTabListNavKey('Enter')).toBe(false);
    expect(isTabListNavKey('ArrowUp')).toBe(false);
    expect(isTabListNavKey('ArrowDown')).toBe(false);
  });

  it('keeps aria-controls only on the active tab (no dangling panel target)', () => {
    expect(ariaControlsOnlyOnActive('trends', 'trends')).toBe(true);
    expect(ariaControlsOnlyOnActive('tasks', 'trends')).toBe(false);
  });
});

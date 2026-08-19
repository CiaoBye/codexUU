import { describe, it, expect } from 'vitest';
import { installDesktopPageGuards } from './desktopGuards';

describe('desktop page guards', () => {
  it('blocks F5 and Ctrl+R so the desktop window does not reload like a browser', () => {
    installDesktopPageGuards();

    const f5 = new KeyboardEvent('keydown', { key: 'F5', bubbles: true, cancelable: true });
    window.dispatchEvent(f5);
    expect(f5.defaultPrevented).toBe(true);

    const ctrlR = new KeyboardEvent('keydown', {
      key: 'r',
      ctrlKey: true,
      bubbles: true,
      cancelable: true,
    });
    window.dispatchEvent(ctrlR);
    expect(ctrlR.defaultPrevented).toBe(true);
  });
});

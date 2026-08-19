import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { App } from './App';
import { formatTokens } from './components/dashboard/TokenMetricCards';
import { EMPTY_SNAPSHOT, DEFAULT_SETTINGS } from './api';
import type { DashboardSnapshot, AppSettings } from './types';
// Static import forces the mocked core module to initialise (its factory sets
// the invoke handle) even before any Tauri runtime is enabled.
import { invoke as tauriInvoke } from '@tauri-apps/api/core';

function freshSnapshot(channel: DashboardSnapshot['channel'], total: number): DashboardSnapshot {
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

//
// Mock the Tauri boundary: `invoke` from @tauri-apps/api/core and the
// `__TAURI_INTERNALS__` environment flag that `isTauri()` checks. We never
// mock ./api directly, so the real api wiring is exercised end-to-end.
//
vi.mock('@tauri-apps/api/core', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tauri-apps/api/core')>();
  const invokeHandlers: Record<string, (args: any) => unknown> = {
    get_settings: () => DEFAULT_SETTINGS,
    get_dashboard_snapshot: (args) => freshSnapshot(args.channel ?? 'codex', 0),
    refresh_data: (args) => freshSnapshot(args.scope ?? 'all', 0),
    save_settings: (args) => args.settings,
    toggle_desktop_widget: () => undefined,
    set_widget_style: () => undefined,
    is_main_window_maximized: () => false,
    minimize_main_window: () => undefined,
    close_main_window: () => undefined,
  };
  const invoke = vi.fn(async (cmd: string, args?: any) => {
    const handler = invokeHandlers[cmd];
    if (!handler) throw new Error(`Unexpected invoke command: ${cmd}`);
    return handler(args);
  });
  return { ...actual, invoke };
});

// The static import above initialises the mocked core module; this is the SAME
// mocked vi.fn the tests drive directly (no extra capture needed).
const invokeMock = vi.mocked(tauriInvoke);

// Simulate a Tauri runtime so api.isTauri() returns true and invoke is used.
function enableTauri() {
  (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = { invoke: true };
}

function disableTauri() {
  delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
}

describe('CodexUU 1.0 Architecture & Frontend Tests', () => {
  beforeEach(() => {
    sessionStorage.clear();
    disableTauri(); // default: browser mode (api returns empty/defaults)
  });

  it('formats token numbers with correct suffixes', () => {
    expect(formatTokens(500)).toBe('500');
    expect(formatTokens(1500)).toBe('1.5k');
    expect(formatTokens(2_400_000)).toBe('2.40M');
    expect(formatTokens(1_200_000_000)).toBe('1.20B');
  });

  it('renders dual-channel TopNav correctly', async () => {
    render(<App />);
    await waitFor(() => expect(screen.getAllByText('CodexUU').length).toBeGreaterThan(0));
    expect(screen.getByText('Codex 官方')).toBeDefined();
    expect(screen.getAllByText('Antigravity').length).toBeGreaterThan(0);
    expect(screen.getByLabelText('打开项目排行')).toBeDefined();
    expect(screen.getByLabelText('最大化窗口')).toBeDefined();
    expect(screen.queryByLabelText('刷新')).toBeNull();
    expect(screen.queryByText('当前时区: Asia/Shanghai')).toBeNull();
  });

  it('renders Scheme C Quota Compass and 4 Token Metric Cards', async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText('额度')).toBeDefined());
    expect(screen.getByText('今日用量')).toBeDefined();
    expect(screen.getByText('本周用量')).toBeDefined();
    expect(screen.getByText('本月用量')).toBeDefined();
    expect(screen.getByText('累计记录')).toBeDefined();
    expect(screen.queryByText('暂无额度')).toBeNull();
    expect(screen.queryByText(/未检测到/)).toBeNull();
  });

  it('allows in-place tab switching between Tasks, Trends, Projects, and Skills', async () => {
    render(<App />);

    // Default tab is 今日任务
    await waitFor(() => expect(screen.getAllByText('进行中').length).toBeGreaterThan(0));
    expect(screen.getAllByText('待处理').length).toBeGreaterThan(0);
    expect(screen.getAllByText('已完成').length).toBeGreaterThan(0);

    // Switch to 用量趋势
    const trendsTabBtn = screen.getByText('用量趋势');
    fireEvent.click(trendsTabBtn);
    await waitFor(() => expect(screen.getByText('趋势')).toBeDefined());

    // Switch to 项目排行
    const projectsTabBtn = screen.getByText('项目排行');
    fireEvent.click(projectsTabBtn);
    await waitFor(() => expect(screen.getByText('项目用量排行')).toBeDefined());
    expect(screen.getByText('活动概览')).toBeDefined();

    // Switch to Skill & 工具
    const skillsTabBtn = screen.getByText('Skill & 工具');
    fireEvent.click(skillsTabBtn);
    await waitFor(() => expect(screen.getByText('Skill 与工具')).toBeDefined());
  });
});

describe('Dashboard tablist accessibility (roving tabindex)', () => {
  beforeEach(() => {
    sessionStorage.clear();
    disableTauri();
  });

  it('uses roving tabindex, arrow keys, and only points aria-controls at the rendered panel', () => {
    render(<App />);
    const tasksTab = screen.getByRole('tab', { name: /今日任务/ });
    const trendsTab = screen.getByRole('tab', { name: /用量趋势/ });

    // Active tab is focusable; others are out of the tab order.
    expect(tasksTab.getAttribute('tabindex')).toBe('0');
    expect(trendsTab.getAttribute('tabindex')).toBe('-1');
    // Only the active tab has aria-controls (its panel is the one rendered).
    expect(tasksTab.getAttribute('aria-controls')).toBe('dashboard-panel-tasks');
    expect(trendsTab.getAttribute('aria-controls')).toBeNull();

    // ArrowRight moves selection + focus to the next tab.
    fireEvent.keyDown(tasksTab, { key: 'ArrowRight' });
    expect(trendsTab.getAttribute('aria-selected')).toBe('true');
    expect(trendsTab.getAttribute('tabindex')).toBe('0');
    expect(tasksTab.getAttribute('tabindex')).toBe('-1');
    expect(trendsTab.getAttribute('aria-controls')).toBe('dashboard-panel-trends');
    expect(tasksTab.getAttribute('aria-controls')).toBeNull();
  });
});

describe('App async request ordering (Tauri invoke boundary)', () => {
  beforeEach(() => {
    sessionStorage.clear();
    enableTauri();
  });

  afterEach(() => {
    disableTauri();
  });

  function flush() {
    return new Promise<void>((resolve) => {
      const { act } = require('@testing-library/react') as typeof import('@testing-library/react');
      act(() => resolve());
    });
  }

  it('initialises with the default channel and calls the snapshot command for it', async () => {
    const invoke = invokeMock;
    invoke.mockClear();
    invoke.mockImplementation(async (cmd: string, args?: any) => {
      if (cmd === 'get_settings') return { ...DEFAULT_SETTINGS, default_channel: 'antigravity' };
      if (cmd === 'get_dashboard_snapshot') return freshSnapshot(args.channel ?? 'codex', 9);
      throw new Error(`unexpected ${cmd}`);
    });

    render(<App />);
    await waitFor(() => expect(screen.getByText('Antigravity')).toBeDefined());
    expect(invoke).toHaveBeenCalledWith(
      'get_dashboard_snapshot',
      expect.objectContaining({ channel: 'antigravity', timezone: 'Asia/Shanghai' }),
    );
  });

  it('only the latest channel switch wins when responses arrive out of order', async () => {
    const invoke = invokeMock;
    invoke.mockClear();
    let snapshotCall = 0;
    const pending: Record<number, (value: DashboardSnapshot) => void> = {};
    invoke.mockImplementation(async (cmd: string, args?: any) => {
      if (cmd === 'get_settings') return DEFAULT_SETTINGS;
      if (cmd === 'get_dashboard_snapshot') {
        snapshotCall += 1;
        const call = snapshotCall;
        return new Promise<DashboardSnapshot>((resolve) => { pending[call] = resolve; });
      }
      return undefined;
    });

    const { container } = render(<App />);

    // init fires get_dashboard_snapshot (call 1 -> codex). Resolve it.
    await waitFor(() => expect(snapshotCall).toBe(1));
    const { act } = require('@testing-library/react') as typeof import('@testing-library/react');
    await act(async () => { pending[1](freshSnapshot('codex', 0)); });
    await act(async () => { await new Promise((r) => setTimeout(r, 20)); });

    // Now two rapid channel switches: Antigravity (call 2, slow) then 全部聚合 (call 3, fast).
    await act(async () => {
      fireEvent.click(screen.getByLabelText('切换到Antigravity'));
    });
    await act(async () => {
      fireEvent.click(screen.getByLabelText('切换到全部聚合'));
    });
    await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
    expect(snapshotCall).toBe(3);

    // Resolve ALL (newer) first, then ANTIGRAVITY (older) — the stale one must be dropped.
    await act(async () => { pending[3](freshSnapshot('all', 321)); });
    await act(async () => { pending[2](freshSnapshot('antigravity', 999)); });
    await flush();

    // The selected channel is 全部聚合, and the stale antigravity total never shows.
    expect(screen.getByLabelText('切换到全部聚合').getAttribute('aria-pressed')).toBe('true');
    expect(container.textContent).toContain('321');
    expect(container.textContent).not.toContain('999');
  });

  it('keeps a user channel switch even when init settings finish loading late', async () => {
    const invoke = invokeMock;
    invoke.mockClear();
    const act = (require('@testing-library/react') as typeof import('@testing-library/react')).act;
    let resolveSettings!: (s: AppSettings) => void;
    const pendingSnap: Record<number, (v: DashboardSnapshot) => void> = {};
    let snapCall = 0;
    invoke.mockImplementation(async (cmd: string, args?: any) => {
      if (cmd === 'get_settings') {
        return new Promise<AppSettings>((resolve) => { resolveSettings = resolve; });
      }
      if (cmd === 'get_dashboard_snapshot') {
        snapCall += 1;
        const call = snapCall;
        return new Promise<DashboardSnapshot>((resolve) => { pendingSnap[call] = resolve; });
      }
      return undefined;
    });

    const { container } = render(<App />);
    // init has started and is waiting on get_settings; it has NOT fetched a
    // snapshot yet (settings gate the init snapshot call).
    await waitFor(() => expect(resolveSettings).toBeDefined());
    expect(snapCall).toBe(0);

    // User quickly switches to 全部聚合 while init settings are still loading.
    await act(async () => {
      fireEvent.click(screen.getByLabelText('切换到全部聚合'));
    });
    await waitFor(() => expect(snapCall).toBe(1)); // user's switch snapshot

    // Now init's settings resolve with a *different* default channel (codex),
    // which triggers init's own snapshot fetch (call 2 -> codex).
    await act(async () => { resolveSettings({ ...DEFAULT_SETTINGS, default_channel: 'codex' }); });
    await waitFor(() => expect(snapCall).toBe(2));

    // The user's switch (all, call 1) is the newest request and must win;
    // init's later codex snapshot (call 2) belongs to a stale token and must be
    // dropped, and the default channel must not override the user's choice.
    await act(async () => { pendingSnap[1](freshSnapshot('all', 555)); });
    await act(async () => { pendingSnap[2](freshSnapshot('codex', 111)); });
    await flush();

    expect(screen.getByLabelText('切换到全部聚合').getAttribute('aria-pressed')).toBe('true');
    expect(container.textContent).toContain('555');
    expect(container.textContent).not.toContain('111');
  });
});

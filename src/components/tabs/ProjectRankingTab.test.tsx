import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { ProjectRankingTab } from './ProjectRankingTab';
import type { ProjectRankingItem } from '../../types';

vi.mock('../../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api')>();
  return {
    ...actual,
    exportData: vi.fn(async () => 'rank,name\n1,proj\n'),
  };
});

async function getApi() {
  const api = await import('../../api');
  return { exportData: api.exportData as ReturnType<typeof vi.fn> };
}

const projects: ProjectRankingItem[] = [
  {
    rank: 1,
    name: 'acme',
    path: 'C:/acme',
    tokens: { uncached_input: 1, cached_input: 0, output: 0, total: 1 },
    cost_usd: 0.01,
    sessions: 1,
    last_active_at: '2026-08-19 10:00:00',
    primary_model: 'gemini-3.1-pro',
  },
];

describe('ProjectRankingTab export robustness', () => {
  let originalCreateObjectURL: typeof URL.createObjectURL;
  let originalRevokeObjectURL: typeof URL.revokeObjectURL;

  beforeEach(async () => {
    const api = await getApi();
    api.exportData.mockClear().mockResolvedValue('rank,name\n1,proj\n');
    originalCreateObjectURL = URL.createObjectURL;
    originalRevokeObjectURL = URL.revokeObjectURL;
    URL.createObjectURL = vi.fn(() => 'blob:mock');
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  });

  afterEach(() => {
    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
    vi.restoreAllMocks();
    // Clean up an anchor that handleExport may leave mounted.
    document.querySelectorAll('a[download]').forEach((a) => a.remove());
  });

  it('mounts the download anchor into the DOM and defers revoking the URL', async () => {
    render(<ProjectRankingTab projects={projects} channel="codex" />);
    fireEvent.click(screen.getByLabelText('导出项目排行 JSON'));

    await waitFor(() => expect(screen.getByText(/已导出 JSON/)).toBeDefined());

    // The anchor is mounted (implicitly by appendChild) with the download name.
    const anchor = document.querySelector<HTMLAnchorElement>('a[download]');
    expect(anchor).not.toBeNull();
    expect(anchor?.download).toBe(`codexuu-projects-codex.json`);
    // Object URL is created, but NOT revoked synchronously — it is deferred.
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
  });

  it('reports an export failure without mounting an anchor', async () => {
    const api = await getApi();
    api.exportData.mockRejectedValueOnce(new Error('boom'));
    render(<ProjectRankingTab projects={projects} channel="codex" />);
    fireEvent.click(screen.getByLabelText('导出项目排行 CSV'));
    await waitFor(() => expect(screen.getByText(/导出失败/)).toBeDefined());
    expect(document.querySelector('a[download]')).toBeNull();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});

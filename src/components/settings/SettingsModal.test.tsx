import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { SettingsModal } from './SettingsModal';
import type { AppSettings } from '../../types';

const defaultSettings: AppSettings = {
  schema_version: 1,
  theme: 'dark',
  language: 'zh-CN',
  quota_mode: 'used',
  timezone: 'Asia/Shanghai',
  global_shortcut: 'Ctrl+U',
  always_on_top: false,
  close_to_tray: true,
  start_at_login: false,
  widget_enabled: true,
  widget_style: 'ring',
  widget_scale: 1.0,
  default_channel: 'codex',
};

// Mock the public API boundary so we can verify the save/apply flow and its
// error reporting without reaching into SettingsModal internals.
vi.mock('../../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api')>();
  return {
    ...actual,
    updateSettings: vi.fn(async (s: AppSettings) => s),
    setWidgetVisible: vi.fn(async () => undefined),
    setWidgetStyle: vi.fn(async () => undefined),
  };
});

async function getApi() {
  const api = await import('../../api');
  return {
    updateSettings: api.updateSettings as ReturnType<typeof vi.fn>,
    setWidgetVisible: api.setWidgetVisible as ReturnType<typeof vi.fn>,
    setWidgetStyle: api.setWidgetStyle as ReturnType<typeof vi.fn>,
  };
}

const baseProps = {
  isOpen: true,
  onClose: () => {},
  onSaveSettings: () => {},
  sourcesHealth: [],
  onRefreshSources: async () => {},
  isRefreshing: false,
};

function renderModal(settings: AppSettings = defaultSettings) {
  return render(<SettingsModal {...baseProps} settings={{ ...settings }} />);
}

function openWidgetTab() {
  fireEvent.click(screen.getByRole('tab', { name: /托盘与悬浮窗/ }));
}

describe('SettingsModal save & widget-apply flow', () => {
  beforeEach(async () => {
    const api = await getApi();
    api.updateSettings.mockClear().mockImplementation(async (s) => s);
    api.setWidgetVisible.mockClear().mockResolvedValue(undefined);
    api.setWidgetStyle.mockClear().mockResolvedValue(undefined);
  });

  it('persists settings once, then applies the widget window', async () => {
    const api = await getApi();
    const onSave = vi.fn();
    render(<SettingsModal {...baseProps} onSaveSettings={onSave} settings={{ ...defaultSettings }} />);
    openWidgetTab();
    // Change the widget style so the apply step actually runs.
    fireEvent.click(screen.getByText('状态胶囊 (Status Capsule)'));
    fireEvent.click(screen.getByText('保存设置'));
    await waitFor(() => expect(api.updateSettings).toHaveBeenCalledTimes(1));
    expect(api.setWidgetVisible).toHaveBeenCalledWith(defaultSettings.widget_enabled);
    expect(api.setWidgetStyle).toHaveBeenCalled();
    expect(onSave).toHaveBeenCalled();
  });

  it('does not redundantly re-apply widget style when it is unchanged', async () => {
    const api = await getApi();
    render(<SettingsModal {...baseProps} settings={{ ...defaultSettings }} />);
    fireEvent.click(screen.getByText('保存设置'));
    await waitFor(() => expect(api.updateSettings).toHaveBeenCalledTimes(1));
    // Style and scale unchanged -> no duplicate style write.
    expect(api.setWidgetStyle).not.toHaveBeenCalled();
    expect(api.setWidgetVisible).toHaveBeenCalledTimes(1);
  });

  it('reports a partial failure when only the widget apply fails', async () => {
    const api = await getApi();
    api.setWidgetStyle.mockRejectedValueOnce(new Error('widget window busy'));
    render(<SettingsModal {...baseProps} settings={{ ...defaultSettings, widget_scale: 1.0 }} />);
    openWidgetTab();
    // Change the zoom so the modal applies the widget style to the window.
    fireEvent.change(screen.getByLabelText('自定义缩放比例'), { target: { value: '2.0' } });
    fireEvent.click(screen.getByText('保存设置'));

    // Settings persistence still succeeded - the message must say so instead of
    // reporting a blanket save failure.
    await waitFor(() => {
      expect(api.updateSettings).toHaveBeenCalledTimes(1);
      expect(screen.getByRole('alert').textContent).toContain('设置已保存');
      expect(screen.getByRole('alert').textContent).toContain('悬浮窗应用失败');
    });
    expect(screen.queryByText(/保存失败/)).toBeNull();
  });

  it('reports an overall failure when the settings persistence itself fails', async () => {
    const api = await getApi();
    api.updateSettings.mockRejectedValueOnce(new Error('disk error'));
    render(<SettingsModal {...baseProps} settings={{ ...defaultSettings }} />);
    fireEvent.click(screen.getByText('保存设置'));
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('保存失败');
    });
    // No widget-apply call happens because persistence was the blocker.
    expect(api.setWidgetVisible).not.toHaveBeenCalled();
  });
});

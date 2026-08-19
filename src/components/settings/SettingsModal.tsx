import React, { useEffect, useRef, useState } from 'react';
import { AppSettings, SourceHealthStatus } from '../../types';
import {
  Settings,
  Sliders,
  Palette,
  Layout,
  Shield,
  Activity,
  Save,
  X,
  Check,
  RefreshCw,
} from 'lucide-react';
import { updateSettings, setWidgetVisible, setWidgetStyle } from '../../api';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  settings: AppSettings;
  onSaveSettings: (newSettings: AppSettings) => void;
  sourcesHealth: SourceHealthStatus[];
  onRefreshSources: () => Promise<void>;
  isRefreshing: boolean;
}

function healthLabel(status: string): string {
  switch (status) {
    case 'healthy':
      return '正常';
    case 'degraded':
      return '降级';
    case 'stale':
      return '过期';
    case 'refreshing':
      return '刷新中';
    case 'unavailable':
      return '不可用';
    default:
      return '未知';
  }
}

function healthClass(status: string): string {
  switch (status) {
    case 'healthy':
      return 'bg-[color-mix(in_srgb,var(--success)_12%,transparent)] text-[var(--success)] border-[color-mix(in_srgb,var(--success)_28%,transparent)]';
    case 'degraded':
      return 'bg-[color-mix(in_srgb,var(--warning)_12%,transparent)] text-[var(--warning)] border-[color-mix(in_srgb,var(--warning)_28%,transparent)]';
    case 'stale':
      return 'bg-[color-mix(in_srgb,var(--token-output)_12%,transparent)] text-[var(--token-output)] border-[color-mix(in_srgb,var(--token-output)_28%,transparent)]';
    case 'refreshing':
      return 'bg-[color-mix(in_srgb,var(--info)_12%,transparent)] text-[var(--info)] border-[color-mix(in_srgb,var(--info)_28%,transparent)]';
    case 'unavailable':
      return 'bg-[color-mix(in_srgb,var(--danger)_12%,transparent)] text-[var(--danger)] border-[color-mix(in_srgb,var(--danger)_28%,transparent)]';
    default:
      return 'bg-[var(--bg-subtle)] text-[var(--text-secondary)] border-[var(--border-default)]';
  }
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  settings,
  onSaveSettings,
  sourcesHealth,
  onRefreshSources,
  isRefreshing,
}) => {
  const [activeTab, setActiveTab] = useState<'general' | 'appearance' | 'widget' | 'privacy' | 'diagnostics'>('general');
  const [draft, setDraft] = useState<AppSettings>({ ...settings });
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const saveTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (isOpen) {
      setDraft({ ...settings });
      setSaveSuccess(false);
      setSaveError(null);
    }
  }, [isOpen, settings]);

  useEffect(() => {
    if (!isOpen) return;

    const previousActiveElement = document.activeElement as HTMLElement | null;
    const animationFrame = window.requestAnimationFrame(() => closeButtonRef.current?.focus());

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }

      if (event.key !== 'Tab' || !dialogRef.current) return;
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      window.cancelAnimationFrame(animationFrame);
      document.removeEventListener('keydown', handleKeyDown);
      previousActiveElement?.focus();
    };
  }, [isOpen, onClose]);

  useEffect(() => () => {
    if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current);
  }, []);

  if (!isOpen) return null;

  const handleSave = async () => {
    if (isSaving) return;
    setSaveError(null);
    setIsSaving(true);
    let saved: AppSettings;
    try {
      saved = await updateSettings({ ...draft, language: 'zh-CN' });
    } catch (err) {
      setSaveError(`保存失败：${err instanceof Error ? err.message : String(err)}`);
      setIsSaving(false);
      return;
    }
    onSaveSettings(saved);

    // Apply the widget window AFTER settings are already persisted. A failure
    // here is a partial failure (the app settings are saved) and must not be
    // reported as an overall save failure. Widget style/scale are only
    // re-applied when they actually changed, to avoid redundant writes and the
    // partial-transaction confusion of writing them twice.
    let widgetApplied = true;
    try {
      await setWidgetVisible(draft.widget_enabled);
      if (
        draft.widget_style !== settings.widget_style
        || draft.widget_scale !== settings.widget_scale
      ) {
        await setWidgetStyle(draft.widget_style, draft.widget_scale);
      }
    } catch (err) {
      widgetApplied = false;
      setSaveError(`设置已保存，但悬浮窗应用失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsSaving(false);
    }

    if (widgetApplied) {
      setSaveSuccess(true);
      saveTimerRef.current = window.setTimeout(() => {
        setSaveSuccess(false);
        onClose();
      }, 800);
    }
  };

  const tabs: Array<{
    id: 'general' | 'appearance' | 'widget' | 'privacy' | 'diagnostics';
    label: string;
    icon: typeof Sliders;
  }> = [
    { id: 'general', label: '常规设置', icon: Sliders },
    { id: 'appearance', label: '外观与口径', icon: Palette },
    { id: 'widget', label: '托盘与悬浮窗', icon: Layout },
    { id: 'privacy', label: '隐私与维护', icon: Shield },
    { id: 'diagnostics', label: '数据源诊断', icon: Activity },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-dialog-title"
        tabIndex={-1}
        className="bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-2xl w-full max-w-2xl min-h-[420px] h-[min(620px,calc(100dvh-2rem))] shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200"
      >
        {/* Header */}
        <div className="h-12 border-b border-[var(--border-default)] px-4 flex items-center justify-between shrink-0 bg-[var(--bg-card)]">
          <div className="flex items-center gap-2">
            <Settings aria-hidden="true" className="w-4 h-4 text-[var(--accent-brand)]" />
            <span id="settings-dialog-title" className="font-bold text-sm text-[var(--text-primary)]">设置中心</span>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label="关闭设置"
            className="p-1 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition"
          >
            <X aria-hidden="true" className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body: West Tab Navigation + Main Panel */}
        <div className="flex-1 flex overflow-hidden">
          {/* West Sidebar Tabs */}
          <div role="tablist" aria-label="设置分类" className="w-40 border-r border-[var(--border-default)] bg-[var(--bg-card)] p-2 space-y-1 shrink-0">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  aria-controls={`settings-panel-${tab.id}`}
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-medium transition ${
                    isActive
                      ? 'ui-selected'
                      : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)]'
                  }`}
                >
                  <Icon aria-hidden="true" className="w-4 h-4" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>

          {/* Tab Content Panel */}
          <div id={`settings-panel-${activeTab}`} role="tabpanel" aria-label={tabs.find((tab) => tab.id === activeTab)?.label} className="flex-1 p-5 overflow-y-auto bg-[var(--bg-canvas)] space-y-4 text-xs">
            {activeTab === 'general' && (
              <div className="space-y-4">
                <div>
                  <span className="block text-[var(--text-secondary)] mb-1 font-medium">界面语言</span>
                  <p className="w-full bg-[var(--bg-card)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[var(--text-primary)]">
                    简体中文
                  </p>
                  <span className="text-[10px] text-[var(--text-muted)] mt-1 block">
                    目前仅支持简体中文，English 选项尚未实现，因此不再提供无效切换。
                  </span>
                </div>

                <div>
                  <label htmlFor="settings-default-channel" className="block text-[var(--text-secondary)] mb-1 font-medium">启动默认渠道</label>
                  <select
                    id="settings-default-channel"
                    value={draft.default_channel}
                    onChange={(e) => setDraft({
                      ...draft,
                      default_channel: e.target.value as AppSettings['default_channel'],
                    })}
                    className="w-full bg-[var(--bg-card)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[var(--text-primary)] focus:border-[var(--accent-brand)] focus:ring-2 focus:ring-[var(--accent-brand)]/30"
                  >
                    <option value="codex">Codex 官方</option>
                    <option value="antigravity">Antigravity</option>
                    <option value="all">全部聚合</option>
                  </select>
                </div>

                <div>
                  <label htmlFor="settings-timezone" className="block text-[var(--text-secondary)] mb-1 font-medium">统计时区</label>
                  <select
                    id="settings-timezone"
                    value={draft.timezone}
                    onChange={(e) => setDraft({ ...draft, timezone: e.target.value })}
                    className="w-full bg-[var(--bg-card)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[var(--text-primary)] focus:border-[var(--accent-brand)] focus:ring-2 focus:ring-[var(--accent-brand)]/30"
                  >
                    <option value="Asia/Shanghai">Asia/Shanghai (北京时间, UTC+8)</option>
                    <option value="UTC">UTC (世界标准时间)</option>
                    <option value="America/New_York">America/New_York (美东时间)</option>
                    <option value="America/Los_Angeles">America/Los_Angeles (美西时间)</option>
                    <option value="Europe/London">Europe/London (伦敦时间)</option>
                    <option value="Asia/Tokyo">Asia/Tokyo (东京时间)</option>
                  </select>
                </div>

                <div>
                  <label htmlFor="settings-shortcut" className="block text-[var(--text-secondary)] mb-1 font-medium">全局快捷键</label>
                  <input
                    id="settings-shortcut"
                    type="text"
                    value={draft.global_shortcut}
                    onChange={(e) => setDraft({ ...draft, global_shortcut: e.target.value })}
                    className="w-full bg-[var(--bg-card)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[var(--text-primary)] font-mono focus:border-[var(--accent-brand)] focus:ring-2 focus:ring-[var(--accent-brand)]/30"
                    placeholder="Ctrl+U"
                  />
                  <span className="text-[10px] text-[var(--text-muted)] mt-1 block">
                    默认 Ctrl+U 用于一键唤回或最小化主窗口
                  </span>
                </div>

                <div className="pt-2 border-t border-[var(--border-default)] space-y-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      id="settings-close-to-tray"
                      type="checkbox"
                      checked={draft.close_to_tray}
                      onChange={(e) => setDraft({ ...draft, close_to_tray: e.target.checked })}
                      className="rounded border-[var(--border-default)] text-[var(--accent-brand)] focus:ring-2 focus:ring-[var(--accent-brand)]/40"
                    />
                    <span className="text-[var(--text-primary)]">关闭主窗口时最小化到系统托盘</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      id="settings-start-at-login"
                      type="checkbox"
                      checked={draft.start_at_login}
                      onChange={(e) => setDraft({ ...draft, start_at_login: e.target.checked })}
                      className="rounded border-[var(--border-default)] text-[var(--accent-brand)] focus:ring-2 focus:ring-[var(--accent-brand)]/40"
                    />
                    <span className="text-[var(--text-primary)]">登录 Windows 时自动启动</span>
                  </label>
                </div>
              </div>
            )}

            {activeTab === 'appearance' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-[var(--text-secondary)] mb-1 font-medium">色彩主题</label>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { id: 'dark' as const, label: '深色暗黑' },
                      { id: 'light' as const, label: '明亮浅色' },
                      { id: 'system' as const, label: '跟随系统' },
                    ].map((th) => (
                      <button
                        key={th.id}
                        type="button"
                        aria-pressed={draft.theme === th.id}
                        onClick={() => setDraft({ ...draft, theme: th.id })}
                        className={`p-2.5 rounded-xl border text-center font-medium transition ${
                          draft.theme === th.id
                            ? 'ui-selected'
                            : 'bg-[var(--bg-card)] border-[var(--border-default)] text-[var(--text-secondary)]'
                        }`}
                      >
                        {th.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="block text-[var(--text-secondary)] mb-1 font-medium">额度罗盘显示口径</label>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      aria-pressed={draft.quota_mode === 'used'}
                      onClick={() => setDraft({ ...draft, quota_mode: 'used' })}
                      className={`p-2.5 rounded-xl border text-center font-medium transition ${
                        draft.quota_mode === 'used'
                          ? 'ui-selected'
                          : 'bg-[var(--bg-card)] border-[var(--border-default)] text-[var(--text-secondary)]'
                      }`}
                    >
                      已用口径 (从底向左增长)
                    </button>
                    <button
                      type="button"
                      aria-pressed={draft.quota_mode === 'remaining'}
                      onClick={() => setDraft({ ...draft, quota_mode: 'remaining' })}
                      className={`p-2.5 rounded-xl border text-center font-medium transition ${
                        draft.quota_mode === 'remaining'
                          ? 'ui-selected'
                          : 'bg-[var(--bg-card)] border-[var(--border-default)] text-[var(--text-secondary)]'
                      }`}
                    >
                      剩余口径 (从底向右增长)
                    </button>
                  </div>
                </div>

                <div className="pt-2 border-t border-[var(--border-default)]">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      id="settings-always-on-top"
                      type="checkbox"
                      checked={draft.always_on_top}
                      onChange={(e) => setDraft({ ...draft, always_on_top: e.target.checked })}
                      className="rounded border-[var(--border-default)] text-[var(--accent-brand)] focus:ring-2 focus:ring-[var(--accent-brand)]/40"
                    />
                    <span className="text-[var(--text-primary)]">主窗口始终置顶</span>
                  </label>
                </div>
              </div>
            )}

            {activeTab === 'widget' && (
              <div className="space-y-4">
                <div>
                  <label className="flex items-center gap-2 cursor-pointer mb-3">
                    <input
                      id="settings-widget-enabled"
                      type="checkbox"
                      checked={draft.widget_enabled}
                      onChange={(e) => setDraft({ ...draft, widget_enabled: e.target.checked })}
                      className="rounded border-[var(--border-default)] text-[var(--accent-brand)] focus:ring-2 focus:ring-[var(--accent-brand)]/40"
                    />
                    <span className="text-[var(--text-primary)] font-bold">启用桌面状态悬浮窗</span>
                  </label>
                </div>

                <div>
                  <label className="block text-[var(--text-secondary)] mb-1 font-medium">悬浮窗视觉形态</label>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { id: 'ring' as const, label: '极简圆环 (Minimal Ring)' },
                      { id: 'capsule' as const, label: '状态胶囊 (Status Capsule)' },
                      { id: 'tracks' as const, label: '双轨卡片 (Dual Track)' },
                      { id: 'disc' as const, label: '信息圆盘 (Info Disc)' },
                      { id: 'gauge' as const, label: '双环仪表 (Gauge Meter)' },
                    ].map((st) => (
                      <button
                        key={st.id}
                        type="button"
                        aria-pressed={draft.widget_style === st.id}
                        onClick={() => setDraft({ ...draft, widget_style: st.id })}
                        className={`p-2 rounded-xl border text-left font-medium text-xs transition ${
                          draft.widget_style === st.id
                            ? 'ui-selected'
                            : 'bg-[var(--bg-card)] border-[var(--border-default)] text-[var(--text-secondary)]'
                        }`}
                      >
                        {st.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label htmlFor="settings-widget-scale" className="text-[var(--text-secondary)] font-medium">自定义缩放比例</label>
                    <span className="font-mono text-[var(--accent-brand)] font-bold">{Math.round(draft.widget_scale * 100)}%</span>
                  </div>
                  <input
                    id="settings-widget-scale"
                    type="range"
                    min="0.2"
                    max="3.0"
                    step="0.05"
                    value={draft.widget_scale}
                    aria-valuetext={`${Math.round(draft.widget_scale * 100)}%`}
                    onChange={(e) => setDraft({ ...draft, widget_scale: parseFloat(e.target.value) })}
                    className="w-full cursor-pointer accent-[var(--accent-brand)]"
                  />
                  <div className="flex justify-between text-[10px] text-[var(--text-muted)] mt-1">
                    <span>20% (超小)</span>
                    <span>100% (标准)</span>
                    <span>300% (超大)</span>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'privacy' && (
              <div className="space-y-3">
                <div className="p-3 rounded-xl bg-[var(--bg-card)] border border-[var(--border-default)]">
                  <h5 className="font-bold text-[var(--text-primary)] mb-1">本地优先与隐私保障</h5>
                  <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
                    CodexUU 为 100% 纯本地运行架构，绝不上报代码正文、Transcript 提示词、工具入参或任何敏感凭证。所有统计计算均在 Rust 引擎内完成。
                  </p>
                </div>

                <div className="p-3 rounded-xl bg-[var(--bg-card)] border border-[var(--border-default)]">
                  <h5 className="font-bold text-[var(--text-primary)] mb-1">数据维护</h5>
                  <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
                    当前版本会按本地数据源指纹自动复用快照；数据源暂时不可用时保留上次成功结果，并持续归档每日摘要，无需手动重建索引。
                  </p>
                </div>
              </div>
            )}

            {activeTab === 'diagnostics' && (
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3 mb-2">
                  <h5 className="font-bold text-[var(--text-primary)]">底层数据源健康诊断</h5>
                  <button
                    type="button"
                    onClick={() => void onRefreshSources()}
                    disabled={isRefreshing}
                    aria-label="重新扫描数据源"
                    aria-busy={isRefreshing}
                    className="flex items-center gap-1 px-2 py-1 rounded-lg bg-[var(--bg-card)] border border-[var(--border-default)] text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[color-mix(in_srgb,var(--accent-brand)_40%,transparent)] disabled:opacity-50"
                  >
                    <RefreshCw aria-hidden="true" className={`w-3 h-3 ${isRefreshing ? 'animate-spin' : ''}`} />
                    重新扫描
                  </button>
                </div>
                {sourcesHealth.map((src) => (
                  <div
                    key={src.id}
                    className="p-2.5 rounded-xl bg-[var(--bg-card)] border border-[var(--border-default)]"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="font-bold text-[var(--text-primary)]">{src.name}</div>
                        <div className="text-[10px] text-[var(--text-muted)] mt-0.5">{src.message}</div>
                      </div>
                      <span className={`shrink-0 text-[10px] px-2 py-0.5 rounded-full border font-medium ${healthClass(src.status)}`}>
                        {healthLabel(src.status)}
                      </span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-[var(--text-muted)]">
                      <span>文件 {src.scanned_files ?? 0}</span>
                      <span>会话 {src.parsed_sessions ?? 0}</span>
                      {src.source_schema && <span>格式 {src.source_schema}</span>}
                      {src.error_code && <span className="text-[var(--warning)]">错误 {src.error_code}</span>}
                      {src.last_success_at && <span>最近成功 {src.last_success_at}</span>}
                      {src.last_attempt_at && <span>最近尝试 {src.last_attempt_at}</span>}
                    </div>
                    {(src.locations ?? []).length > 0 && (
                      <div className="mt-1 text-[10px] text-[var(--text-muted)] break-all">
                        路径：{src.locations.join(' · ')}
                      </div>
                    )}
                    {(src.capabilities ?? []).length > 0 && (
                      <div className="mt-1 text-[10px] text-[var(--text-muted)]">
                        能力：{src.capabilities.join(' · ')}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Footer Fixed Action Bar */}
        <div className="h-14 border-t border-[var(--border-default)] px-4 flex items-center justify-between shrink-0 bg-[var(--bg-card)]">
          <span role={saveError ? 'alert' : 'status'} aria-live="polite" className="text-[11px] text-[var(--text-muted)]">
            {saveError || '设置将在点击“保存设置”后即时持久化并生效'}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-1.5 rounded-xl border border-[var(--border-default)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={isSaving}
              aria-busy={isSaving}
              className="px-4 py-1.5 rounded-xl bg-[var(--accent-brand)] hover:opacity-90 text-[var(--on-accent)] font-bold flex items-center gap-1.5 shadow-sm transition disabled:opacity-60 disabled:cursor-wait"
            >
              {saveSuccess ? <Check aria-hidden="true" className="w-4 h-4" /> : <Save aria-hidden="true" className="w-4 h-4" />}
              <span>{isSaving ? '保存中…' : saveSuccess ? '已保存！' : '保存设置'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

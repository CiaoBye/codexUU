import React, { useEffect, useState } from 'react';
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
} from 'lucide-react';
import { updateSettings, setWidgetVisible, setWidgetStyle } from '../../api';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  settings: AppSettings;
  onSaveSettings: (newSettings: AppSettings) => void;
  sourcesHealth: SourceHealthStatus[];
}

function healthLabel(status: string): string {
  switch (status) {
    case 'healthy':
      return '正常';
    case 'degraded':
      return '降级';
    case 'stale':
      return '过期';
    case 'unavailable':
      return '不可用';
    default:
      return '未知';
  }
}

function healthClass(status: string): string {
  switch (status) {
    case 'healthy':
      return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
    case 'degraded':
      return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
    case 'stale':
      return 'bg-orange-500/10 text-orange-400 border-orange-500/20';
    case 'unavailable':
      return 'bg-red-500/10 text-red-400 border-red-500/20';
    default:
      return 'bg-slate-500/10 text-slate-400 border-slate-500/20';
  }
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  settings,
  onSaveSettings,
  sourcesHealth,
}) => {
  const [activeTab, setActiveTab] = useState<'general' | 'appearance' | 'widget' | 'privacy' | 'diagnostics'>('general');
  const [draft, setDraft] = useState<AppSettings>({ ...settings });
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setDraft({ ...settings });
      setSaveSuccess(false);
      setSaveError(null);
    }
  }, [isOpen, settings]);

  if (!isOpen) return null;

  const handleSave = async () => {
    setSaveError(null);
    try {
      const saved = await updateSettings(draft);
      onSaveSettings(saved);

      // Apply widget settings
      await setWidgetVisible(draft.widget_enabled);
      await setWidgetStyle(draft.widget_style, draft.widget_scale);

      setSaveSuccess(true);
      setTimeout(() => {
        setSaveSuccess(false);
        onClose();
      }, 800);
    } catch (err) {
      setSaveError(`保存失败：${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const tabs = [
    { id: 'general', label: '常规设置', icon: Sliders },
    { id: 'appearance', label: '外观与口径', icon: Palette },
    { id: 'widget', label: '托盘与悬浮窗', icon: Layout },
    { id: 'privacy', label: '隐私与维护', icon: Shield },
    { id: 'diagnostics', label: '数据源诊断', icon: Activity },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm select-none p-4">
      <div className="bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-2xl w-full max-w-2xl h-[520px] shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="h-12 border-b border-[var(--border-default)] px-4 flex items-center justify-between shrink-0 bg-[var(--bg-card)]">
          <div className="flex items-center gap-2">
            <Settings className="w-4 h-4 text-teal-400" />
            <span className="font-bold text-sm text-[var(--text-primary)]">设置中心</span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body: West Tab Navigation + Main Panel */}
        <div className="flex-1 flex overflow-hidden">
          {/* West Sidebar Tabs */}
          <div className="w-40 border-r border-[var(--border-default)] bg-[var(--bg-card)] p-2 space-y-1 shrink-0">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  className={`w-full flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-medium transition ${
                    isActive
                      ? 'bg-teal-500/15 text-teal-300 border border-teal-500/30'
                      : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)]'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>

          {/* Tab Content Panel */}
          <div className="flex-1 p-5 overflow-y-auto bg-[var(--bg-canvas)] space-y-4 text-xs">
            {activeTab === 'general' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-[var(--text-secondary)] mb-1 font-medium">界面语言</label>
                  <select
                    value={draft.language}
                    onChange={(e) => setDraft({ ...draft, language: e.target.value as any })}
                    className="w-full bg-[var(--bg-card)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[var(--text-primary)] focus:outline-none focus:border-teal-500"
                  >
                    <option value="zh-CN">简体中文 (Simplified Chinese)</option>
                    <option value="en">English</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[var(--text-secondary)] mb-1 font-medium">统计时区</label>
                  <select
                    value={draft.timezone}
                    onChange={(e) => setDraft({ ...draft, timezone: e.target.value })}
                    className="w-full bg-[var(--bg-card)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[var(--text-primary)] focus:outline-none focus:border-teal-500"
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
                  <label className="block text-[var(--text-secondary)] mb-1 font-medium">全局快捷键</label>
                  <input
                    type="text"
                    value={draft.global_shortcut}
                    onChange={(e) => setDraft({ ...draft, global_shortcut: e.target.value })}
                    className="w-full bg-[var(--bg-card)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[var(--text-primary)] font-mono focus:outline-none focus:border-teal-500"
                    placeholder="Ctrl+U"
                  />
                  <span className="text-[10px] text-[var(--text-muted)] mt-1 block">
                    默认 Ctrl+U 用于一键唤回或最小化主窗口
                  </span>
                </div>

                <div className="pt-2 border-t border-[var(--border-default)] space-y-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={draft.close_to_tray}
                      onChange={(e) => setDraft({ ...draft, close_to_tray: e.target.checked })}
                      className="rounded border-[var(--border-default)] text-teal-500 focus:ring-0"
                    />
                    <span className="text-[var(--text-primary)]">关闭主窗口时最小化到系统托盘</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={draft.start_at_login}
                      onChange={(e) => setDraft({ ...draft, start_at_login: e.target.checked })}
                      className="rounded border-[var(--border-default)] text-teal-500 focus:ring-0"
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
                      { id: 'dark', label: '深色暗黑' },
                      { id: 'light', label: '明亮浅色' },
                      { id: 'system', label: '跟随系统' },
                    ].map((th) => (
                      <button
                        key={th.id}
                        type="button"
                        onClick={() => setDraft({ ...draft, theme: th.id as any })}
                        className={`p-2.5 rounded-xl border text-center font-medium transition ${
                          draft.theme === th.id
                            ? 'bg-teal-500/20 text-teal-300 border-teal-500/40'
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
                      onClick={() => setDraft({ ...draft, quota_mode: 'used' })}
                      className={`p-2.5 rounded-xl border text-center font-medium transition ${
                        draft.quota_mode === 'used'
                          ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40'
                          : 'bg-[var(--bg-card)] border-[var(--border-default)] text-[var(--text-secondary)]'
                      }`}
                    >
                      已用口径 (从底向左增长)
                    </button>
                    <button
                      type="button"
                      onClick={() => setDraft({ ...draft, quota_mode: 'remaining' })}
                      className={`p-2.5 rounded-xl border text-center font-medium transition ${
                        draft.quota_mode === 'remaining'
                          ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40'
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
                      type="checkbox"
                      checked={draft.always_on_top}
                      onChange={(e) => setDraft({ ...draft, always_on_top: e.target.checked })}
                      className="rounded border-[var(--border-default)] text-teal-500 focus:ring-0"
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
                      type="checkbox"
                      checked={draft.widget_enabled}
                      onChange={(e) => setDraft({ ...draft, widget_enabled: e.target.checked })}
                      className="rounded border-[var(--border-default)] text-teal-500 focus:ring-0"
                    />
                    <span className="text-[var(--text-primary)] font-bold">启用桌面状态悬浮窗</span>
                  </label>
                </div>

                <div>
                  <label className="block text-[var(--text-secondary)] mb-1 font-medium">悬浮窗视觉形态</label>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { id: 'ring', label: '极简圆环 (Minimal Ring)' },
                      { id: 'capsule', label: '状态胶囊 (Status Capsule)' },
                      { id: 'tracks', label: '双轨卡片 (Dual Track)' },
                      { id: 'disc', label: '信息圆盘 (Info Disc)' },
                      { id: 'gauge', label: '双环仪表 (Gauge Meter)' },
                    ].map((st) => (
                      <button
                        key={st.id}
                        type="button"
                        onClick={() => setDraft({ ...draft, widget_style: st.id as any })}
                        className={`p-2 rounded-xl border text-left font-medium text-xs transition ${
                          draft.widget_style === st.id
                            ? 'bg-teal-500/20 text-teal-300 border-teal-500/40'
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
                    <label className="text-[var(--text-secondary)] font-medium">自定义缩放比例</label>
                    <span className="font-mono text-teal-400 font-bold">{Math.round(draft.widget_scale * 100)}%</span>
                  </div>
                  <input
                    type="range"
                    min="0.2"
                    max="3.0"
                    step="0.05"
                    value={draft.widget_scale}
                    onChange={(e) => setDraft({ ...draft, widget_scale: parseFloat(e.target.value) })}
                    className="w-full accent-teal-500 cursor-pointer"
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
                    当前版本会自动扫描本机 Codex 与 Antigravity 本地数据，无需手动重建索引。
                  </p>
                </div>
              </div>
            )}

            {activeTab === 'diagnostics' && (
              <div className="space-y-2">
                <h5 className="font-bold text-[var(--text-primary)] mb-2">底层数据源健康诊断</h5>
                {sourcesHealth.map((src) => (
                  <div
                    key={src.id}
                    className="p-2.5 rounded-xl bg-[var(--bg-card)] border border-[var(--border-default)] flex items-center justify-between"
                  >
                    <div>
                      <div className="font-bold text-[var(--text-primary)]">{src.name}</div>
                      <div className="text-[10px] text-[var(--text-muted)] mt-0.5">{src.message}</div>
                    </div>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${healthClass(src.status)}`}>
                      {healthLabel(src.status)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Footer Fixed Action Bar */}
        <div className="h-14 border-t border-[var(--border-default)] px-4 flex items-center justify-between shrink-0 bg-[var(--bg-card)]">
          <span className="text-[11px] text-[var(--text-muted)]">
            {saveError || '设置将在点击“保存设置”后即时持久化并生效'}
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-1.5 rounded-xl border border-[var(--border-default)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition"
            >
              取消
            </button>
            <button
              onClick={handleSave}
              className="px-4 py-1.5 rounded-xl bg-teal-500 hover:bg-teal-600 text-slate-950 font-bold flex items-center gap-1.5 shadow-sm transition"
            >
              {saveSuccess ? <Check className="w-4 h-4" /> : <Save className="w-4 h-4" />}
              <span>{saveSuccess ? '已保存！' : '保存设置'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

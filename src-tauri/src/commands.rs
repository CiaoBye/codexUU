use crate::engine::aggregator::Aggregator;
use crate::models::DashboardSnapshot;
use crate::storage::settings::{AppSettings, SettingsStorage};
use tauri::{AppHandle, Manager};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutEvent, ShortcutState};

pub fn register_global_shortcut(app: &AppHandle, shortcut: &str) -> Result<(), String> {
    let shortcut = shortcut.trim();
    if shortcut.is_empty() {
        return Ok(());
    }
    app.global_shortcut()
        .on_shortcut(shortcut, |_app, _shortcut, event: ShortcutEvent| {
            if event.state() != ShortcutState::Pressed {
                return;
            }
            if let Some(window) = _app.get_webview_window("main") {
                let visible = window.is_visible().unwrap_or(false);
                let focused = window.is_focused().unwrap_or(false);
                if visible && focused {
                    let _ = window.hide();
                } else {
                    let _ = window.show();
                    let _ = window.unminimize();
                    let _ = window.set_focus();
                }
            }
        })
        .map_err(|error| format!("注册全局快捷键失败：{error}"))
}

pub fn unregister_global_shortcut(app: &AppHandle, shortcut: &str) {
    if !shortcut.trim().is_empty() {
        let _ = app.global_shortcut().unregister(shortcut);
    }
}

#[cfg(windows)]
pub fn apply_start_at_login(enabled: bool) -> Result<(), String> {
    use std::process::Command;
    let key = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run";
    let result = if enabled {
        let executable =
            std::env::current_exe().map_err(|error| format!("获取程序路径失败：{error}"))?;
        Command::new("reg.exe")
            .args([
                "ADD",
                key,
                "/v",
                "CodexUU",
                "/t",
                "REG_SZ",
                "/d",
                &format!("\"{}\"", executable.display()),
                "/f",
            ])
            .status()
    } else {
        Command::new("reg.exe")
            .args(["DELETE", key, "/v", "CodexUU", "/f"])
            .status()
    };
    match result {
        Ok(status) if status.success() || !enabled => Ok(()),
        Ok(status) => Err(format!("设置 Windows 登录启动失败，退出码：{status}")),
        Err(error) => Err(format!("执行 Windows 登录启动设置失败：{error}")),
    }
}

#[cfg(not(windows))]
pub fn apply_start_at_login(_enabled: bool) -> Result<(), String> {
    Ok(())
}

#[tauri::command]
pub fn get_dashboard_snapshot(
    channel: String,
    timezone: Option<String>,
) -> Result<DashboardSnapshot, String> {
    let tz = timezone.unwrap_or_else(|| SettingsStorage::load().timezone);
    Ok(Aggregator::build_snapshot(&channel, Some(tz)))
}

#[tauri::command]
pub fn get_settings() -> Result<AppSettings, String> {
    Ok(SettingsStorage::load())
}

#[tauri::command]
pub fn save_settings(app: AppHandle, settings: AppSettings) -> Result<AppSettings, String> {
    let previous = SettingsStorage::load();
    if previous.global_shortcut != settings.global_shortcut {
        unregister_global_shortcut(&app, &previous.global_shortcut);
        if let Err(error) = register_global_shortcut(&app, &settings.global_shortcut) {
            let _ = register_global_shortcut(&app, &previous.global_shortcut);
            return Err(error);
        }
    }
    if let Err(error) = apply_start_at_login(settings.start_at_login) {
        if previous.global_shortcut != settings.global_shortcut {
            unregister_global_shortcut(&app, &settings.global_shortcut);
            let _ = register_global_shortcut(&app, &previous.global_shortcut);
        }
        return Err(error);
    }
    SettingsStorage::save(&settings)?;
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.set_always_on_top(settings.always_on_top);
    }
    Ok(settings)
}

#[tauri::command]
pub fn refresh_data(scope: String) -> Result<DashboardSnapshot, String> {
    let tz = SettingsStorage::load().timezone;
    Ok(Aggregator::build_snapshot(&scope, Some(tz)))
}

#[tauri::command]
pub fn export_data(format: String, channel: String) -> Result<String, String> {
    let tz = SettingsStorage::load().timezone;
    let snapshot = Aggregator::build_snapshot(&channel, Some(tz));
    match format.as_str() {
        "json" => serde_json::to_string_pretty(&snapshot).map_err(|e| e.to_string()),
        "csv" => {
            let mut csv = String::from("rank,name,tokens_total,tokens_uncached,tokens_cached,tokens_output,cost_usd,sessions,last_active,model\n");
            for p in &snapshot.projects {
                csv.push_str(&format!(
                    "{},{},{},{},{},{},{:.4},{},{},{}\n",
                    p.rank,
                    csv_escape(&p.name),
                    p.tokens.total,
                    p.tokens.uncached_input,
                    p.tokens.cached_input,
                    p.tokens.output,
                    p.cost_usd,
                    p.sessions,
                    csv_escape(&p.last_active_at),
                    csv_escape(&p.primary_model),
                ));
            }
            Ok(csv)
        }
        "markdown" => {
            let mut md = format!("# Project Rankings · {}\n\n| Rank | Project | Total Tokens | Cost (USD) | Primary Model |\n|---|---|---|---|---|\n", channel);
            for p in &snapshot.projects {
                md.push_str(&format!(
                    "| {} | {} | {} | ${:.4} | {} |\n",
                    p.rank,
                    markdown_escape(&p.name),
                    p.tokens.total,
                    p.cost_usd,
                    markdown_escape(&p.primary_model)
                ));
            }
            Ok(md)
        }
        _ => Err(format!("Unsupported export format: {}", format)),
    }
}

fn csv_escape(value: &str) -> String {
    format!("\"{}\"", value.replace('"', "\"\""))
}

fn markdown_escape(value: &str) -> String {
    value.replace('|', "\\|").replace('\n', " ")
}

#[tauri::command]
pub fn toggle_desktop_widget(app: AppHandle, visible: bool) -> Result<(), String> {
    let mut settings = SettingsStorage::load();
    settings.widget_enabled = visible;
    SettingsStorage::save(&settings)?;

    if let Some(window) = app.get_webview_window("widget") {
        if visible {
            let _ = window.show();
            let _ = window.unminimize();
        } else {
            let _ = window.hide();
        }
    }
    Ok(())
}

#[tauri::command]
pub fn set_widget_style(_app: AppHandle, style: String, scale: f64) -> Result<(), String> {
    if !matches!(
        style.as_str(),
        "ring" | "capsule" | "tracks" | "disc" | "gauge"
    ) {
        return Err(format!("不支持的悬浮窗样式：{style}"));
    }
    if !scale.is_finite() || !(0.2..=3.0).contains(&scale) {
        return Err("悬浮窗缩放比例必须在 0.2 到 3.0 之间".to_string());
    }
    let mut s = SettingsStorage::load();
    s.widget_style = style;
    s.widget_scale = scale;
    SettingsStorage::save(&s)
}

#[tauri::command]
pub fn show_main_window(app: AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
    Ok(())
}

#[tauri::command]
pub fn minimize_main_window(app: AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.minimize();
    }
    Ok(())
}

#[tauri::command]
pub fn close_main_window(app: AppHandle) -> Result<(), String> {
    let settings = SettingsStorage::load();
    if let Some(window) = app.get_webview_window("main") {
        if settings.close_to_tray {
            let _ = window.hide();
        } else {
            let _ = window.close();
        }
    }
    Ok(())
}

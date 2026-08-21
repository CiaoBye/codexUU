use crate::engine::aggregator::Aggregator;
use crate::models::DashboardSnapshot;
use crate::storage::settings::{AppSettings, SettingsStorage};
use tauri::{AppHandle, LogicalSize, Manager, WebviewWindow};
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
fn delete_already_missing(stderr: &str) -> bool {
    let lower = stderr.to_ascii_lowercase();
    lower.contains("unable to find")
        || lower.contains("does not exist")
        || lower.contains("does not have a value")
        || lower.contains("找不到")
        || lower.contains("不存在")
}

#[cfg(windows)]
fn sanitized_process_detail(stderr: &[u8]) -> Option<String> {
    let text = std::str::from_utf8(stderr).ok()?.trim();
    if text.is_empty() || text.contains('\u{fffd}') {
        return None;
    }
    Some(text.to_string())
}

#[cfg(windows)]
fn startup_failure_message(
    action: &str,
    status: std::process::ExitStatus,
    stderr: &[u8],
) -> String {
    let code = status
        .code()
        .map(|value| value.to_string())
        .unwrap_or_else(|| "未知".to_string());
    let detail = sanitized_process_detail(stderr)
        .map(|value| format!("：{value}"))
        .unwrap_or_else(|| "。请确认当前用户有权限后重试".to_string());
    format!("{action} Windows 登录启动失败（退出码 {code}）{detail}")
}

#[cfg(windows)]
pub fn apply_start_at_login(enabled: bool) -> Result<(), String> {
    use std::process::Command;
    let key = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run";
    if enabled {
        let executable =
            std::env::current_exe().map_err(|error| format!("获取程序路径失败：{error}"))?;
        let output = Command::new("reg.exe")
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
            .output()
            .map_err(|error| format!("执行 Windows 登录启动设置失败：{error}"))?;
        if output.status.success() {
            return Ok(());
        }
        Err(startup_failure_message(
            "设置",
            output.status,
            &output.stderr,
        ))
    } else {
        let output = Command::new("reg.exe")
            .args(["DELETE", key, "/v", "CodexUU", "/f"])
            .output()
            .map_err(|error| format!("执行 Windows 登录启动设置失败：{error}"))?;
        if output.status.success() {
            return Ok(());
        }
        // The only idempotent disable outcome is "the value did not exist" —
        // anything else (permissions, registry lock, ...) is a real failure.
        let stderr = String::from_utf8_lossy(&output.stderr);
        // `reg.exe` uses exit code 1 for a missing value. On localized Windows
        // builds the diagnostic is emitted in the active code page, so it is
        // not valid UTF-8 and cannot be matched safely; treat that exact
        // undecodable case as the same idempotent "already disabled" result.
        if delete_already_missing(&stderr)
            || (output.status.code() == Some(1)
                && sanitized_process_detail(&output.stderr).is_none())
        {
            return Ok(());
        }
        Err(startup_failure_message(
            "禁用",
            output.status,
            &output.stderr,
        ))
    }
}

#[cfg(not(windows))]
pub fn apply_start_at_login(_enabled: bool) -> Result<(), String> {
    Ok(())
}

#[tauri::command]
pub fn get_dashboard_snapshot(
    app: AppHandle,
    channel: String,
    timezone: Option<String>,
) -> Result<DashboardSnapshot, String> {
    let tz = timezone.unwrap_or_else(|| SettingsStorage::load().timezone);
    let snapshot = Aggregator::build_snapshot(&channel, Some(tz));
    if let Err(error) = crate::windows::tray::update_tray_status(&app, &snapshot) {
        tracing::warn!(%error, "dynamic tray status is unavailable");
    }
    Ok(snapshot)
}

#[tauri::command]
pub fn get_settings() -> Result<AppSettings, String> {
    Ok(SettingsStorage::load())
}

#[tauri::command]
pub fn save_settings(app: AppHandle, settings: AppSettings) -> Result<AppSettings, String> {
    settings.validate()?;
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
    if let Err(error) = SettingsStorage::save(&settings) {
        if previous.start_at_login != settings.start_at_login {
            let _ = apply_start_at_login(previous.start_at_login);
        }
        if previous.global_shortcut != settings.global_shortcut {
            unregister_global_shortcut(&app, &settings.global_shortcut);
            let _ = register_global_shortcut(&app, &previous.global_shortcut);
        }
        return Err(error);
    }
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.set_always_on_top(settings.always_on_top);
    }
    Ok(settings)
}

#[tauri::command]
pub fn refresh_data(app: AppHandle, scope: String) -> Result<DashboardSnapshot, String> {
    let tz = SettingsStorage::load().timezone;
    let snapshot = Aggregator::build_snapshot_with_refresh(&scope, Some(tz), true);
    if let Err(error) = crate::windows::tray::update_tray_status(&app, &snapshot) {
        tracing::warn!(%error, "dynamic tray status is unavailable");
    }
    Ok(snapshot)
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
        apply_widget_geometry(&window, &settings.widget_style, settings.widget_scale)?;
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
pub fn set_widget_style(app: AppHandle, style: String, scale: f64) -> Result<(), String> {
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
    SettingsStorage::save(&s)?;
    if let Some(window) = app.get_webview_window("widget") {
        apply_widget_geometry(&window, &s.widget_style, s.widget_scale)?;
    }
    Ok(())
}

/// Returns the native window size needed by each widget visual style.
/// The content itself is transformed by `scale`; the root's 12px padding is
/// deliberately added after scaling so it neither clips nor creates a large
/// transparent border at non-100% zoom levels.
pub fn widget_size(style: &str, scale: f64) -> LogicalSize<f64> {
    let (content_width, content_height) = match style {
        "capsule" => (224.0, 48.0),
        "gauge" => (224.0, 64.0),
        "tracks" => (240.0, 100.0),
        "disc" => (112.0, 112.0),
        _ => (96.0, 96.0),
    };
    LogicalSize {
        width: content_width * scale + 12.0,
        height: content_height * scale + 12.0,
    }
}

pub fn apply_widget_geometry(
    window: &WebviewWindow,
    style: &str,
    scale: f64,
) -> Result<(), String> {
    window
        .set_size(widget_size(style, scale))
        .map_err(|error| format!("调整悬浮窗尺寸失败：{error}"))
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

#[tauri::command]
pub fn is_main_window_maximized(app: AppHandle) -> Result<bool, String> {
    Ok(app
        .get_webview_window("main")
        .and_then(|window| window.is_maximized().ok())
        .unwrap_or(false))
}

#[tauri::command]
pub fn toggle_maximize_main_window(app: AppHandle) -> Result<bool, String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "主窗口不可用".to_string())?;
    window
        .unminimize()
        .map_err(|error| format!("还原最小化失败：{error}"))?;
    if window.is_maximized().unwrap_or(false) {
        window
            .unmaximize()
            .map_err(|error| format!("还原窗口失败：{error}"))?;
        Ok(false)
    } else {
        window
            .maximize()
            .map_err(|error| format!("最大化窗口失败：{error}"))?;
        Ok(true)
    }
}

#[cfg(all(test, windows))]
mod tests {
    use super::{delete_already_missing, sanitized_process_detail};

    #[test]
    fn reg_delete_value_not_found_is_idempotent() {
        assert!(delete_already_missing(
            "ERROR: The system was unable to find the specified registry key or value."
        ));
        assert!(delete_already_missing(
            "ERROR: The system was unable to find the specified registry key or value.\r\n"
        ));
        assert!(delete_already_missing(
            "错误: 系统找不到指定的注册表项或值。"
        ));
    }

    #[test]
    fn reg_delete_other_failures_are_not_idempotent() {
        assert!(!delete_already_missing("ERROR: Access is denied."));
        assert!(!delete_already_missing("ERROR: The process cannot access the file because it is being used by another process."));
        assert!(!delete_already_missing(""));
    }

    #[test]
    fn invalid_windows_code_page_output_is_not_exposed_as_garbage() {
        assert_eq!(sanitized_process_detail(&[0xff, 0xfe]), None);
        assert_eq!(
            sanitized_process_detail(b"  Access is denied.  "),
            Some("Access is denied.".to_string())
        );
    }
}

#[cfg(test)]
mod widget_size_tests {
    use super::widget_size;

    #[test]
    fn widget_size_matches_content_plus_fixed_padding() {
        let ring = widget_size("ring", 1.0);
        assert_eq!(ring.width, 108.0);
        assert_eq!(ring.height, 108.0);

        let capsule = widget_size("capsule", 0.5);
        assert_eq!(capsule.width, 124.0);
        assert_eq!(capsule.height, 36.0);
    }

    #[test]
    fn widget_scale_does_not_scale_transparent_padding() {
        let standard = widget_size("tracks", 1.0);
        let large = widget_size("tracks", 2.0);
        assert_eq!(large.width, standard.width * 2.0 - 12.0);
        assert_eq!(large.height, standard.height * 2.0 - 12.0);
    }
}

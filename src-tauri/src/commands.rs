use crate::engine::aggregator::Aggregator;
use crate::models::DashboardSnapshot;
use crate::storage::settings::{AppSettings, SettingsStorage};
use tauri::{AppHandle, Manager};

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
                    "{},\"{}\",{},{},{},{},{:.4},{},\"{}\",\"{}\"\n",
                    p.rank,
                    p.name,
                    p.tokens.total,
                    p.tokens.uncached_input,
                    p.tokens.cached_input,
                    p.tokens.output,
                    p.cost_usd,
                    p.sessions,
                    p.last_active_at,
                    p.primary_model
                ));
            }
            Ok(csv)
        }
        "markdown" => {
            let mut md = format!("# Project Rankings · {}\n\n| Rank | Project | Total Tokens | Cost (USD) | Primary Model |\n|---|---|---|---|---|\n", channel);
            for p in &snapshot.projects {
                md.push_str(&format!(
                    "| {} | {} | {} | ${:.4} | {} |\n",
                    p.rank, p.name, p.tokens.total, p.cost_usd, p.primary_model
                ));
            }
            Ok(md)
        }
        _ => Err(format!("Unsupported export format: {}", format)),
    }
}

#[tauri::command]
pub fn toggle_desktop_widget(app: AppHandle, visible: bool) -> Result<(), String> {
    let mut settings = SettingsStorage::load();
    settings.widget_enabled = visible;
    let _ = SettingsStorage::save(&settings);

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
    let mut s = SettingsStorage::load();
    s.widget_style = style;
    s.widget_scale = scale;
    let _ = SettingsStorage::save(&s);
    Ok(())
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

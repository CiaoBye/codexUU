#![allow(linker_messages)]

pub mod commands;
pub mod engine;
pub mod models;
pub mod providers;
pub mod storage;
pub mod windows;

use tauri::Manager;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Initialize logging
    let _ = tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::new("info"))
        .with(tracing_subscriber::fmt::layer())
        .try_init();

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let handle = app.handle();
            let _ = windows::tray::setup_tray(handle);

            // Load settings and apply widget visibility
            let settings = storage::settings::SettingsStorage::load();
            if settings.widget_enabled {
                if let Some(widget_window) = app.get_webview_window("widget") {
                    let _ = widget_window.show();
                    let _ = widget_window.set_always_on_top(true);
                }
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_dashboard_snapshot,
            commands::get_settings,
            commands::save_settings,
            commands::refresh_data,
            commands::export_data,
            commands::toggle_desktop_widget,
            commands::set_widget_style,
            commands::show_main_window,
            commands::minimize_main_window,
            commands::close_main_window,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

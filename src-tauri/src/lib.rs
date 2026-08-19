#![allow(linker_messages)]

pub mod commands;
pub mod engine;
pub mod models;
pub mod providers;
pub mod storage;
pub mod windows;

use tauri::{Manager, WindowEvent};
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
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "main"
                    && storage::settings::SettingsStorage::load().close_to_tray
                {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .setup(|app| {
            let handle = app.handle();
            let _ = windows::tray::setup_tray(handle);

            // Load settings and apply all runtime-only settings.
            let settings = storage::settings::SettingsStorage::load();
            if let Some(main_window) = app.get_webview_window("main") {
                let _ = main_window.set_always_on_top(settings.always_on_top);
            }
            if let Some(widget_window) = app.get_webview_window("widget") {
                if let Err(error) = commands::apply_widget_geometry(
                    &widget_window,
                    &settings.widget_style,
                    settings.widget_scale,
                ) {
                    tracing::warn!(%error, "widget geometry is unavailable");
                }
                if settings.widget_enabled {
                    let _ = widget_window.show();
                    let _ = widget_window.set_always_on_top(true);
                } else {
                    let _ = widget_window.hide();
                }
            }
            if let Err(error) =
                commands::register_global_shortcut(handle, &settings.global_shortcut)
            {
                tracing::warn!(%error, "global shortcut is unavailable");
            }
            if let Err(error) = commands::apply_start_at_login(settings.start_at_login) {
                tracing::warn!(%error, "start-at-login setting is unavailable");
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

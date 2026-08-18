use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppSettings {
    pub schema_version: u32,
    pub theme: String,           // "dark", "light", "system"
    pub language: String,        // "zh-CN", "en"
    pub quota_mode: String,      // "used", "remaining"
    pub timezone: String,        // "Asia/Shanghai", "UTC", etc.
    pub global_shortcut: String, // "Ctrl+U"
    pub always_on_top: bool,
    pub close_to_tray: bool,
    pub start_at_login: bool,
    pub widget_enabled: bool,
    pub widget_style: String, // "ring", "capsule", "tracks", "disc", "gauge"
    pub widget_scale: f64,    // 0.2 to 3.0
    pub default_channel: String, // "codex", "antigravity", "all"
}

impl Default for AppSettings {
    fn default() -> Self {
        Self {
            schema_version: 1,
            theme: "dark".to_string(),
            language: "zh-CN".to_string(),
            quota_mode: "used".to_string(),
            timezone: "Asia/Shanghai".to_string(),
            global_shortcut: "Ctrl+U".to_string(),
            always_on_top: false,
            close_to_tray: true,
            start_at_login: false,
            widget_enabled: true,
            widget_style: "ring".to_string(),
            widget_scale: 1.0,
            default_channel: "codex".to_string(),
        }
    }
}

pub struct SettingsStorage;

impl SettingsStorage {
    fn get_settings_path() -> PathBuf {
        let appdata = dirs::data_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join("CodexUU");
        let _ = fs::create_dir_all(&appdata);
        appdata.join("settings.json")
    }

    pub fn load() -> AppSettings {
        let path = Self::get_settings_path();
        if path.exists() {
            if let Ok(content) = fs::read_to_string(&path) {
                if let Ok(settings) = serde_json::from_str::<AppSettings>(&content) {
                    return settings;
                }
            }
        }

        // Try migrate legacy ~/.codexU/config.json if exists
        if let Some(home) = dirs::home_dir() {
            let legacy_config = home.join(".codexU").join("config.json");
            if legacy_config.exists() {
                if let Ok(content) = fs::read_to_string(&legacy_config) {
                    if let Ok(val) = serde_json::from_str::<serde_json::Value>(&content) {
                        let mut settings = AppSettings::default();
                        if let Some(th) = val.get("theme").and_then(|v| v.as_str()) {
                            settings.theme = th.to_string();
                        }
                        if let Some(lang) = val.get("language").and_then(|v| v.as_str()) {
                            settings.language = lang.to_string();
                        }
                        if let Some(qm) = val.get("quota_mode").and_then(|v| v.as_str()) {
                            settings.quota_mode = qm.to_string();
                        }
                        let _ = Self::save(&settings);
                        return settings;
                    }
                }
            }
        }

        let defaults = AppSettings::default();
        let _ = Self::save(&defaults);
        defaults
    }

    pub fn save(settings: &AppSettings) -> Result<(), String> {
        let path = Self::get_settings_path();
        let content = serde_json::to_string_pretty(settings)
            .map_err(|e| format!("Failed to serialize settings: {}", e))?;
        fs::write(path, content).map_err(|e| format!("Failed to write settings: {}", e))?;
        Ok(())
    }
}

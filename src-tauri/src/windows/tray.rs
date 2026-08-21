use crate::commands::apply_widget_geometry;
use crate::models::{DashboardSnapshot, QuotaSnapshot};
use crate::storage::settings::SettingsStorage;
use tauri::{
    image::Image,
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager,
};

const TRAY_ICON_SIZE: u32 = 32;

fn quota_remaining_ratio(quota: &QuotaSnapshot) -> Option<f64> {
    quota
        .five_hour_remaining_ratio
        .or(quota.seven_day_remaining_ratio)
        .or_else(|| {
            quota
                .five_hour_used_ratio
                .or(quota.seven_day_used_ratio)
                .map(|used| 1.0 - used)
        })
        .or_else(|| {
            quota.families.iter().find_map(|family| {
                family
                    .five_hour_remaining_ratio
                    .or(family.seven_day_remaining_ratio)
                    .or_else(|| {
                        family
                            .five_hour_used_ratio
                            .or(family.seven_day_used_ratio)
                            .map(|used| 1.0 - used)
                    })
            })
        })
        .filter(|ratio| ratio.is_finite())
        .map(|ratio| ratio.clamp(0.0, 1.0))
}

fn status_color(remaining: Option<f64>) -> [u8; 4] {
    match remaining {
        Some(ratio) if ratio <= 0.2 => [220, 80, 92, 255],
        Some(ratio) if ratio <= 0.5 => [236, 166, 76, 255],
        Some(_) => [44, 159, 155, 255],
        None => [125, 135, 150, 255],
    }
}

/// Resizes the brand icon and overlays a compact quota badge. The badge arc is
/// intentionally data-driven so Windows users can read the latest quota state
/// without opening the main window, while the original app mark stays intact.
fn render_dynamic_icon(
    base_rgba: &[u8],
    base_width: u32,
    base_height: u32,
    remaining: Option<f64>,
) -> Vec<u8> {
    let size = TRAY_ICON_SIZE as usize;
    let mut output = vec![0; size * size * 4];
    if base_width > 0
        && base_height > 0
        && base_rgba.len() >= (base_width as usize * base_height as usize * 4)
    {
        for y in 0..size {
            let source_y = y * base_height as usize / size;
            for x in 0..size {
                let source_x = x * base_width as usize / size;
                let source = (source_y * base_width as usize + source_x) * 4;
                let destination = (y * size + x) * 4;
                output[destination..destination + 4]
                    .copy_from_slice(&base_rgba[source..source + 4]);
            }
        }
    }

    let center_x = 24.0;
    let center_y = 24.0;
    let outer_radius = 7.5;
    let inner_radius = 4.0;
    let progress = remaining.unwrap_or(0.0).clamp(0.0, 1.0);
    let color = status_color(remaining);
    for y in 0..size {
        for x in 0..size {
            let dx = x as f64 + 0.5 - center_x;
            let dy = y as f64 + 0.5 - center_y;
            let distance = (dx * dx + dy * dy).sqrt();
            if distance > outer_radius {
                continue;
            }
            let pixel = (y * size + x) * 4;
            if distance < inner_radius {
                output[pixel..pixel + 4].copy_from_slice(&[20, 30, 40, 255]);
                continue;
            }

            // Start at twelve o'clock and grow clockwise around the badge.
            let angle =
                (dy.atan2(dx) + std::f64::consts::FRAC_PI_2).rem_euclid(std::f64::consts::TAU);
            let fraction = angle / std::f64::consts::TAU;
            let ring_color = if remaining.is_some() && fraction <= progress {
                color
            } else {
                [67, 77, 90, 255]
            };
            output[pixel..pixel + 4].copy_from_slice(&ring_color);
        }
    }
    output
}

fn format_tokens(value: u64) -> String {
    if value >= 1_000_000_000 {
        format!("{:.1}B", value as f64 / 1_000_000_000.0)
    } else if value >= 1_000_000 {
        format!("{:.1}M", value as f64 / 1_000_000.0)
    } else if value >= 1_000 {
        format!("{:.1}K", value as f64 / 1_000.0)
    } else {
        value.to_string()
    }
}

fn tray_tooltip(snapshot: &DashboardSnapshot, remaining: Option<f64>) -> String {
    let channel = match snapshot.channel.as_str() {
        "antigravity" => "Antigravity",
        "all" => "全部聚合",
        _ => "Codex",
    };
    let quota = remaining
        .map(|ratio| format!(" · 额度剩余 {:.0}%", ratio * 100.0))
        .unwrap_or_else(|| " · 额度 --".to_string());
    format!(
        "CodexUU · {channel} · 今日 {} Token{quota}",
        format_tokens(snapshot.tokens.today.total)
    )
}

pub fn update_tray_status(app: &AppHandle, snapshot: &DashboardSnapshot) -> Result<(), String> {
    let tray = app
        .tray_by_id("main_tray")
        .ok_or_else(|| "系统托盘尚未初始化".to_string())?;
    let base = app
        .default_window_icon()
        .ok_or_else(|| "应用图标不可用".to_string())?;
    let remaining = quota_remaining_ratio(&snapshot.quota);
    let rgba = render_dynamic_icon(base.rgba(), base.width(), base.height(), remaining);
    tray.set_icon(Some(Image::new_owned(rgba, TRAY_ICON_SIZE, TRAY_ICON_SIZE)))
        .map_err(|error| format!("更新托盘图标失败：{error}"))?;
    tray.set_tooltip(Some(tray_tooltip(snapshot, remaining)))
        .map_err(|error| format!("更新托盘提示失败：{error}"))
}

pub fn setup_tray(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let show_i = MenuItem::with_id(app, "show", "打开 CodexUU", true, None::<&str>)?;
    let hide_i = MenuItem::with_id(app, "hide", "最小化到托盘", true, None::<&str>)?;
    let widget_i = MenuItem::with_id(app, "widget", "切换桌面悬浮窗", true, None::<&str>)?;
    let quit_i = MenuItem::with_id(app, "quit", "退出程序", true, None::<&str>)?;

    let menu = Menu::with_items(app, &[&show_i, &hide_i, &widget_i, &quit_i])?;
    let icon = app.default_window_icon().cloned();

    let mut builder = TrayIconBuilder::with_id("main_tray")
        .tooltip("CodexUU - 本地 AI 编程控制台")
        .menu(&menu)
        .show_menu_on_left_click(false);

    if let Some(i) = icon {
        builder = builder.icon(i);
    }

    let _tray = builder
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.unminimize();
                    let _ = window.set_focus();
                }
            }
            "hide" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.hide();
                }
            }
            "widget" => {
                if let Some(window) = app.get_webview_window("widget") {
                    let visible = !window.is_visible().unwrap_or(false);
                    let mut settings = SettingsStorage::load();
                    settings.widget_enabled = visible;
                    let _ = SettingsStorage::save(&settings);
                    let _ = apply_widget_geometry(
                        &window,
                        &settings.widget_style,
                        settings.widget_scale,
                    );
                    if visible {
                        let _ = window.show();
                        let _ = window.set_always_on_top(true);
                    } else {
                        let _ = window.hide();
                    }
                }
            }
            "quit" => {
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let app = tray.app_handle();
                if let Some(window) = app.get_webview_window("main") {
                    if window.is_visible().unwrap_or(false) {
                        let _ = window.hide();
                    } else {
                        let _ = window.show();
                        let _ = window.unminimize();
                        let _ = window.set_focus();
                    }
                }
            }
        })
        .build(app)?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{render_dynamic_icon, status_color, tray_tooltip, TRAY_ICON_SIZE};
    use crate::models::{DashboardSnapshot, QuotaSnapshot, TokenBreakdown, TokenPeriods};

    #[test]
    fn dynamic_badge_changes_with_quota_remaining() {
        let base = vec![255; 16 * 16 * 4];
        let abundant = render_dynamic_icon(&base, 16, 16, Some(0.8));
        let low = render_dynamic_icon(&base, 16, 16, Some(0.1));

        assert_eq!(
            abundant.len(),
            (TRAY_ICON_SIZE * TRAY_ICON_SIZE * 4) as usize
        );
        assert_ne!(abundant, low);
        assert_eq!(status_color(Some(0.8)), [44, 159, 155, 255]);
        assert_eq!(status_color(Some(0.1)), [220, 80, 92, 255]);
    }

    #[test]
    fn tooltip_reports_channel_tokens_and_quota() {
        let mut snapshot = DashboardSnapshot {
            channel: "antigravity".to_string(),
            quota: QuotaSnapshot::default(),
            quotas: std::collections::HashMap::new(),
            tokens: TokenPeriods::default(),
            daily_activities: Vec::new(),
            models: Vec::new(),
            tasks: Vec::new(),
            projects: Vec::new(),
            skills_and_tools: Vec::new(),
            sources_health: Vec::new(),
            timestamp: String::new(),
        };
        snapshot.tokens.today = TokenBreakdown::new(1_000_000, 2_000_000, 500_000);
        let tooltip = tray_tooltip(&snapshot, Some(0.42));

        assert!(tooltip.contains("Antigravity"));
        assert!(tooltip.contains("3.5M Token"));
        assert!(tooltip.contains("42%"));
    }
}

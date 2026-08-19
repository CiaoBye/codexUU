//! Read Antigravity weekly / 5-hour quota from the local language server.
//!
//! The official Model Quota UI exposes two families (Gemini, Claude & GPT),
//! each with a weekly window and a 5-hour window. This module never invents
//! ratios: missing windows stay empty.

use std::collections::{HashMap, HashSet};
use std::fs;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::Path;
use std::process::Command;
use std::time::Duration;

use chrono::{DateTime, Utc};
use chrono_tz::Tz;
use serde_json::Value;

use crate::models::{QuotaFamily, QuotaSnapshot};

const RPC_PREFIX: &str = "/exa.language_server_pb.LanguageServerService";
const QUOTA_METHODS: [&str; 3] = [
    "RetrieveUserQuotaSummary",
    "GetUserStatus",
    "GetCommandModelConfigs",
];

pub fn fetch_quota(tz: &Tz) -> QuotaSnapshot {
    let endpoints = discover_local_endpoints();
    if endpoints.is_empty() {
        return unavailable(tz, "未检测到运行中的 Antigravity，无法读取额度");
    }

    for endpoint in &endpoints {
        for method in QUOTA_METHODS {
            if let Some(quota) = query_endpoint(endpoint, method, tz) {
                return quota;
            }
        }
    }

    unavailable(
        tz,
        "已发现 Antigravity 本地端口，但额度接口无有效窗口。请保持 Antigravity 打开后刷新",
    )
}

fn unavailable(tz: &Tz, source: &str) -> QuotaSnapshot {
    QuotaSnapshot {
        status: "unavailable".to_string(),
        source: source.to_string(),
        last_updated: Utc::now()
            .with_timezone(tz)
            .format("%Y-%m-%d %H:%M:%S")
            .to_string(),
        ..Default::default()
    }
}

#[derive(Debug, Clone)]
struct LocalEndpoint {
    port: u16,
    csrf: Option<String>,
    prefer_https: bool,
}

fn discover_local_endpoints() -> Vec<LocalEndpoint> {
    let mut by_port: HashMap<u16, LocalEndpoint> = HashMap::new();
    for endpoint in discover_from_logs() {
        if port_open(endpoint.port) {
            by_port.insert(endpoint.port, endpoint);
        }
    }

    let (command_lines, extra_ports) = process_inventory();
    let mut csrf = None;
    let mut http_ports = HashSet::new();
    for line in &command_lines {
        if csrf.is_none() {
            csrf = flag_value(line, "extension_server_csrf_token")
                .or_else(|| flag_value(line, "csrf_token"));
        }
        if let Some(port) = flag_value(line, "extension_server_port")
            .and_then(|value| value.parse::<u16>().ok())
            .filter(|port| *port > 0)
        {
            http_ports.insert(port);
        }
    }
    let csrf = csrf
        .filter(|token| !token.is_empty())
        .or_else(|| by_port.values().find_map(|endpoint| endpoint.csrf.clone()));

    for port in extra_ports.into_iter().chain(http_ports.iter().copied()) {
        if !port_open(port) {
            continue;
        }
        by_port.entry(port).or_insert(LocalEndpoint {
            port,
            csrf: csrf.clone(),
            prefer_https: !http_ports.contains(&port),
        });
    }

    let mut endpoints: Vec<_> = by_port.into_values().collect();
    endpoints.sort_by_key(|endpoint| (!endpoint.prefer_https, endpoint.port));
    endpoints
}

fn discover_from_logs() -> Vec<LocalEndpoint> {
    let log_dir = dirs::data_dir()
        .unwrap_or_default()
        .join("Antigravity")
        .join("logs");
    let main_log = read_log_tail(&log_dir.join("main.log"), 64 * 1024);
    let ls_log = read_log_tail(&log_dir.join("language_server.log"), 64 * 1024);
    parse_log_endpoints(&main_log, &ls_log)
}

fn read_log_tail(path: &Path, max_bytes: usize) -> String {
    let Ok(bytes) = fs::read(path) else {
        return String::new();
    };
    let slice = if bytes.len() > max_bytes {
        &bytes[bytes.len() - max_bytes..]
    } else {
        &bytes
    };
    String::from_utf8_lossy(slice).into_owned()
}

fn parse_log_endpoints(main_log: &str, ls_log: &str) -> Vec<LocalEndpoint> {
    let csrf = last_flag_value(main_log, "csrf_token").filter(|token| !token.is_empty());
    let mut https_ports = HashSet::new();
    let mut http_ports = HashSet::new();
    if let Some(port) = last_local_https_port(main_log) {
        https_ports.insert(port);
    }
    for (port, kind) in last_listening_ports(ls_log) {
        if kind == "https" {
            https_ports.insert(port);
        } else {
            http_ports.insert(port);
        }
    }
    let mut endpoints = Vec::new();
    for port in https_ports {
        endpoints.push(LocalEndpoint {
            port,
            csrf: csrf.clone(),
            prefer_https: true,
        });
    }
    for port in http_ports {
        endpoints.push(LocalEndpoint {
            port,
            csrf: csrf.clone(),
            prefer_https: false,
        });
    }
    endpoints
}

fn last_flag_value(text: &str, name: &str) -> Option<String> {
    let mut found = None;
    for line in text.lines() {
        if let Some(value) = flag_value(line, name) {
            found = Some(value);
        }
    }
    found
}

fn last_local_https_port(text: &str) -> Option<u16> {
    let mut found = None;
    for line in text.lines() {
        if let Some(index) = line.find("https://127.0.0.1:") {
            let rest = &line[index + "https://127.0.0.1:".len()..];
            let digits: String = rest.chars().take_while(|ch| ch.is_ascii_digit()).collect();
            if let Ok(port) = digits.parse::<u16>() {
                if port > 0 {
                    found = Some(port);
                }
            }
        }
    }
    found
}

fn last_listening_ports(text: &str) -> Vec<(u16, &'static str)> {
    let mut https = None;
    let mut http = None;
    for line in text.lines() {
        if let Some(port) = capture_after(line, "random port at ") {
            if line.to_ascii_lowercase().contains("https") {
                https = Some(port);
            } else if line.to_ascii_lowercase().contains("http") {
                http = Some(port);
            }
        }
    }
    let mut ports = Vec::new();
    if let Some(port) = https {
        ports.push((port, "https"));
    }
    if let Some(port) = http {
        ports.push((port, "http"));
    }
    ports
}

fn capture_after(line: &str, marker: &str) -> Option<u16> {
    let index = line.find(marker)?;
    let rest = &line[index + marker.len()..];
    let digits: String = rest.chars().take_while(|ch| ch.is_ascii_digit()).collect();
    digits.parse::<u16>().ok().filter(|port| *port > 0)
}

fn port_open(port: u16) -> bool {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    TcpStream::connect_timeout(&addr, Duration::from_millis(150)).is_ok()
}

fn process_inventory() -> (Vec<String>, Vec<u16>) {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let script = r#"
$lines = @()
$pids = New-Object System.Collections.Generic.List[int]
Get-CimInstance Win32_Process | ForEach-Object {
  $name = [string]$_.Name
  $cmd = [string]$_.CommandLine
  if ($name -match 'Antigravity|language_server' -or ($cmd -and $cmd -match 'antigravity|language_server')) {
    if ($cmd) { $lines += ('CMD|' + $cmd) }
    if ($_.ProcessId) { $pids.Add([int]$_.ProcessId) | Out-Null }
  }
}
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
  if ($pids -contains $_.OwningProcess -and ($_.LocalAddress -eq '127.0.0.1' -or $_.LocalAddress -eq '::1')) {
    $lines += ('PORT|' + $_.LocalPort)
  }
}
$lines -join "`n"
"#;
        let Ok(output) = Command::new("powershell")
            .args(["-NoProfile", "-NonInteractive", "-Command", script])
            .creation_flags(0x0800_0000)
            .output()
        else {
            return (Vec::new(), Vec::new());
        };
        let mut commands = Vec::new();
        let mut ports = Vec::new();
        for line in String::from_utf8_lossy(&output.stdout).lines() {
            let line = line.trim();
            if let Some(cmd) = line.strip_prefix("CMD|") {
                if !cmd.is_empty() {
                    commands.push(cmd.to_string());
                }
            } else if let Some(port) = line.strip_prefix("PORT|") {
                if let Ok(port) = port.parse::<u16>() {
                    if port > 0 {
                        ports.push(port);
                    }
                }
            }
        }
        (commands, ports)
    }
    #[cfg(not(windows))]
    {
        (Vec::new(), Vec::new())
    }
}

fn flag_value(command_line: &str, name: &str) -> Option<String> {
    let needle = format!("--{name}");
    let mut rest = command_line;
    while let Some(pos) = rest.find(&needle) {
        rest = &rest[pos + needle.len()..];
        let after = rest.trim_start();
        if after.is_empty() || after.starts_with("--") {
            continue;
        }
        let value = after.split_whitespace().next()?.trim_matches('"');
        if !value.is_empty() {
            return Some(value.to_string());
        }
    }
    None
}

fn query_endpoint(endpoint: &LocalEndpoint, method: &str, tz: &Tz) -> Option<QuotaSnapshot> {
    let path = format!("{RPC_PREFIX}/{method}");
    let body = if endpoint.prefer_https {
        post_json_https(endpoint.port, &path, endpoint.csrf.as_deref(), "{}")
            .or_else(|| post_json_http(endpoint.port, &path, endpoint.csrf.as_deref(), "{}"))
    } else {
        post_json_http(endpoint.port, &path, endpoint.csrf.as_deref(), "{}")
            .or_else(|| post_json_https(endpoint.port, &path, endpoint.csrf.as_deref(), "{}"))
    }?;
    parse_quota_payload(
        &body,
        tz,
        &format!("Antigravity 本地服务 :{}", endpoint.port),
    )
}

fn post_json_http(port: u16, path: &str, csrf: Option<&str>, body: &str) -> Option<Value> {
    let mut stream = TcpStream::connect(("127.0.0.1", port)).ok()?;
    stream.set_read_timeout(Some(Duration::from_secs(2))).ok()?;
    stream
        .set_write_timeout(Some(Duration::from_secs(2)))
        .ok()?;

    let mut request = format!(
        "POST {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Type: application/json\r\nAccept: application/json\r\nConnect-Protocol-Version: 1\r\nContent-Length: {}\r\nConnection: close\r\n",
        body.len()
    );
    if let Some(token) = csrf.filter(|token| !token.is_empty()) {
        request.push_str("X-Codeium-Csrf-Token: ");
        request.push_str(token);
        request.push_str("\r\n");
    }
    request.push_str("\r\n");
    request.push_str(body);
    stream.write_all(request.as_bytes()).ok()?;

    let mut raw = Vec::new();
    stream.read_to_end(&mut raw).ok()?;
    let text = String::from_utf8_lossy(&raw);
    let body_text = http_body(&text)?;
    serde_json::from_str(body_text).ok()
}

fn post_json_https(port: u16, path: &str, csrf: Option<&str>, body: &str) -> Option<Value> {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let url = format!("https://127.0.0.1:{port}{path}");
        let mut command = Command::new("curl.exe");
        command
            .args([
                "-k",
                "-sS",
                "-m",
                "2",
                "-X",
                "POST",
                &url,
                "-H",
                "Content-Type: application/json",
                "-H",
                "Accept: application/json",
                "-H",
                "Connect-Protocol-Version: 1",
                "--data-raw",
                body,
            ])
            .creation_flags(0x0800_0000);
        if let Some(token) = csrf.filter(|token| !token.is_empty()) {
            command.args(["-H", &format!("X-Codeium-Csrf-Token: {token}")]);
        }
        let output = command.output().ok()?;
        if !output.status.success() {
            return None;
        }
        serde_json::from_slice(&output.stdout).ok()
    }
    #[cfg(not(windows))]
    {
        let _ = (port, path, csrf, body);
        None
    }
}

fn http_body(response: &str) -> Option<&str> {
    let (sep, sep_len) = if let Some(index) = response.find("\r\n\r\n") {
        (index, 4)
    } else {
        let index = response.find("\n\n")?;
        (index, 2)
    };
    let headers = &response[..sep];
    let status_line = headers.lines().next()?;
    if !status_line.contains(" 200") {
        return None;
    }
    Some(response[sep + sep_len..].trim())
}

pub fn parse_quota_payload(value: &Value, tz: &Tz, source: &str) -> Option<QuotaSnapshot> {
    let root = value.get("response").unwrap_or(value);
    let mut families: HashMap<String, QuotaFamily> = HashMap::new();

    if let Some(groups) = root
        .get("groups")
        .or_else(|| root.get("quotaGroups"))
        .and_then(Value::as_array)
    {
        for group in groups {
            let title = group
                .get("displayName")
                .or_else(|| group.get("name"))
                .and_then(Value::as_str)
                .unwrap_or("");
            let Some((id, label)) = classify_family(title) else {
                continue;
            };
            let family = families
                .entry(id.to_string())
                .or_insert_with(|| QuotaFamily {
                    id: id.to_string(),
                    label: label.to_string(),
                    ..Default::default()
                });
            fill_family_from_buckets(family, group.get("buckets"), tz);
        }
    }
    collect_legacy_configs(root, tz, &mut families);

    if families.is_empty() {
        return None;
    }

    let mut ordered = Vec::new();
    for key in ["gemini", "claude"] {
        if let Some(family) = families.remove(key) {
            ordered.push(family);
        }
    }
    ordered.extend(families.into_values());
    ordered.retain(|family| family.has_five_hour || family.has_seven_day);
    if ordered.is_empty() {
        return None;
    }

    let mut quota = QuotaSnapshot {
        status: "available".to_string(),
        source: source.to_string(),
        last_updated: Utc::now()
            .with_timezone(tz)
            .format("%Y-%m-%d %H:%M:%S")
            .to_string(),
        families: ordered,
        ..Default::default()
    };
    if let Some(primary) = quota
        .families
        .iter()
        .find(|family| family.id == "gemini")
        .cloned()
        .or_else(|| quota.families.first().cloned())
    {
        quota.has_five_hour = primary.has_five_hour;
        quota.has_seven_day = primary.has_seven_day;
        quota.five_hour_used_ratio = primary.five_hour_used_ratio;
        quota.five_hour_remaining_ratio = primary.five_hour_remaining_ratio;
        quota.five_hour_reset_at = primary.five_hour_reset_at;
        quota.seven_day_used_ratio = primary.seven_day_used_ratio;
        quota.seven_day_remaining_ratio = primary.seven_day_remaining_ratio;
        quota.seven_day_reset_at = primary.seven_day_reset_at;
    }
    Some(quota)
}

fn classify_family(name: &str) -> Option<(&'static str, &'static str)> {
    let lower = name.to_ascii_lowercase();
    if lower.contains("claude") || lower.contains("gpt") {
        Some(("claude", "Claude 与 GPT"))
    } else if lower.contains("gemini") {
        Some(("gemini", "Gemini"))
    } else {
        None
    }
}

fn fill_family_from_buckets(family: &mut QuotaFamily, buckets: Option<&Value>, tz: &Tz) {
    let Some(items) = buckets.and_then(Value::as_array) else {
        return;
    };
    for bucket in items {
        let Some(remaining) = remaining_fraction(bucket) else {
            continue;
        };
        let reset = reset_label(bucket, tz);
        let label = bucket_label(bucket);
        if is_weekly(&label) {
            apply_family_window(family, true, remaining, reset);
        } else if is_five_hour(&label) {
            apply_family_window(family, false, remaining, reset);
        }
    }
}

fn collect_legacy_configs(root: &Value, tz: &Tz, families: &mut HashMap<String, QuotaFamily>) {
    let configs = root
        .pointer("/userStatus/cascadeModelConfigData/clientModelConfigs")
        .or_else(|| root.pointer("/cascadeModelConfigData/clientModelConfigs"))
        .and_then(Value::as_array);
    let Some(configs) = configs else {
        return;
    };
    for config in configs {
        let info = config.get("quotaInfo").unwrap_or(config);
        let Some(remaining) = remaining_fraction(info) else {
            continue;
        };
        let reset = reset_label(info, tz).or_else(|| reset_label(config, tz));
        let label = bucket_label(config);
        let Some((id, family_label)) = classify_family(&label) else {
            continue;
        };
        let family = families
            .entry(id.to_string())
            .or_insert_with(|| QuotaFamily {
                id: id.to_string(),
                label: family_label.to_string(),
                ..Default::default()
            });
        if is_weekly(&label) {
            apply_family_window(family, true, remaining, reset);
        } else if is_five_hour(&label) {
            apply_family_window(family, false, remaining, reset);
        }
    }
}

fn apply_family_window(
    family: &mut QuotaFamily,
    weekly: bool,
    remaining: f64,
    reset: Option<String>,
) {
    let used = (1.0 - remaining).clamp(0.0, 1.0);
    if weekly {
        family.has_seven_day = true;
        family.seven_day_used_ratio = Some(used);
        family.seven_day_remaining_ratio = Some(remaining);
        family.seven_day_reset_at = reset;
    } else {
        family.has_five_hour = true;
        family.five_hour_used_ratio = Some(used);
        family.five_hour_remaining_ratio = Some(remaining);
        family.five_hour_reset_at = reset;
    }
}

fn remaining_fraction(value: &Value) -> Option<f64> {
    value
        .pointer("/remaining/remainingFraction")
        .or_else(|| value.get("remainingFraction"))
        .or_else(|| value.pointer("/quotaInfo/remainingFraction"))
        .or_else(|| value.pointer("/remainingFraction"))
        .and_then(as_ratio)
        .or_else(|| {
            value
                .get("usedFraction")
                .or_else(|| value.pointer("/quotaInfo/usedFraction"))
                .and_then(as_ratio)
                .map(|used| (1.0 - used).clamp(0.0, 1.0))
        })
}

fn as_ratio(value: &Value) -> Option<f64> {
    let number = match value {
        Value::Number(n) => n.as_f64()?,
        Value::String(s) => s.trim().parse().ok()?,
        _ => return None,
    };
    let ratio = if number > 1.0 { number / 100.0 } else { number };
    (ratio.is_finite() && (0.0..=1.0).contains(&ratio)).then_some(ratio)
}

fn reset_label(value: &Value, _tz: &Tz) -> Option<String> {
    if let Some(description) = value
        .get("description")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|text| !text.is_empty())
        .filter(|text| is_refresh_description(text))
    {
        return Some(localize_refresh(description));
    }
    let raw = value
        .get("resetTime")
        .or_else(|| value.get("reset_time"))
        .or_else(|| value.get("resetAt"))?;
    let instant = if let Some(text) = raw.as_str().filter(|text| !text.trim().is_empty()) {
        DateTime::parse_from_rfc3339(text)
            .ok()
            .map(|parsed| parsed.with_timezone(&Utc))
    } else {
        raw.as_i64()
            .and_then(|seconds| DateTime::<Utc>::from_timestamp(seconds, 0))
    };
    if let Some(instant) = instant {
        return Some(relative_refresh(instant));
    }
    raw.as_str().map(ToString::to_string)
}

fn is_refresh_description(description: &str) -> bool {
    let lower = description.to_ascii_lowercase();
    lower.starts_with("full refresh in")
        || lower.starts_with("resets in")
        || lower.contains("后刷新")
}

fn localize_refresh(description: &str) -> String {
    let lower = description.trim().to_ascii_lowercase();
    let rest = lower
        .strip_prefix("full refresh in ")
        .or_else(|| lower.strip_prefix("resets in "))
        .unwrap_or(&lower);
    let localized = rest
        .replace(" days", " 天")
        .replace(" day", " 天")
        .replace(" hours", " 小时")
        .replace(" hour", " 小时")
        .replace(" minutes", " 分钟")
        .replace(" minute", " 分钟");
    if description
        .to_ascii_lowercase()
        .starts_with("full refresh in")
        || description.to_ascii_lowercase().starts_with("resets in")
    {
        format!("{localized}后刷新")
    } else {
        description.to_string()
    }
}

fn relative_refresh(reset_at: DateTime<Utc>) -> String {
    let now = Utc::now();
    let delta = reset_at.signed_duration_since(now);
    if delta.num_seconds() <= 0 {
        return "即将刷新".to_string();
    }
    let days = delta.num_days();
    let hours = delta.num_hours() % 24;
    let minutes = delta.num_minutes() % 60;
    if days > 0 {
        if hours > 0 {
            format!("{days} 天 {hours} 小时后刷新")
        } else {
            format!("{days} 天后刷新")
        }
    } else if hours > 0 {
        if minutes > 0 {
            format!("{hours} 小时 {minutes} 分钟后刷新")
        } else {
            format!("{hours} 小时后刷新")
        }
    } else {
        format!("{minutes} 分钟后刷新")
    }
}

fn bucket_label(value: &Value) -> String {
    [
        value.get("bucketId"),
        value.get("displayName"),
        value.get("name"),
        value.get("model"),
        value.get("modelName"),
    ]
    .into_iter()
    .flatten()
    .filter_map(Value::as_str)
    .collect::<Vec<_>>()
    .join(" ")
    .to_ascii_lowercase()
}

fn is_weekly(label: &str) -> bool {
    label.contains("week") || label.contains("7d") || label.contains("seven")
}

fn is_five_hour(label: &str) -> bool {
    label.contains("five")
        || label.contains("5h")
        || label.contains("5-hour")
        || label.contains("5 hour")
        || label.contains("session")
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono_tz::Asia::Shanghai;
    use serde_json::json;

    fn sample_payload() -> Value {
        json!({
            "response": {
                "groups": [
                    {
                        "displayName": "Gemini Models",
                        "buckets": [
                            {
                                "bucketId": "gemini-weekly",
                                "displayName": "Weekly",
                                "description": "Full refresh in 5 days 1 hour",
                                "remaining": { "remainingFraction": 0.78 },
                                "resetTime": "2026-08-24T12:41:00Z"
                            },
                            {
                                "bucketId": "gemini-five-hour",
                                "displayName": "Five hour",
                                "description": "Full refresh in 31 minutes",
                                "remaining": { "remainingFraction": 0.95 },
                                "resetTime": "2026-08-19T06:12:00Z"
                            }
                        ]
                    },
                    {
                        "displayName": "Claude and GPT models",
                        "buckets": [
                            {
                                "bucketId": "claude-weekly",
                                "displayName": "Weekly",
                                "description": "Full refresh in 5 days 3 hours",
                                "remaining": { "remainingFraction": 0.32 },
                                "resetTime": "2026-08-24T14:41:00Z"
                            },
                            {
                                "bucketId": "claude-five-hour",
                                "displayName": "Five hour",
                                "remaining": { "remainingFraction": 1.0 }
                            }
                        ]
                    }
                ]
            }
        })
    }

    #[test]
    fn parse_summary_keeps_gemini_and_claude_windows() {
        let quota = parse_quota_payload(&sample_payload(), &Shanghai, "test").unwrap();
        assert_eq!(quota.families.len(), 2);
        assert_eq!(quota.families[0].label, "Gemini");
        assert_eq!(quota.families[0].seven_day_remaining_ratio, Some(0.78));
        assert_eq!(quota.families[0].five_hour_remaining_ratio, Some(0.95));
        assert_eq!(quota.families[1].label, "Claude 与 GPT");
        assert_eq!(quota.families[1].seven_day_remaining_ratio, Some(0.32));
        assert_eq!(quota.families[1].five_hour_remaining_ratio, Some(1.0));
        assert_eq!(
            quota.families[0].seven_day_reset_at.as_deref(),
            Some("5 天 1 小时后刷新")
        );
        assert_eq!(
            quota.families[1].seven_day_reset_at.as_deref(),
            Some("5 天 3 小时后刷新")
        );
        assert_eq!(quota.seven_day_remaining_ratio, Some(0.78));
        assert_eq!(quota.five_hour_remaining_ratio, Some(0.95));
    }

    #[test]
    fn usage_prose_description_falls_back_to_reset_time() {
        let payload = serde_json::json!({
            "groups": [{
                "displayName": "Gemini Models",
                "buckets": [{
                    "bucketId": "gemini-weekly",
                    "displayName": "Weekly",
                    "description": "You have used some of your weekly quota.",
                    "remaining": { "remainingFraction": 0.22 },
                    "resetTime": "2026-08-24T12:41:00Z"
                }]
            }]
        });
        let quota = parse_quota_payload(&payload, &Shanghai, "test").unwrap();
        let reset = quota.families[0].seven_day_reset_at.as_deref().unwrap();
        assert!(reset.contains("后刷新"), "reset was {reset}");
        assert!(!reset.contains("You have used"));
    }

    #[test]
    fn parse_logs_reads_https_http_and_csrf() {
        let main = r#"
Spawning: language_server.exe --https_server_port 0 --csrf_token 1c22c3a4-bced-45e7-b6de-f3cf31a57494 --app_data_dir antigravity
Local:       https://127.0.0.1:61687/
"#;
        let ls = r#"
Language server listening on random port at 61687 for HTTPS (gRPC)
Language server listening on random port at 61688 for HTTP
"#;
        let endpoints = parse_log_endpoints(main, ls);
        assert!(endpoints
            .iter()
            .any(|endpoint| endpoint.port == 61687 && endpoint.prefer_https));
        assert!(endpoints
            .iter()
            .any(|endpoint| endpoint.port == 61688 && !endpoint.prefer_https));
        assert!(endpoints.iter().all(|endpoint| {
            endpoint.csrf.as_deref() == Some("1c22c3a4-bced-45e7-b6de-f3cf31a57494")
        }));
    }

    #[test]
    fn flag_value_reads_extension_port() {
        let line = r#"C:\Antigravity\language_server.exe --app_data_dir C:\Users\a\.gemini\antigravity --extension_server_port 41234 --csrf_token abcdef"#;
        assert_eq!(
            flag_value(line, "extension_server_port").as_deref(),
            Some("41234")
        );
    }
}

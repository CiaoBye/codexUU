//! Antigravity conversation database reader.
//!
//! Antigravity stores generation usage in SQLite `gen_metadata.data` as a
//! protobuf message. It is deliberately not parsed as UTF-8 text: model names
//! may occasionally be visible in the blob, but token counts are binary wire
//! values. The field mapping follows the same reverse-engineered schema used by
//! tokscale and is kept small so the desktop app does not need a protobuf code
//! generator or another runtime dependency.

use std::collections::{HashMap, HashSet};
use std::path::Path;

use rusqlite::{Connection, OpenFlags};

use crate::models::TokenBreakdown;

#[derive(Debug, Clone)]
pub struct DbGeneration {
    pub model_id: String,
    pub timestamp_ms: i64,
    pub tokens: TokenBreakdown,
    pub response_id: Option<String>,
}

#[derive(Debug, Clone, Default)]
pub struct ParsedDbSession {
    pub generations: Vec<DbGeneration>,
    pub session_timestamp_ms: i64,
    pub workspace_path: Option<String>,
    pub database_opened: bool,
    pub rows_scanned: usize,
    pub decoded_rows: usize,
    pub malformed_rows: usize,
}

#[derive(Debug, Clone)]
struct RawGeneration {
    model_id: Option<String>,
    display_model: Option<String>,
    timestamp_ms: Option<i64>,
    tokens: TokenBreakdown,
    response_id: Option<String>,
}

/// Parse one Antigravity conversation database in read-only mode.
pub fn parse_file(path: &Path) -> ParsedDbSession {
    let mut parsed = ParsedDbSession::default();
    let Ok(connection) = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY) else {
        return parsed;
    };
    parsed.database_opened = true;

    let (session_timestamp_ms, workspace_path) = read_trajectory_metadata(&connection, path);
    parsed.session_timestamp_ms = session_timestamp_ms;
    parsed.workspace_path = workspace_path;

    let mut statement = match connection.prepare("SELECT data FROM gen_metadata ORDER BY idx") {
        Ok(statement) => statement,
        Err(_) => return parsed,
    };
    let rows = match statement.query_map([], |row| row.get::<_, Vec<u8>>(0)) {
        Ok(rows) => rows,
        Err(_) => return parsed,
    };
    let blobs: Vec<Vec<u8>> = rows.flatten().collect();
    parsed.rows_scanned = blobs.len();

    // Some continuation rows omit the machine model (#19) but keep the
    // display label (#21). Recover the machine model from sibling rows in the
    // same conversation, never from a localized display label.
    let mut models_by_display: HashMap<String, HashSet<String>> = HashMap::new();
    let mut all_models = HashSet::new();
    let mut raw_rows = Vec::with_capacity(blobs.len());
    for blob in &blobs {
        let Some(raw) = parse_raw_generation(blob) else {
            parsed.malformed_rows += 1;
            continue;
        };
        parsed.decoded_rows += 1;
        if let (Some(display), Some(model)) = (&raw.display_model, &raw.model_id) {
            models_by_display
                .entry(display.clone())
                .or_default()
                .insert(model.clone());
        }
        if let Some(model) = &raw.model_id {
            all_models.insert(model.clone());
        }
        raw_rows.push(raw);
    }

    let sole_model = (all_models.len() == 1)
        .then(|| all_models.into_iter().next())
        .flatten();
    let mut seen_response_ids = HashSet::new();

    for raw in raw_rows {
        if raw.tokens.total == 0 {
            continue;
        }
        if let Some(response_id) = &raw.response_id {
            if !seen_response_ids.insert(response_id.clone()) {
                continue;
            }
        }

        let recovered_model = raw
            .display_model
            .as_ref()
            .and_then(|display| models_by_display.get(display))
            .filter(|models| models.len() == 1)
            .and_then(|models| models.iter().next())
            .cloned()
            .or(sole_model.clone());
        let model_id = raw
            .model_id
            .or(recovered_model)
            .unwrap_or_else(|| "unknown".to_string());

        parsed.generations.push(DbGeneration {
            model_id,
            timestamp_ms: raw
                .timestamp_ms
                .filter(|timestamp| *timestamp > 0)
                .unwrap_or(0),
            tokens: raw.tokens,
            response_id: raw.response_id,
        });
    }

    fill_missing_generation_timestamps(
        &mut parsed.generations,
        parsed.session_timestamp_ms,
        file_modified_ms(path),
    );

    parsed
}

fn fill_missing_generation_timestamps(
    generations: &mut [DbGeneration],
    session_timestamp_ms: i64,
    file_mtime_ms: i64,
) {
    let last_valid_index = generations
        .iter()
        .rposition(|generation| generation.timestamp_ms > 0);
    let mut carry = session_timestamp_ms.max(0);
    for (index, generation) in generations.iter_mut().enumerate() {
        if generation.timestamp_ms > 0 {
            carry = generation.timestamp_ms;
            continue;
        }
        let trailing = last_valid_index
            .map(|valid_index| index > valid_index)
            .unwrap_or(true);
        generation.timestamp_ms = if trailing && file_mtime_ms > carry {
            file_mtime_ms
        } else {
            carry
        };
    }
}

fn parse_raw_generation(blob: &[u8]) -> Option<RawGeneration> {
    let chat_model = message_field(blob, 1)?;
    let usage = message_field(chat_model, 4)?;

    // #1 is the fixed system prompt, #2 is newly processed input, #5 is the
    // cached prefix, #9 is output text and #10 is thinking/reasoning output.
    let input = varint_field(usage, 1)
        .unwrap_or(0)
        .saturating_add(varint_field(usage, 2).unwrap_or(0));
    let cache_read = varint_field(usage, 5).unwrap_or(0);
    let output = varint_field(usage, 9).unwrap_or(0);
    let reasoning = varint_field(usage, 10).unwrap_or(0);

    Some(RawGeneration {
        model_id: non_empty_string_field(chat_model, 19).map(str::to_string),
        display_model: non_empty_string_field(chat_model, 21).map(str::to_string),
        timestamp_ms: message_field(chat_model, 9)
            .and_then(|generation| message_field(generation, 4))
            .and_then(proto_timestamp_ms),
        tokens: TokenBreakdown::new(input, cache_read, output.saturating_add(reasoning)),
        response_id: non_empty_string_field(usage, 11).map(str::to_string),
    })
}

fn read_trajectory_metadata(connection: &Connection, path: &Path) -> (i64, Option<String>) {
    let blob: Option<Vec<u8>> = connection
        .query_row(
            "SELECT data FROM trajectory_metadata_blob LIMIT 1",
            [],
            |row| row.get::<_, Vec<u8>>(0),
        )
        .ok();

    let timestamp_ms = blob
        .as_deref()
        .and_then(|value| message_field(value, 2))
        .and_then(proto_timestamp_ms)
        .filter(|timestamp| *timestamp > 0)
        .unwrap_or_else(|| file_modified_ms(path));

    let workspace_path = blob
        .as_deref()
        .and_then(|value| message_field(value, 1))
        .and_then(|folder| string_field(folder, 1))
        .and_then(file_uri_to_path);

    (timestamp_ms, workspace_path)
}

fn file_modified_ms(path: &Path) -> i64 {
    std::fs::metadata(path)
        .and_then(|metadata| metadata.modified())
        .ok()
        .map(|time| chrono::DateTime::<chrono::Utc>::from(time).timestamp_millis())
        .unwrap_or(0)
}

fn file_uri_to_path(uri: &str) -> Option<String> {
    let decoded = percent_decode(uri.strip_prefix("file://")?)?;
    if let Some(stripped) = decoded.strip_prefix('/') {
        // file:///C:/workspace -> C:/workspace on Windows. POSIX paths keep
        // their leading slash; UNC authorities are restored below.
        if decoded.as_bytes().get(2) == Some(&b':') {
            Some(stripped.to_string())
        } else {
            Some(decoded)
        }
    } else {
        Some(format!("//{decoded}"))
    }
}

fn percent_decode(value: &str) -> Option<String> {
    let bytes = value.as_bytes();
    let mut decoded = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] == b'%' {
            let high = bytes.get(index + 1).and_then(|byte| hex_value(*byte))?;
            let low = bytes.get(index + 2).and_then(|byte| hex_value(*byte))?;
            decoded.push((high << 4) | low);
            index += 3;
        } else {
            decoded.push(bytes[index]);
            index += 1;
        }
    }
    String::from_utf8(decoded).ok()
}

fn hex_value(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        b'A'..=b'F' => Some(byte - b'A' + 10),
        _ => None,
    }
}

fn proto_timestamp_ms(timestamp: &[u8]) -> Option<i64> {
    let seconds = i64::try_from(varint_field(timestamp, 1)?).ok()?;
    let nanos = i64::try_from(varint_field(timestamp, 2).unwrap_or(0)).ok()?;
    if seconds <= 0 || !(0..=999_999_999).contains(&nanos) {
        return None;
    }
    seconds.checked_mul(1_000)?.checked_add(nanos / 1_000_000)
}

enum Wire<'a> {
    Varint(u64),
    LengthDelimited(&'a [u8]),
    Fixed32,
    Fixed64,
}

struct ProtoReader<'a> {
    buffer: &'a [u8],
    position: usize,
}

impl<'a> ProtoReader<'a> {
    fn new(buffer: &'a [u8]) -> Self {
        Self {
            buffer,
            position: 0,
        }
    }

    fn read_varint(&mut self) -> Option<u64> {
        let mut value = 0u64;
        let mut shift = 0u32;
        loop {
            if shift >= 64 {
                return None;
            }
            let byte = *self.buffer.get(self.position)?;
            self.position += 1;
            let part = u64::from(byte & 0x7f);
            if shift == 63 && part > 1 {
                return None;
            }
            value |= part << shift;
            if byte & 0x80 == 0 {
                return Some(value);
            }
            shift += 7;
        }
    }

    fn next_field(&mut self) -> Option<(u64, Wire<'a>)> {
        if self.position >= self.buffer.len() {
            return None;
        }
        let tag = self.read_varint()?;
        let field = tag >> 3;
        let wire = match tag & 0x7 {
            0 => Wire::Varint(self.read_varint()?),
            1 => {
                self.position = self.position.checked_add(8)?;
                if self.position > self.buffer.len() {
                    return None;
                }
                Wire::Fixed64
            }
            2 => {
                let length = usize::try_from(self.read_varint()?).ok()?;
                let end = self.position.checked_add(length)?;
                if end > self.buffer.len() {
                    return None;
                }
                let value = &self.buffer[self.position..end];
                self.position = end;
                Wire::LengthDelimited(value)
            }
            5 => {
                self.position = self.position.checked_add(4)?;
                if self.position > self.buffer.len() {
                    return None;
                }
                Wire::Fixed32
            }
            _ => return None,
        };
        Some((field, wire))
    }
}

fn message_field(buffer: &[u8], field: u64) -> Option<&[u8]> {
    let mut reader = ProtoReader::new(buffer);
    while let Some((candidate, value)) = reader.next_field() {
        if candidate == field {
            if let Wire::LengthDelimited(bytes) = value {
                return Some(bytes);
            }
        }
    }
    None
}

fn varint_field(buffer: &[u8], field: u64) -> Option<u64> {
    let mut reader = ProtoReader::new(buffer);
    while let Some((candidate, value)) = reader.next_field() {
        if candidate == field {
            if let Wire::Varint(number) = value {
                return Some(number);
            }
        }
    }
    None
}

fn string_field(buffer: &[u8], field: u64) -> Option<&str> {
    message_field(buffer, field).and_then(|bytes| std::str::from_utf8(bytes).ok())
}

fn non_empty_string_field(buffer: &[u8], field: u64) -> Option<&str> {
    string_field(buffer, field).filter(|value| !value.trim().is_empty())
}

#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::{params, Connection};

    struct TestDirectory(std::path::PathBuf);

    impl TestDirectory {
        fn new(label: &str) -> Self {
            let suffix = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            let path = std::env::temp_dir().join(format!(
                "codexuu-antigravity-{label}-{}-{suffix}",
                std::process::id()
            ));
            std::fs::create_dir_all(&path).unwrap();
            Self(path)
        }

        fn path(&self) -> &Path {
            &self.0
        }
    }

    impl Drop for TestDirectory {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    fn encode_varint(mut value: u64) -> Vec<u8> {
        let mut bytes = Vec::new();
        loop {
            let mut byte = (value & 0x7f) as u8;
            value >>= 7;
            if value != 0 {
                byte |= 0x80;
            }
            bytes.push(byte);
            if value == 0 {
                return bytes;
            }
        }
    }

    fn encode_varint_field(field: u64, value: u64) -> Vec<u8> {
        let mut bytes = encode_varint(field << 3);
        bytes.extend(encode_varint(value));
        bytes
    }

    fn encode_message_field(field: u64, value: &[u8]) -> Vec<u8> {
        let mut bytes = encode_varint((field << 3) | 2);
        bytes.extend(encode_varint(value.len() as u64));
        bytes.extend(value);
        bytes
    }

    fn build_generation() -> Vec<u8> {
        let usage = [
            encode_varint_field(1, 1_132),
            encode_varint_field(2, 500),
            encode_varint_field(5, 16_000),
            encode_varint_field(9, 300),
            encode_varint_field(10, 40),
            encode_message_field(11, b"response-1"),
        ]
        .concat();
        let timestamp = [
            encode_varint_field(1, 1_781_502_653),
            encode_varint_field(2, 0),
        ]
        .concat();
        let generation = encode_message_field(4, &timestamp);
        let chat_model = [
            encode_message_field(4, &usage),
            encode_message_field(9, &generation),
            encode_message_field(19, b"gemini-3-flash-a"),
            encode_message_field(21, b"Gemini 3 Flash"),
        ]
        .concat();
        encode_message_field(1, &chat_model)
    }

    #[test]
    fn parses_tokens_timestamp_and_workspace_from_sqlite() {
        let directory = TestDirectory::new("parse");
        let path = directory.path().join("session.db");
        let connection = Connection::open(&path).unwrap();
        connection
            .execute_batch(
                "CREATE TABLE gen_metadata (idx INTEGER, data BLOB, size INTEGER);
                 CREATE TABLE trajectory_metadata_blob (id TEXT, data BLOB);",
            )
            .unwrap();
        let workspace_uri = encode_message_field(1, b"file:///C:/Users/Ayuan/Project%20A");
        let workspace = encode_message_field(1, &workspace_uri);
        let created = encode_message_field(
            2,
            &[
                encode_varint_field(1, 1_781_502_000),
                encode_varint_field(2, 0),
            ]
            .concat(),
        );
        connection
            .execute(
                "INSERT INTO gen_metadata (idx, data, size) VALUES (0, ?1, 0)",
                params![build_generation()],
            )
            .unwrap();
        connection
            .execute(
                "INSERT INTO trajectory_metadata_blob (id, data) VALUES ('main', ?1)",
                params![[workspace, created].concat()],
            )
            .unwrap();
        drop(connection);

        let parsed = parse_file(&path);
        assert_eq!(parsed.rows_scanned, 1);
        assert_eq!(parsed.generations.len(), 1);
        assert_eq!(parsed.generations[0].tokens.uncached_input, 1_632);
        assert_eq!(parsed.generations[0].tokens.cached_input, 16_000);
        assert_eq!(parsed.generations[0].tokens.output, 340);
        assert_eq!(parsed.generations[0].timestamp_ms, 1_781_502_653_000);
        assert_eq!(
            parsed.workspace_path.as_deref(),
            Some("C:/Users/Ayuan/Project A")
        );
    }

    #[test]
    fn ignores_duplicate_response_ids() {
        let directory = TestDirectory::new("dedupe");
        let path = directory.path().join("duplicates.db");
        let connection = Connection::open(&path).unwrap();
        connection
            .execute_batch(
                "CREATE TABLE gen_metadata (idx INTEGER, data BLOB, size INTEGER);
                 CREATE TABLE trajectory_metadata_blob (id TEXT, data BLOB);",
            )
            .unwrap();
        let row = build_generation();
        connection
            .execute(
                "INSERT INTO gen_metadata (idx, data, size) VALUES (0, ?1, 0)",
                params![row.clone()],
            )
            .unwrap();
        connection
            .execute(
                "INSERT INTO gen_metadata (idx, data, size) VALUES (1, ?1, 0)",
                params![row],
            )
            .unwrap();
        drop(connection);

        assert_eq!(parse_file(&path).generations.len(), 1);
    }

    fn generation(timestamp_ms: i64) -> DbGeneration {
        DbGeneration {
            model_id: "gemini-3-flash-a".to_string(),
            timestamp_ms,
            tokens: TokenBreakdown::default(),
            response_id: None,
        }
    }

    #[test]
    fn trailing_missing_timestamps_use_newer_file_mtime() {
        let mut generations = vec![generation(1_781_600_000_000), generation(0)];
        fill_missing_generation_timestamps(&mut generations, 1_781_500_000_000, 1_781_700_000_000);
        assert_eq!(generations[0].timestamp_ms, 1_781_600_000_000);
        assert_eq!(generations[1].timestamp_ms, 1_781_700_000_000);
    }

    #[test]
    fn middle_missing_timestamps_carry_forward() {
        let mut generations = vec![
            generation(1_781_600_000_000),
            generation(0),
            generation(1_781_650_000_000),
        ];
        fill_missing_generation_timestamps(&mut generations, 1_781_500_000_000, 1_781_700_000_000);
        assert_eq!(generations[1].timestamp_ms, 1_781_600_000_000);
    }

    #[test]
    fn zero_proto_timestamp_is_rejected() {
        let timestamp = encode_varint_field(1, 0);
        assert_eq!(proto_timestamp_ms(&timestamp), None);
    }
}

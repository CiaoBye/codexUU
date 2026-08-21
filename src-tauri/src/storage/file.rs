use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Mutex, OnceLock};

/// Replaces a generated JSON file on platforms where rename does not
/// overwrite an existing destination, notably Windows.
pub fn replace(temp: &Path, destination: &Path) -> Result<(), String> {
    match fs::rename(temp, destination) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
            #[cfg(windows)]
            {
                replace_windows(temp, destination)
            }
            #[cfg(not(windows))]
            {
                fs::rename(temp, destination)
                    .map_err(|rename_error| format!("提交新文件失败：{rename_error}"))
            }
        }
        Err(error) => Err(format!("提交新文件失败：{error}")),
    }
}

/// Windows' standard rename refuses to replace an existing file.  Removing
/// the destination first creates a crash window where the old configuration
/// is gone.  ReplaceFileW performs the replacement as one filesystem commit,
/// preserving the old file until the new file is ready.
#[cfg(windows)]
fn replace_windows(temp: &Path, destination: &Path) -> Result<(), String> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{ReplaceFileW, REPLACEFILE_WRITE_THROUGH};

    let destination_w: Vec<u16> = destination.as_os_str().encode_wide().chain([0]).collect();
    let temp_w: Vec<u16> = temp.as_os_str().encode_wide().chain([0]).collect();
    let replaced = unsafe {
        ReplaceFileW(
            destination_w.as_ptr(),
            temp_w.as_ptr(),
            std::ptr::null(),
            REPLACEFILE_WRITE_THROUGH,
            std::ptr::null(),
            std::ptr::null(),
        )
    };
    if replaced == 0 {
        Err(format!(
            "提交新文件失败：{}",
            std::io::Error::last_os_error()
        ))
    } else {
        Ok(())
    }
}

fn write_guard() -> &'static Mutex<()> {
    static GUARD: OnceLock<Mutex<()>> = OnceLock::new();
    GUARD.get_or_init(|| Mutex::new(()))
}

/// Builds a unique temp path in the same directory as `destination` so that
/// parallel writers (even across threads) never clobber each other's temp
/// file. The sequence number plus the process id guarantee uniqueness.
fn unique_temp_path(destination: &Path) -> PathBuf {
    static SEQUENCE: AtomicU64 = AtomicU64::new(0);
    let sequence = SEQUENCE.fetch_add(1, Ordering::Relaxed);
    let file_name = destination
        .file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_else(|| "out".to_string());
    destination.with_file_name(format!(
        ".{}.{}.{}.tmp",
        file_name,
        std::process::id(),
        sequence,
    ))
}

/// Atomically writes `content` to `destination` through a unique temp file
/// that is serialized in-process against concurrent writers, then committed by
/// [`replace`]. This replaces the old fixed-`.json.tmp` scheme whose single
/// temp path was shared by the main window and the widget, allowing one
/// writer to overwrite another's in-flight temp file.
pub fn write_atomic(destination: &Path, content: &str) -> Result<(), String> {
    let _guard = write_guard()
        .lock()
        .map_err(|_| "文件写入锁被污染".to_string())?;
    let temp = unique_temp_path(destination);
    fs::write(&temp, content).map_err(|error| format!("写入临时文件失败：{error}"))?;
    replace(&temp, destination)
}

#[cfg(test)]
mod tests {
    use super::{replace, write_atomic};
    use std::fs;

    #[test]
    fn replace_overwrites_an_existing_generated_file() {
        let root =
            std::env::temp_dir().join(format!("codexuu-file-replace-{}", std::process::id()));
        fs::create_dir_all(&root).expect("create test directory");
        let destination = root.join("settings.json");
        let temp = root.join("settings.json.tmp");
        fs::write(&destination, "old").expect("write destination");
        fs::write(&temp, "new").expect("write temp");

        replace(&temp, &destination).expect("replace file");

        assert_eq!(
            fs::read_to_string(&destination).expect("read destination"),
            "new"
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn write_atomic_commits_content_and_leaves_no_temp_litter() {
        let root = std::env::temp_dir().join(format!("codexuu-file-atomic-{}", std::process::id()));
        fs::create_dir_all(&root).expect("create test directory");
        let destination = root.join("history-v2.json");

        write_atomic(&destination, "first").expect("first atomic write");
        write_atomic(&destination, "second").expect("second atomic write");

        assert_eq!(
            fs::read_to_string(&destination).expect("read destination"),
            "second"
        );
        // No fixed temp files may remain behind after a successful write.
        let leftovers: Vec<_> = fs::read_dir(&root)
            .expect("read test directory")
            .flatten()
            .filter(|entry| entry.file_name().to_string_lossy().contains(".tmp"))
            .collect();
        assert!(leftovers.is_empty(), "temp files leaked: {leftovers:?}");
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn concurrent_atomic_writes_are_serialized_and_valid() {
        let root =
            std::env::temp_dir().join(format!("codexuu-file-atomic-conc-{}", std::process::id()));
        fs::create_dir_all(&root).expect("create test directory");
        let destination = root.join("cache.json");
        let handles: Vec<_> = (0..16)
            .map(|i| {
                let destination = destination.clone();
                std::thread::spawn(move || {
                    write_atomic(&destination, &i.to_string()).expect("write")
                })
            })
            .collect();
        for handle in handles {
            handle.join().expect("writer thread");
        }
        // A serialized writer must always leave a complete, valid value.
        let value = fs::read_to_string(&destination).expect("read destination");
        value
            .parse::<u16>()
            .expect("last write must be a complete integer");
        let _ = fs::remove_dir_all(root);
    }
}

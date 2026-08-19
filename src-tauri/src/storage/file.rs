use std::fs;
use std::path::Path;

/// Replaces a generated JSON file on platforms where rename does not
/// overwrite an existing destination, notably Windows.
pub fn replace(temp: &Path, destination: &Path) -> Result<(), String> {
    match fs::rename(temp, destination) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
            fs::remove_file(destination)
                .map_err(|remove_error| format!("替换旧文件失败：{remove_error}"))?;
            fs::rename(temp, destination)
                .map_err(|rename_error| format!("提交新文件失败：{rename_error}"))
        }
        Err(error) => Err(format!("提交新文件失败：{error}")),
    }
}

#[cfg(test)]
mod tests {
    use super::replace;
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
}

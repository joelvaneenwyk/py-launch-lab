//! Executable resolution for pyshim-win.
//!
//! Locates the target executable on PATH, applying Windows-specific rules
//! (e.g. preferring `pythonw.exe` when `--hide-console` is active).

use std::env;
use std::path::PathBuf;

/// Known interpreters and their GUI-subsystem counterparts.
///
/// When `--hide-console` is active the shim will try the GUI variant first.
/// `uvw` is a project-specific GUI-subsystem build of `uv` (see M3 scenarios).
const GUI_ALTERNATIVES: &[(&str, &str)] = &[
    ("python", "pythonw"),
    ("python3", "pythonw"),
    ("uv", "uvw"),
];

/// Resolve the first element of `command` to an absolute executable path.
///
/// When `hide_console` is true and the target has a known GUI counterpart
/// (e.g. `python` → `pythonw`), the GUI variant is tried first.
///
/// Returns `None` if the executable cannot be found.
pub fn resolve_target(command: &[String], hide_console: bool) -> Option<String> {
    if command.is_empty() {
        return None;
    }
    let name = &command[0];

    // If hide_console is active, try the GUI variant first.
    if hide_console {
        if let Some(gui_name) = gui_alternative(name) {
            if let Some(path) = which(&gui_name) {
                return Some(path.to_string_lossy().into_owned());
            }
        }
    }

    which(name).map(|p| p.to_string_lossy().into_owned())
}

/// Return the GUI-subsystem alternative for a given interpreter name, if any.
fn gui_alternative(name: &str) -> Option<String> {
    // Normalise: strip .exe suffix for comparison.
    let base = name
        .strip_suffix(".exe")
        .or_else(|| name.strip_suffix(".EXE"))
        .unwrap_or(name)
        .to_lowercase();
    for &(console, gui) in GUI_ALTERNATIVES {
        if base == console {
            return Some(gui.to_string());
        }
    }
    None
}

/// Walk PATH to locate an executable file.
///
/// Uses `env::split_paths` (handles non-UTF-8 entries correctly) and
/// validates that the candidate is a regular file.  On Unix the
/// executable permission bit is also checked.
fn which(name: &str) -> Option<PathBuf> {
    // If the name is already an absolute path and is an executable file, return it.
    let p = PathBuf::from(name);
    if p.is_absolute() && is_executable_file(&p) {
        return Some(p);
    }

    let path_val = env::var_os("PATH")?;

    for dir in env::split_paths(&path_val) {
        let candidate = dir.join(name);
        if is_executable_file(&candidate) {
            return Some(candidate);
        }
        // Try with .exe on Windows.
        #[cfg(target_os = "windows")]
        {
            let with_ext = dir.join(format!("{}.exe", name));
            if is_executable_file(&with_ext) {
                return Some(with_ext);
            }
        }
    }
    None
}

/// Check that `path` is a regular file (not a directory or symlink to a
/// directory) and, on Unix, has the executable permission bit set.
fn is_executable_file(path: &std::path::Path) -> bool {
    if !path.is_file() {
        return false;
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if let Ok(meta) = path.metadata() {
            return meta.permissions().mode() & 0o111 != 0;
        }
        return false;
    }
    #[cfg(not(unix))]
    {
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_resolve_empty_command() {
        assert!(resolve_target(&[], false).is_none());
    }

    #[test]
    fn test_gui_alternative_python() {
        assert_eq!(gui_alternative("python"), Some("pythonw".to_string()));
        assert_eq!(gui_alternative("Python"), Some("pythonw".to_string()));
    }

    #[test]
    fn test_gui_alternative_python_exe() {
        assert_eq!(gui_alternative("python.exe"), Some("pythonw".to_string()));
    }

    #[test]
    fn test_gui_alternative_uv() {
        assert_eq!(gui_alternative("uv"), Some("uvw".to_string()));
    }

    #[test]
    fn test_gui_alternative_unknown() {
        assert_eq!(gui_alternative("node"), None);
    }

    #[test]
    fn test_resolve_nonexistent_command() {
        let cmd = vec!["__nonexistent_binary_xyz__".to_string()];
        assert!(resolve_target(&cmd, false).is_none());
    }
}

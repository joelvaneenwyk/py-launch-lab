//! Executable resolution for pyshim-win.
//!
//! Locates the target executable on PATH, applying Windows-specific rules
//! (e.g. preferring `pythonw.exe` when `--hide-console` is active).
//!
//! TODO(M4): Implement full resolution logic.

use std::env;
use std::path::PathBuf;

/// Resolve the first element of `command` to an absolute executable path.
///
/// Returns `None` if the executable cannot be found.
pub fn resolve_target(command: &[String]) -> Option<String> {
    if command.is_empty() {
        return None;
    }
    let name = &command[0];
    // TODO(M4): Apply Windows-specific resolution:
    //   - If name is "python" and hide_console is active, prefer "pythonw"
    //   - Search PATH with .exe extension on Windows
    which(name).map(|p| p.to_string_lossy().into_owned())
}

fn which(name: &str) -> Option<PathBuf> {
    // Simple PATH walk — replace with the `which` crate in M4.
    let path_val = env::var_os("PATH")?;
    let path_str = path_val.to_str()?;

    // Use the platform-appropriate separator.
    #[cfg(target_os = "windows")]
    let separator = ';';
    #[cfg(not(target_os = "windows"))]
    let separator = ':';

    for dir in path_str.split(separator).filter(|s| !s.is_empty()) {
        let candidate = PathBuf::from(dir).join(name);
        if candidate.exists() {
            return Some(candidate);
        }
        // Try with .exe on Windows
        #[cfg(target_os = "windows")]
        {
            let with_ext = PathBuf::from(dir).join(format!("{}.exe", name));
            if with_ext.exists() {
                return Some(with_ext);
            }
        }
    }
    None
}

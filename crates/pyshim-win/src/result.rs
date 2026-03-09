//! Result model and emitter for pyshim-win.

use crate::detect::Subsystem;
use serde::Serialize;

/// Structured result emitted by pyshim-win after launching a child process.
#[derive(Debug, Serialize)]
pub struct LaunchResult {
    pub exit_code: Option<i32>,
    pub resolved_executable: Option<String>,
    pub hide_console: bool,
    pub detected_subsystem: Option<Subsystem>,
    pub error: Option<String>,
}

/// Emit the result as JSON to stdout.
///
/// If stdout is unavailable (GUI subsystem without an attached console),
/// the result is written to a temp file instead.
pub fn emit(result: &LaunchResult) {
    if let Ok(json) = serde_json::to_string_pretty(result) {
        // Attempt to print; ignore errors (stdout may not be available in GUI mode).
        let _ = println!("{}", json);
    }
}

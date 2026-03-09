//! Child process launcher for pyshim-win.
//!
//! TODO(M4): Replace stub with real CreateProcess call using Windows API.

use crate::cli::Args;
use crate::result::LaunchResult;

/// Launch the target command as a child process.
///
/// On Windows this will use `CreateProcess` with appropriate `dwCreationFlags`
/// to control console visibility.  The stub below falls back to `std::process::Command`.
pub fn launch(args: &Args, resolved: Option<&str>) -> LaunchResult {
    let exe = match resolved {
        Some(r) => r.to_string(),
        None => {
            return LaunchResult {
                exit_code: Some(127),
                resolved_executable: None,
                hide_console: args.hide_console,
                error: Some("Could not resolve target executable".to_string()),
            };
        }
    };

    let child_args = if args.command.len() > 1 {
        &args.command[1..]
    } else {
        &[][..]
    };

    // TODO(M4): On Windows, use CreateProcess with CREATE_NO_WINDOW when
    //           hide_console is true.  For now use std::process::Command as
    //           a cross-platform stub.
    let status = std::process::Command::new(&exe)
        .args(child_args)
        .status();

    match status {
        Ok(s) => LaunchResult {
            exit_code: s.code(),
            resolved_executable: Some(exe),
            hide_console: args.hide_console,
            error: None,
        },
        Err(e) => LaunchResult {
            exit_code: Some(1),
            resolved_executable: Some(exe),
            hide_console: args.hide_console,
            error: Some(e.to_string()),
        },
    }
}

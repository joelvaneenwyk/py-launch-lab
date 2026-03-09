//! Child process launcher for pyshim-win.
//!
//! On Windows, uses `CreateProcessW` with appropriate `dwCreationFlags` to
//! control console visibility.  On other platforms, falls back to
//! `std::process::Command`.

use crate::cli::Args;
use crate::detect::Subsystem;
use crate::result::LaunchResult;

/// Launch the target command as a child process.
pub fn launch(
    args: &Args,
    resolved: Option<&str>,
    detected_subsystem: Option<&Subsystem>,
) -> LaunchResult {
    let exe = match resolved {
        Some(r) => r.to_string(),
        None => {
            return LaunchResult {
                exit_code: Some(127),
                resolved_executable: None,
                hide_console: args.hide_console,
                detected_subsystem: detected_subsystem.cloned(),
                error: Some("Could not resolve target executable".to_string()),
            };
        }
    };

    let child_args: Vec<&str> = if args.command.len() > 1 {
        args.command[1..].iter().map(|s| s.as_str()).collect()
    } else {
        vec![]
    };

    let result = launch_impl(&exe, &child_args, args.hide_console);

    LaunchResult {
        exit_code: result.0,
        resolved_executable: Some(exe),
        hide_console: args.hide_console,
        detected_subsystem: detected_subsystem.cloned(),
        error: result.1,
    }
}

/// Platform-specific launch implementation.
///
/// Returns (exit_code, error).
#[cfg(windows)]
fn launch_impl(exe: &str, args: &[&str], hide_console: bool) -> (Option<i32>, Option<String>) {
    use std::ffi::OsStr;
    use std::iter::once;
    use std::os::windows::ffi::OsStrExt;

    use windows_sys::Win32::Foundation::{CloseHandle, INVALID_HANDLE_VALUE, WAIT_FAILED};
    use windows_sys::Win32::System::Console::{
        GetStdHandle, STD_INPUT_HANDLE, STD_OUTPUT_HANDLE, STD_ERROR_HANDLE,
    };
    use windows_sys::Win32::System::Threading::{
        CreateProcessW, GetExitCodeProcess, WaitForSingleObject,
        PROCESS_INFORMATION, STARTUPINFOW,
        CREATE_NO_WINDOW, INFINITE, STARTF_USESTDHANDLES,
    };

    // Build the command line as a single wide string (Windows convention).
    let mut cmdline_str = quote_arg(exe);
    for arg in args {
        cmdline_str.push(' ');
        cmdline_str.push_str(&quote_arg(arg));
    }
    let mut cmdline_wide: Vec<u16> = OsStr::new(&cmdline_str)
        .encode_wide()
        .chain(once(0))
        .collect();

    let creation_flags: u32 = if hide_console { CREATE_NO_WINDOW } else { 0 };

    // Retrieve the parent's standard handles so the child can inherit them.
    let h_stdin = unsafe { GetStdHandle(STD_INPUT_HANDLE) };
    let h_stdout = unsafe { GetStdHandle(STD_OUTPUT_HANDLE) };
    let h_stderr = unsafe { GetStdHandle(STD_ERROR_HANDLE) };

    let mut si: STARTUPINFOW = unsafe { std::mem::zeroed() };
    si.cb = std::mem::size_of::<STARTUPINFOW>() as u32;

    // Wire standard handles into the child so it can read/write the
    // parent's console streams (matching the non-Windows Command fallback).
    if h_stdin != INVALID_HANDLE_VALUE as isize
        && h_stdout != INVALID_HANDLE_VALUE as isize
        && h_stderr != INVALID_HANDLE_VALUE as isize
    {
        si.dwFlags |= STARTF_USESTDHANDLES;
        si.hStdInput = h_stdin as _;
        si.hStdOutput = h_stdout as _;
        si.hStdError = h_stderr as _;
    }

    let mut pi: PROCESS_INFORMATION = unsafe { std::mem::zeroed() };

    let ok = unsafe {
        CreateProcessW(
            std::ptr::null(),          // lpApplicationName
            cmdline_wide.as_mut_ptr(), // lpCommandLine
            std::ptr::null(),          // lpProcessAttributes
            std::ptr::null(),          // lpThreadAttributes
            1,                         // bInheritHandles (TRUE)
            creation_flags,            // dwCreationFlags
            std::ptr::null(),          // lpEnvironment
            std::ptr::null(),          // lpCurrentDirectory
            &si,                       // lpStartupInfo
            &mut pi,                   // lpProcessInformation
        )
    };

    if ok == 0 {
        let err = std::io::Error::last_os_error();
        return (Some(1), Some(format!("CreateProcessW failed: {}", err)));
    }

    // Wait for the child to exit.
    let wait = unsafe { WaitForSingleObject(pi.hProcess, INFINITE) };
    if wait == WAIT_FAILED {
        let err = std::io::Error::last_os_error();
        unsafe {
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
        }
        return (Some(1), Some(format!("WaitForSingleObject failed: {}", err)));
    }

    let mut exit_code: u32 = 1;
    unsafe {
        GetExitCodeProcess(pi.hProcess, &mut exit_code);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
    }

    (Some(exit_code as i32), None)
}

/// Fallback launch implementation for non-Windows platforms.
#[cfg(not(windows))]
fn launch_impl(exe: &str, args: &[&str], _hide_console: bool) -> (Option<i32>, Option<String>) {
    match std::process::Command::new(exe).args(args).status() {
        Ok(s) => (s.code(), None),
        Err(e) => (Some(1), Some(e.to_string())),
    }
}

/// Quote a command-line argument for Windows CreateProcess.
///
/// Implements the escaping algorithm documented in Microsoft's
/// "Parsing C Command-Line Arguments" reference: backslashes are
/// literal unless immediately followed by a double-quote.
#[cfg(windows)]
fn quote_arg(arg: &str) -> String {
    if arg.is_empty() {
        return "\"\"".to_string();
    }
    // If no special characters, return as-is.
    if !arg.contains(' ')
        && !arg.contains('\t')
        && !arg.contains('"')
        && !arg.contains('\\')
    {
        return arg.to_string();
    }

    let mut result = String::with_capacity(arg.len() + 4);
    result.push('"');
    let mut backslash_count = 0usize;

    for ch in arg.chars() {
        match ch {
            '\\' => {
                backslash_count += 1;
            }
            '"' => {
                // Double the backslashes before a quote, then escape the quote.
                for _ in 0..backslash_count * 2 + 1 {
                    result.push('\\');
                }
                result.push('"');
                backslash_count = 0;
            }
            _ => {
                // Flush pending backslashes literally.
                for _ in 0..backslash_count {
                    result.push('\\');
                }
                result.push(ch);
                backslash_count = 0;
            }
        }
    }

    // If the argument ends with backslashes, double them (they precede
    // the closing quote).
    for _ in 0..backslash_count * 2 {
        result.push('\\');
    }
    result.push('"');
    result
}

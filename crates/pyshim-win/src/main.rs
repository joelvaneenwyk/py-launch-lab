//! pyshim-win — Windows GUI-subsystem launcher shim for py-launch-lab.
//!
//! This binary is built as a GUI-subsystem executable so it never opens its
//! own console window.  It accepts a target command and launches it with
//! controlled console visibility.
//!
//! # Usage
//!
//! ```text
//! pyshim-win --hide-console -- python script.py
//! pyshim-win --hide-console -- uv run script.py
//! ```

mod cli;
mod detect;
mod launch;
mod resolve;
mod result;

use std::process;

fn main() {
    let args = cli::parse();

    // Resolve the target executable (respecting --hide-console preference).
    let resolved = resolve::resolve_target(&args.command, args.hide_console);

    // Detect subsystem of the resolved executable.
    let subsystem = detect::detect_subsystem(resolved.as_deref());

    // Launch the child process with appropriate creation flags.
    let launch_result = launch::launch(&args, resolved.as_deref(), subsystem.as_ref());

    // Emit the result as JSON to stdout.
    result::emit(&launch_result);

    process::exit(launch_result.exit_code.unwrap_or(1));
}

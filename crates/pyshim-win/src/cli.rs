//! CLI argument parsing for pyshim-win.

use clap::Parser;

/// pyshim-win — Windows GUI-subsystem launcher shim.
#[derive(Parser, Debug)]
#[command(name = "pyshim-win", version, about)]
pub struct Args {
    /// Launch the child with a hidden console window.
    #[arg(long)]
    pub hide_console: bool,

    /// The command to launch and its arguments (after `--`).
    #[arg(last = true, required = true)]
    pub command: Vec<String>,
}

pub fn parse() -> Args {
    Args::parse()
}

// build.rs — Set the Windows subsystem to GUI so pyshim-win never opens
// a console window of its own.
fn main() {
    // This only applies when building for Windows targets.
    #[cfg(target_os = "windows")]
    println!("cargo:rustc-link-arg=/SUBSYSTEM:WINDOWS");
    #[cfg(target_os = "windows")]
    println!("cargo:rustc-link-arg=/ENTRY:mainCRTStartup");
}

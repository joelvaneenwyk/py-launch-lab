//! Runtime subsystem detection for pyshim-win.
//!
//! TODO(M4): Read the PE header of a target executable to determine its
//! subsystem (GUI vs CUI) at runtime.

/// Subsystem classification for a Windows executable.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Subsystem {
    Gui,
    Cui,
    Unknown,
    NotPe,
}

/// Detect the PE subsystem of the executable at `path`.
///
/// Returns `None` if `path` is `None` or cannot be read.
///
/// TODO(M4): Implement by reading IMAGE_NT_HEADERS from the file.
pub fn detect_subsystem(path: Option<&str>) -> Option<Subsystem> {
    let _path = path?;
    // TODO(M4): Open file, read MZ header, seek to PE offset, read subsystem field.
    Some(Subsystem::Unknown)
}

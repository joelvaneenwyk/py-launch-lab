//! Runtime subsystem detection for pyshim-win.
//!
//! Reads the PE header of a target executable to determine its subsystem
//! (GUI vs CUI) at runtime.  Works cross-platform — it only reads bytes
//! from the file, no Windows API required.

use serde::Serialize;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;

/// PE constants.
const IMAGE_DOS_SIGNATURE: u16 = 0x5A4D; // 'MZ'
const IMAGE_NT_SIGNATURE: u32 = 0x0000_4550; // 'PE\0\0'
const IMAGE_SUBSYSTEM_WINDOWS_GUI: u16 = 2;
const IMAGE_SUBSYSTEM_WINDOWS_CUI: u16 = 3;
const PE32_MAGIC: u16 = 0x10B;
const PE32_PLUS_MAGIC: u16 = 0x20B;

/// Subsystem classification for a Windows executable.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub enum Subsystem {
    Gui,
    Cui,
    Unknown,
    NotPe,
}

impl std::fmt::Display for Subsystem {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Subsystem::Gui => write!(f, "GUI"),
            Subsystem::Cui => write!(f, "CUI"),
            Subsystem::Unknown => write!(f, "UNKNOWN"),
            Subsystem::NotPe => write!(f, "NOT_PE"),
        }
    }
}

/// Detect the PE subsystem of the executable at `path`.
///
/// Returns `None` if `path` is `None` or the file cannot be read.
pub fn detect_subsystem(path: Option<&str>) -> Option<Subsystem> {
    let path = path?;
    read_pe_subsystem(Path::new(path)).ok()
}

/// Read the PE subsystem field from a file.
fn read_pe_subsystem(path: &Path) -> Result<Subsystem, std::io::Error> {
    let mut f = File::open(path)?;
    let mut buf2 = [0u8; 2];
    let mut buf4 = [0u8; 4];

    // DOS header — check MZ signature
    f.read_exact(&mut buf2)?;
    let dos_sig = u16::from_le_bytes(buf2);
    if dos_sig != IMAGE_DOS_SIGNATURE {
        return Ok(Subsystem::NotPe);
    }

    // Offset to PE header is at 0x3C
    f.seek(SeekFrom::Start(0x3C))?;
    f.read_exact(&mut buf4)?;
    let pe_offset = u32::from_le_bytes(buf4) as u64;

    // PE signature
    f.seek(SeekFrom::Start(pe_offset))?;
    f.read_exact(&mut buf4)?;
    let pe_sig = u32::from_le_bytes(buf4);
    if pe_sig != IMAGE_NT_SIGNATURE {
        return Ok(Subsystem::NotPe);
    }

    // Skip COFF header (20 bytes) to reach the optional header
    let optional_header_start = pe_offset + 4 + 20;
    f.seek(SeekFrom::Start(optional_header_start))?;
    f.read_exact(&mut buf2)?;
    let magic = u16::from_le_bytes(buf2);

    // Subsystem is at offset 68 from start of optional header for both
    // PE32 (0x10B) and PE32+ (0x20B).
    if magic != PE32_MAGIC && magic != PE32_PLUS_MAGIC {
        return Ok(Subsystem::Unknown);
    }

    f.seek(SeekFrom::Start(optional_header_start + 68))?;
    f.read_exact(&mut buf2)?;
    let subsystem = u16::from_le_bytes(buf2);

    match subsystem {
        IMAGE_SUBSYSTEM_WINDOWS_GUI => Ok(Subsystem::Gui),
        IMAGE_SUBSYSTEM_WINDOWS_CUI => Ok(Subsystem::Cui),
        _ => Ok(Subsystem::Unknown),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    /// Build a minimal synthetic PE file with the given subsystem value.
    fn build_synthetic_pe(subsystem: u16, pe32_plus: bool) -> Vec<u8> {
        let mut buf = vec![0u8; 256];
        // DOS header: MZ signature
        buf[0] = 0x4D; // 'M'
        buf[1] = 0x5A; // 'Z'
        // PE offset at 0x3C → point to offset 0x80
        let pe_offset: u32 = 0x80;
        buf[0x3C..0x40].copy_from_slice(&pe_offset.to_le_bytes());
        // PE signature at offset 0x80
        buf[0x80..0x84].copy_from_slice(&IMAGE_NT_SIGNATURE.to_le_bytes());
        // Optional header magic at offset 0x80 + 4 + 20 = 0x98
        let magic = if pe32_plus { PE32_PLUS_MAGIC } else { PE32_MAGIC };
        buf[0x98..0x9A].copy_from_slice(&magic.to_le_bytes());
        // Subsystem at optional header start + 68 = 0x98 + 68 = 0xDC
        let sub_offset = 0x98 + 68;
        buf[sub_offset..sub_offset + 2].copy_from_slice(&subsystem.to_le_bytes());
        buf
    }

    #[test]
    fn test_detect_cui_pe32() {
        let data = build_synthetic_pe(IMAGE_SUBSYSTEM_WINDOWS_CUI, false);
        let dir = std::env::temp_dir().join("pyshim_test_detect");
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("test_cui_pe32.exe");
        File::create(&path).unwrap().write_all(&data).unwrap();
        assert_eq!(
            detect_subsystem(Some(path.to_str().unwrap())),
            Some(Subsystem::Cui)
        );
        std::fs::remove_file(&path).ok();
    }

    #[test]
    fn test_detect_gui_pe32_plus() {
        let data = build_synthetic_pe(IMAGE_SUBSYSTEM_WINDOWS_GUI, true);
        let dir = std::env::temp_dir().join("pyshim_test_detect");
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("test_gui_pe32p.exe");
        File::create(&path).unwrap().write_all(&data).unwrap();
        assert_eq!(
            detect_subsystem(Some(path.to_str().unwrap())),
            Some(Subsystem::Gui)
        );
        std::fs::remove_file(&path).ok();
    }

    #[test]
    fn test_detect_not_pe() {
        let dir = std::env::temp_dir().join("pyshim_test_detect");
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("test_not_pe.txt");
        File::create(&path)
            .unwrap()
            .write_all(b"not a PE file")
            .unwrap();
        assert_eq!(
            detect_subsystem(Some(path.to_str().unwrap())),
            Some(Subsystem::NotPe)
        );
        std::fs::remove_file(&path).ok();
    }

    #[test]
    fn test_detect_none_path() {
        assert_eq!(detect_subsystem(None), None);
    }

    #[test]
    fn test_detect_nonexistent() {
        assert_eq!(detect_subsystem(Some("/nonexistent/path.exe")), None);
    }
}

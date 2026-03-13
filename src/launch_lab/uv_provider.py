"""
Custom uv binary provider for py-launch-lab.

Supports three modes of providing a custom uv binary:

1. **Local binary path** — an existing uv executable (e.g. ``C:/builds/uv.exe``).
   When the path points to a file, the parent directory is used to resolve
   sibling binaries (``uvx``, ``uvw``).

2. **Local source directory** — a directory containing a Rust ``Cargo.toml``
   (e.g. a cloned uv repository).  The project is built with ``cargo build
   --release`` and the resulting binaries are used.

3. **Git URL** — a remote git repository (e.g.
   ``https://github.com/joelvaneenwyk/uv``).  The repo is cloned into
   ``.cache/custom_uv/<hash>/``, built with ``cargo build --release``, and the
   resulting binaries are used.

Usage::

    from launch_lab.uv_provider import setup_custom_uv, get_uv_binary

    # Call once at startup when --custom-uv is provided
    setup_custom_uv("https://github.com/joelvaneenwyk/uv")

    # Then anywhere a uv/uvx/uvw binary is needed:
    uv_path = get_uv_binary("uv")    # e.g. ".cache/custom_uv/.../target/release/uv.exe"
    uvx_path = get_uv_binary("uvx")
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CACHE_DIR = _PROJECT_ROOT / ".cache" / "custom_uv"
_IS_WINDOWS = sys.platform == "win32"
_EXE_SUFFIX = ".exe" if _IS_WINDOWS else ""

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_custom_uv_dir: Path | None = None
"""Directory containing custom uv/uvx/uvw binaries, or None for system default."""

_custom_uv_source: str | None = None
"""The original --custom-uv value for display purposes."""


def is_custom_uv_configured() -> bool:
    """Return True if a custom uv binary has been configured."""
    return _custom_uv_dir is not None


def get_custom_uv_source() -> str | None:
    """Return the original --custom-uv value, or None."""
    return _custom_uv_source


def get_uv_binary(name: str = "uv") -> str:
    """Return the path to a uv-family binary (``uv``, ``uvx``, ``uvw``).

    If a custom uv has been configured via :func:`setup_custom_uv`, the
    binary is resolved from the custom build/install directory.  Otherwise
    the bare binary name is returned (relying on PATH lookup).

    Parameters
    ----------
    name:
        The binary name — ``"uv"``, ``"uvx"``, or ``"uvw"``.
    """
    if _custom_uv_dir is not None:
        candidate = _custom_uv_dir / f"{name}{_EXE_SUFFIX}"
        if candidate.is_file():
            return str(candidate)
        # Fall back: some builds may only produce ``uv`` (uvx/uvw are
        # symlinks or multi-call), so try the directory anyway.
        logger.warning(
            "Custom uv dir %s has no %s binary; falling back to PATH", _custom_uv_dir, name
        )
    return name


def setup_custom_uv(source: str) -> str:
    """Resolve *source* to a directory of uv binaries and configure it globally.

    Parameters
    ----------
    source:
        One of:

        - Path to an existing ``uv`` binary file.
        - Path to a directory with ``Cargo.toml`` (Rust source tree).
        - A ``https://`` or ``git@`` git URL to clone and build.

    Returns
    -------
    str
        The resolved path to the ``uv`` binary.

    Raises
    ------
    RuntimeError
        If the source cannot be resolved or the build fails.
    """
    global _custom_uv_dir, _custom_uv_source  # noqa: PLW0603

    _custom_uv_source = source
    source_path = Path(source)

    if _is_git_url(source):
        _custom_uv_dir = _resolve_git_source(source)
    elif source_path.is_file():
        _custom_uv_dir = _resolve_binary_path(source_path)
    elif source_path.is_dir():
        _custom_uv_dir = _resolve_source_dir(source_path)
    else:
        raise RuntimeError(f"Custom uv source is not a valid file, directory, or git URL: {source}")

    uv_bin = get_uv_binary("uv")
    logger.info("Custom uv configured: %s", uv_bin)
    return uv_bin


# ---------------------------------------------------------------------------
# Source resolution helpers
# ---------------------------------------------------------------------------


def _is_git_url(source: str) -> bool:
    """Return True if *source* looks like a git remote URL."""
    return source.startswith(("https://", "http://", "git@", "git://", "ssh://"))


def _resolve_binary_path(binary: Path) -> Path:
    """Use the parent directory of an existing uv binary."""
    resolved = binary.resolve()
    if not resolved.is_file():
        raise RuntimeError(f"Custom uv binary not found: {binary}")
    logger.info("Using existing uv binary: %s", resolved)
    return resolved.parent


def _resolve_source_dir(source_dir: Path) -> Path:
    """Build uv from a local Rust source tree and return the output directory."""
    source_dir = source_dir.resolve()
    cargo_toml = source_dir / "Cargo.toml"
    if not cargo_toml.is_file():
        # Maybe the user pointed at a directory containing the binary?
        uv_candidate = source_dir / f"uv{_EXE_SUFFIX}"
        if uv_candidate.is_file():
            logger.info("Using existing uv binary directory: %s", source_dir)
            return source_dir
        raise RuntimeError(
            f"Custom uv source directory has no Cargo.toml and no uv binary: {source_dir}"
        )
    return _cargo_build(source_dir)


def _resolve_git_source(url: str) -> Path:
    """Clone a git repo, build uv, and return the output directory."""
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    clone_dir = _CACHE_DIR / url_hash

    if clone_dir.exists() and (clone_dir / "Cargo.toml").is_file():
        logger.info("Reusing cached clone: %s", clone_dir)
        # Pull latest changes
        _git_pull(clone_dir)
    else:
        _git_clone(url, clone_dir)

    return _cargo_build(clone_dir)


def _git_clone(url: str, dest: Path) -> None:
    """Clone a git repository to *dest*."""
    logger.info("Cloning %s → %s", url, dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.check_call(
            ["git", "clone", "--depth", "1", url, str(dest)],
            timeout=300,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"git clone failed: {exc}") from exc
    except FileNotFoundError as exc:
        raise RuntimeError("git is not available on PATH") from exc


def _git_pull(repo_dir: Path) -> None:
    """Pull latest changes in an existing clone."""
    logger.info("Pulling latest changes in %s", repo_dir)
    try:
        subprocess.check_call(
            ["git", "pull", "--ff-only"],
            cwd=str(repo_dir),
            timeout=120,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("git pull failed; using existing checkout")


def _cargo_build(source_dir: Path) -> Path:
    """Run ``cargo build --release`` and return the directory containing binaries.

    The uv project uses a workspace layout.  We build the ``uv`` binary
    specifically using ``--package uv``.  If that fails (e.g. the project
    structure is different) we fall back to a plain ``cargo build --release``.
    """
    logger.info("Building uv from source in %s (this may take several minutes) …", source_dir)

    # Determine if this is a workspace with a uv package
    target_dir = source_dir / "target" / "release"

    # Try building just the uv package first (faster for the astral-sh/uv workspace)
    built = False
    for build_cmd in (
        ["cargo", "build", "--release", "--package", "uv"],
        ["cargo", "build", "--release"],
    ):
        try:
            logger.info("Running: %s", " ".join(build_cmd))
            subprocess.check_call(
                build_cmd,
                cwd=str(source_dir),
                timeout=1800,  # 30 min — Rust builds can be slow
            )
            built = True
            break
        except subprocess.CalledProcessError:
            logger.warning("Build command failed: %s; trying fallback", " ".join(build_cmd))
            continue
        except FileNotFoundError as exc:
            raise RuntimeError("cargo is not available on PATH") from exc

    if not built:
        raise RuntimeError(f"Cargo build failed in {source_dir}")

    # Verify the binary exists
    uv_bin = target_dir / f"uv{_EXE_SUFFIX}"
    if not uv_bin.is_file():
        contents = list(target_dir.iterdir()) if target_dir.exists() else "directory does not exist"
        raise RuntimeError(
            f"Cargo build succeeded but uv binary not found at {uv_bin}. "
            f"Contents of {target_dir}: {contents}"
        )

    logger.info("Custom uv binary built: %s", uv_bin)
    return target_dir


# ---------------------------------------------------------------------------
# Environment variable auto-configuration
# ---------------------------------------------------------------------------


def auto_configure_from_env() -> None:
    """Check the ``CUSTOM_UV`` environment variable and configure if set.

    This is called automatically on module import so that tests running
    under ``CUSTOM_UV=... uv run pytest`` pick up the custom binary
    without needing explicit CLI flags.
    """
    env_value = os.environ.get("CUSTOM_UV", "").strip()
    if env_value:
        try:
            setup_custom_uv(env_value)
        except RuntimeError:
            logger.warning(
                "CUSTOM_UV environment variable set to %r but could not resolve it; ignoring.",
                env_value,
            )


auto_configure_from_env()

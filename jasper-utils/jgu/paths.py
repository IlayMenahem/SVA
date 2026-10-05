"""Local path helpers shared by the uploader and the manifest builder."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

SKIPPED_NAMES = frozenset({"jgproj", "__pycache__", ".DS_Store", ".git"})


def walk_files(path: Path) -> list[Path]:
    """path itself if it is not a directory, else every file below it, sorted, skipping
    prover projects, caches and VCS metadata."""
    if not path.is_dir():
        return [path]
    files: list[Path] = []
    for root, dirs, names in os.walk(path):
        dirs[:] = sorted(d for d in dirs if d not in SKIPPED_NAMES)
        files += [
            Path(root) / name for name in sorted(names) if name not in SKIPPED_NAMES
        ]
    return files


def display_path(path: Path, cwd: Path) -> str:
    """Path relative to cwd when it lies below cwd, else absolute."""
    absolute = path if path.is_absolute() else cwd / path
    try:
        return absolute.relative_to(cwd).as_posix()
    except ValueError:
        return absolute.as_posix()


def require_relative(path: str) -> str:
    """A path that stays inside the directory it is relative to, in POSIX form."""
    posix = PurePosixPath(path)
    if posix.is_absolute() or ".." in posix.parts or not posix.parts:
        raise ValueError(
            f"path must be relative and inside the working directory: {path}"
        )
    return posix.as_posix()

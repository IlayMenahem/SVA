"""Build input manifests ({"files": [...], "settings": {...}}) for accelerate-sva-proofs' record_run.py."""

from __future__ import annotations

import glob
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from .flist import FileList
from .paths import display_path, walk_files


def expand_entry(entry: str, cwd: Path) -> list[Path]:
    """A file, a directory (recursively) or a glob pattern, relative to cwd."""
    path = Path(entry) if Path(entry).is_absolute() else cwd / entry
    if glob.has_magic(entry):
        return [
            file
            for match in sorted(glob.glob(str(path), recursive=True))
            for file in walk_files(Path(match))
        ]
    if not path.exists():
        raise FileNotFoundError(f"manifest entry does not exist: {entry}")
    return walk_files(path)


def flist_files(file_list: FileList) -> list[Path]:
    """Sources, the .f files themselves, and the files directly inside include directories."""
    included = [
        p
        for d in file_list.incdirs
        if d.is_dir()
        for p in sorted(d.iterdir())
        if p.is_file()
    ]
    return [*file_list.flists, *file_list.sources, *included]


def collect_files(
    cwd: Path, entries: Iterable[str], file_lists: Iterable[FileList]
) -> list[str]:
    """Sorted, de-duplicated manifest paths of every entry and file list."""
    paths = [p for entry in entries for p in expand_entry(entry, cwd)]
    paths += [p for file_list in file_lists for p in flist_files(file_list)]
    missing = sorted(str(p) for p in paths if not p.is_file())
    if missing:
        raise FileNotFoundError(
            f"manifest files do not exist: {', '.join(missing[:5])}"
        )
    root = cwd.resolve()
    return sorted({display_path(p.resolve(), root) for p in paths})


def parse_settings(pairs: Sequence[str]) -> dict[str, str]:
    """KEY=VALUE strings to a dict; a later key overrides an earlier one."""
    malformed = [p for p in pairs if "=" not in p or not p.split("=", 1)[0]]
    if malformed:
        raise ValueError(f"settings must be KEY=VALUE: {', '.join(malformed)}")
    return dict(p.split("=", 1) for p in pairs)


def build_manifest(
    files: Sequence[str],
    settings: Mapping[str, str],
    base: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Merge files and settings into an optional base manifest."""
    base_files = (base or {}).get("files", [])
    base_settings = (base or {}).get("settings", {})
    if not isinstance(base_files, list) or not isinstance(base_settings, dict):
        raise TypeError("base manifest needs a files list and a settings object")
    merged = sorted({str(f) for f in base_files} | set(files))
    if not merged:
        raise ValueError("a manifest needs at least one file")
    return {"files": merged, "settings": {**base_settings, **settings}}


def load_manifest(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or not isinstance(data.get("files"), list):
        raise TypeError(f"{path}: a manifest must be an object with a files list")
    return data


def write_manifest(path: Path, manifest: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n")

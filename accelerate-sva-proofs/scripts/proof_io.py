"""Shared integrity helpers; no vendor report interpretation."""

import hashlib
import json
from pathlib import Path


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def load_json(path):
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"invalid JSON number: {value}")

    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=unique_keys,
        parse_constant=invalid_constant,
    )


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def resolve(base, path):
    return (Path(base) / path).resolve()


def contained_file(base, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError("evidence path must be relative to the run directory")
    base = Path(base).resolve()
    path = resolve(base, name)
    if base not in path.parents or not path.is_file():
        raise ValueError(f"missing or escaping evidence path: {name}")
    return path

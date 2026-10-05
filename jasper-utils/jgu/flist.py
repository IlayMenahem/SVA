"""Expand Verilog file lists (.f) into source files, include dirs and defines."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

VARIABLE = re.compile(r"\$\{(\w+)\}|\$\((\w+)\)|\$(\w+)")
COMMENT = re.compile(r"//.*|#.*")
OPTIONS_WITH_ARGUMENT = frozenset({"-f", "-F", "-v", "-y", "-top"})


@dataclass(frozen=True)
class FileList:
    """Result of expanding one .f file and everything it includes."""

    sources: tuple[Path, ...] = ()
    incdirs: tuple[Path, ...] = ()
    defines: tuple[str, ...] = ()
    flists: tuple[Path, ...] = ()
    other: tuple[str, ...] = ()

    def merge(self, other: FileList) -> FileList:
        return FileList(
            sources=self.sources + other.sources,
            incdirs=self.incdirs + other.incdirs,
            defines=self.defines + other.defines,
            flists=self.flists + other.flists,
            other=self.other + other.other,
        )


def expand_variables(text: str, variables: Mapping[str, str]) -> str:
    """Substitute ${X}, $(X) and $X; unknown variables are an error."""
    unknown = sorted({next(filter(None, m.groups())) for m in VARIABLE.finditer(text)} - set(variables))
    if unknown:
        raise ValueError(f"undefined file-list variables: {', '.join(unknown)}")
    return VARIABLE.sub(lambda m: variables[next(filter(None, m.groups()))], text)


def tokens(text: str, variables: Mapping[str, str]) -> list[str]:
    """Words of a file list with comments removed first, so comments may mention any variable."""
    uncommented = "\n".join(COMMENT.sub("", line) for line in text.splitlines())
    return expand_variables(uncommented, variables).split()


def plus_option(token: str, base: Path) -> FileList:
    """+incdir+a+b and +define+A=1+B; other plus options are kept verbatim."""
    if token.startswith("+incdir+"):
        return FileList(incdirs=tuple(base / d for d in token[len("+incdir+") :].split("+") if d))
    if token.startswith("+define+"):
        return FileList(defines=tuple(d for d in token[len("+define+") :].split("+") if d))
    return FileList(other=(token,))


def parse_flist(path: Path, variables: Mapping[str, str], cwd: Path, relative_to_file: bool = False) -> FileList:
    """Expand path. Entries resolve against the file's own directory when relative_to_file
    (nested -F lists) and against cwd otherwise (nested -f lists)."""
    path = path if path.is_absolute() else cwd / path
    base = path.parent if relative_to_file else cwd
    words = tokens(path.read_text(), variables)
    result = FileList(flists=(path.resolve(),))
    index = 0
    while index < len(words):
        word = words[index]
        argument = words[index + 1] if word in OPTIONS_WITH_ARGUMENT and index + 1 < len(words) else None
        if word in ("-f", "-F") and argument is not None:
            result = result.merge(parse_flist(base / argument, variables, cwd, relative_to_file=word == "-F"))
        elif word == "-v" and argument is not None:
            result = result.merge(FileList(sources=((base / argument).resolve(),)))
        elif argument is not None:
            result = result.merge(FileList(other=(word, argument)))
        elif word.startswith("+"):
            result = result.merge(plus_option(word, base))
        elif word.startswith("-"):
            result = result.merge(FileList(other=(word,)))
        else:
            result = result.merge(FileList(sources=((base / word).resolve(),)))
        index += 2 if argument is not None else 1
    return FileList(
        sources=result.sources,
        incdirs=tuple(d.resolve() for d in result.incdirs),
        defines=result.defines,
        flists=result.flists,
        other=result.other,
    )


def missing_files(file_list: FileList) -> list[Path]:
    return [p for p in file_list.sources if not p.is_file()] + [d for d in file_list.incdirs if not d.is_dir()]

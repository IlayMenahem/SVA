"""Remote Jasper runs over ssh: pure command builders plus a thin subprocess edge.

Remote layout under the workspace root (relative to $HOME unless absolute):

    <root>/                 shared inputs uploaded with `jgu push` (read them via $JGU_ROOT)
    <root>/runs/<run>/      one directory per run, never reused
        <synced inputs>     the --sync paths, at their local relative paths
        .jgu/               runner, params, jglib.tcl, pgid, time.pid, inputs.sha256
        jg.log time.txt exit_code results.json cpu_sample.txt out/

The hosts' login shell may be csh, so every ssh command is a list of plain tokens
(validated below) and scripts travel as files or on stdin, never as quoted strings.
"""

from __future__ import annotations

import io
import os
import re
import shlex
import subprocess
import tarfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from .paths import require_relative, walk_files

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
RUNNER = PACKAGE_ROOT / "remote" / "jgu_run.sh"
SAMPLER = PACKAGE_ROOT / "remote" / "cpu_sampler.py"
JGLIB = PACKAGE_ROOT / "tcl" / "jglib.tcl"
SUPPORT_FILES: Mapping[str, Path] = {
    ".jgu/jgu_run.sh": RUNNER,
    ".jgu/cpu_sampler.py": SAMPLER,
    ".jgu/jglib.tcl": JGLIB,
}

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@-]*")
ROOT = re.compile(r"/?[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*")
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
REMOTE_TOKEN = re.compile(r"[A-Za-z0-9_./=+:,@%-]+")
REMOTE_OPERATORS = frozenset({"&&"})
MULTIPLEX_OPTIONS = ("-o", "ControlMaster=auto", "-o", "ControlPersist=120", "-o", "ControlPath=~/.ssh/jgu-%C")


@dataclass(frozen=True)
class Target:
    """A host and a workspace root on it (root is relative to $HOME unless absolute)."""

    host: str
    root: str

    def run_dir(self, run: str) -> str:
        return f"{self.root}/runs/{run}"


@dataclass(frozen=True)
class RunSpec:
    """One Jasper session: what to upload and how to start jg."""

    run: str
    tcl: str
    sync: tuple[str, ...]
    timeout_s: int
    jobs: int
    jg: str = "jg"
    env: tuple[tuple[str, str], ...] = ()
    sample_cpu: bool = True
    sample_period_s: int = 5
    kill_after_s: int = 30


def require_name(run: str) -> str:
    if not NAME.fullmatch(run):
        raise ValueError(f"run names use letters, digits, '.', '_' and '-': {run!r}")
    return run


def normalize_root(root: str) -> str:
    """The root without a leading '~/' or trailing '/', checked to be a plain path."""
    stripped = (root[2:] if root.startswith("~/") else root).rstrip("/")
    if not ROOT.fullmatch(stripped) or ".." in stripped.split("/"):
        raise ValueError(f"remote root must be a plain path of letters, digits, '.', '_', '-': {root!r}")
    return stripped


def make_target(host: str | None, root: str | None) -> Target:
    if not host or not HOST.fullmatch(host):
        raise ValueError(f"give a plain ssh host with --host or JGU_HOST: {host!r}")
    if not root:
        raise ValueError("give a remote workspace root with --root or JGU_ROOT")
    return Target(host=host, root=normalize_root(root))


def parse_env(pairs: Sequence[str]) -> tuple[tuple[str, str], ...]:
    """KEY=VALUE pairs exported to the Jasper session; JGU_* names are reserved."""
    bad = [
        p for p in pairs
        if "=" not in p or not ENV_NAME.fullmatch(p.split("=", 1)[0]) or p.startswith("JGU_")
    ]
    if bad:
        raise ValueError(f"--env takes KEY=VALUE with a shell name, not JGU_*: {', '.join(bad)}")
    return tuple((name, value) for name, value in (p.split("=", 1) for p in pairs))


def ssh_options() -> tuple[str, ...]:
    multiplex = os.environ.get("JGU_SSH_MUX", "1") != "0"
    return ("-o", "BatchMode=yes", *(MULTIPLEX_OPTIONS if multiplex else ()))


def ssh_argv(host: str, remote: Sequence[str], stdin_null: bool = True) -> list[str]:
    """ssh argv for a remote command made of csh-safe tokens."""
    unsafe = [t for t in remote if t not in REMOTE_OPERATORS and not REMOTE_TOKEN.fullmatch(t)]
    if unsafe:
        raise ValueError(f"unsafe remote tokens: {unsafe}")
    return ["ssh", *(["-n"] if stdin_null else []), *ssh_options(), host, *remote]


def params_text(spec: RunSpec, target: Target) -> str:
    """Shell assignments sourced by jgu_run.sh; user env comes last."""
    fixed = {
        "JGU_RUN": spec.run,
        "JGU_ROOT": target.root,
        "JGU_TCL": spec.tcl,
        "JGU_TIMEOUT_S": str(spec.timeout_s),
        "JGU_KILL_AFTER_S": str(spec.kill_after_s),
        "JGU_JOBS": str(spec.jobs),
        "JGU_JG": spec.jg,
        "JGU_SAMPLE_CPU": "1" if spec.sample_cpu else "0",
        "JGU_SAMPLE_PERIOD_S": str(spec.sample_period_s),
    }
    lines = [f"export {name}={shlex.quote(value)}" for name, value in [*fixed.items(), *spec.env]]
    return "# written by jgu run; sourced by .jgu/jgu_run.sh\n" + "\n".join(lines) + "\n"


def sync_files(cwd: Path, paths: Sequence[str]) -> list[str]:
    """Relative POSIX paths of every file under the sync paths, sorted and unique."""
    missing = [p for p in paths if not (cwd / require_relative(p)).exists()]
    if missing:
        raise FileNotFoundError(f"sync paths do not exist: {', '.join(missing)}")
    files = (f for p in paths for f in walk_files(cwd / require_relative(p)))
    return sorted({f.relative_to(cwd).as_posix() for f in files})


def run_files(cwd: Path, spec: RunSpec) -> list[str]:
    """Files uploaded for a run: the sync paths plus the Tcl script."""
    return sorted(set(sync_files(cwd, spec.sync)) | {require_relative(spec.tcl)})


def generated_files(spec: RunSpec, target: Target) -> dict[str, bytes]:
    return {
        ".jgu/params.sh": params_text(spec, target).encode(),
        **{name: path.read_bytes() for name, path in SUPPORT_FILES.items()},
    }


def write_archive(stream: IO[bytes], cwd: Path, files: Sequence[str], generated: Mapping[str, bytes]) -> None:
    """Stream a tar of files (relative to cwd) and generated members to stream."""
    with tarfile.open(fileobj=stream, mode="w|", format=tarfile.PAX_FORMAT) as tar:
        for name in files:
            tar.add(cwd / name, arcname=name, recursive=False)
        for name, data in generated.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o755 if name.endswith(".sh") else 0o644, int(time.time())
            tar.addfile(info, io.BytesIO(data))


def exists_argv(target: Target, path: str) -> list[str]:
    return ssh_argv(target.host, ["test", "-e", path])


def upload_run_argv(target: Target, run: str) -> list[str]:
    """Create the run directory atomically (mkdir fails if it exists) and untar stdin into it."""
    run_dir = target.run_dir(require_name(run))
    remote = ["mkdir", "-p", f"{target.root}/runs", "&&", "mkdir", run_dir, "&&", "tar", "-xf", "-", "-C", run_dir]
    return ssh_argv(target.host, remote, stdin_null=False)


def push_argv(target: Target) -> list[str]:
    return ssh_argv(target.host, ["mkdir", "-p", target.root, "&&", "tar", "-xf", "-", "-C", target.root], stdin_null=False)


def runner_argv(target: Target, run: str, mode: str, *extra: str) -> list[str]:
    script = f"{target.run_dir(require_name(run))}/.jgu/jgu_run.sh"
    return ssh_argv(target.host, ["sh", script, mode, *extra])


def list_argv(target: Target) -> list[str]:
    """ssh argv that runs jgu_run.sh from stdin in list mode."""
    return ssh_argv(target.host, ["sh", "-s", "list", target.root], stdin_null=False)


def remote_exists(target: Target, path: str) -> bool:
    result = subprocess.run(exists_argv(target, path), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode not in (0, 1):
        raise ConnectionError(f"ssh {target.host} failed: {result.stderr.decode(errors='replace').strip()}")
    return result.returncode == 0


def stream_upload(argv: Sequence[str], cwd: Path, files: Sequence[str], generated: Mapping[str, bytes]) -> int:
    """Run argv with a tar of the files on its stdin; returns its exit code."""
    with subprocess.Popen(list(argv), stdin=subprocess.PIPE) as process:
        assert process.stdin is not None
        try:
            write_archive(process.stdin, cwd, files, generated)
        except BrokenPipeError:
            pass
        finally:
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
        return process.wait()


def upload_run(target: Target, spec: RunSpec, cwd: Path) -> int:
    if remote_exists(target, target.run_dir(spec.run)):
        raise FileExistsError(f"{target.host}:{target.run_dir(spec.run)} exists; run names are never reused")
    return stream_upload(upload_run_argv(target, spec.run), cwd, run_files(cwd, spec), generated_files(spec, target))


def push(target: Target, cwd: Path, paths: Sequence[str]) -> int:
    return stream_upload(push_argv(target), cwd, sync_files(cwd, paths), {})


def start(target: Target, run: str, detach: bool) -> int:
    return subprocess.run(runner_argv(target, run, "start", *(["--detach"] if detach else []))).returncode


def control(target: Target, run: str, mode: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(runner_argv(target, run, mode), capture_output=True, text=True)


def list_runs(target: Target) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list_argv(target), input=RUNNER.read_text(), capture_output=True, text=True)


def fetch(target: Target, run: str, dest: Path) -> list[str]:
    """Copy the run outputs into dest (which must not exist); returns the member names."""
    if dest.exists():
        raise FileExistsError(f"{dest} exists; fetch into a fresh directory")
    dest.mkdir(parents=True)
    names: list[str] = []
    with subprocess.Popen(runner_argv(target, run, "pack"), stdout=subprocess.PIPE) as process:
        assert process.stdout is not None
        with tarfile.open(fileobj=process.stdout, mode="r|") as tar:
            for member in tar:
                tar.extract(member, dest, filter="data")
                names.append(member.name)
        if process.wait() != 0:
            raise RuntimeError(f"could not pack outputs of {target.host}:{target.run_dir(run)}")
    return names

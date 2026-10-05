"""Command line: `jasper-utils/bin/jgu <command> --help`."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from types import FrameType

from . import flist, manifest, remote, results, vcd

DEFAULT_OUT_ROOT = "jgu-runs"
FETCH_SLACK_S = 300
CLI = remote.PACKAGE_ROOT / "bin" / "jgu"
ACTIVE_STATES = frozenset({"new", "running", "started"})


def positive_int(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def env_int(name: str) -> int | None:
    value = os.environ.get(name)
    return int(value) if value else None


def raise_interrupt(signum: int, frame: FrameType | None) -> None:
    raise KeyboardInterrupt


def run_spec(args: argparse.Namespace, run: str) -> remote.RunSpec:
    if args.timeout is None:
        raise ValueError("give the session wall limit with --timeout or JGU_TIMEOUT_S")
    return remote.RunSpec(
        run=remote.require_name(run),
        tcl=args.tcl,
        sync=tuple(args.sync),
        timeout_s=args.timeout,
        jobs=args.jobs,
        jg=args.jg,
        env=remote.parse_env(args.env),
        sample_cpu=not args.no_sample_cpu,
    )


def run_command(target: remote.Target, spec: remote.RunSpec, out: Path) -> list[str]:
    """The `jgu run` argv that reproduces spec (used as the recorded command)."""
    return [
        sys.executable,
        str(CLI),
        "run",
        "--host",
        target.host,
        "--root",
        target.root,
        "--run",
        spec.run,
        "--tcl",
        spec.tcl,
        *[flag for path in spec.sync for flag in ("--sync", path)],
        "--timeout",
        str(spec.timeout_s),
        "--jobs",
        str(spec.jobs),
        "--jg",
        spec.jg,
        *[flag for name, value in spec.env for flag in ("--env", f"{name}={value}")],
        *([] if spec.sample_cpu else ["--no-sample-cpu"]),
        "--out",
        str(out),
    ]


def record_settings(target: remote.Target, spec: remote.RunSpec) -> dict[str, str]:
    return {
        "host": target.host,
        "root": target.root,
        "run": spec.run,
        "tcl": spec.tcl,
        "timeout_s": str(spec.timeout_s),
        "jobs": str(spec.jobs),
        "jg": spec.jg,
        "env": " ".join(f"{name}={value}" for name, value in spec.env),
    }


def report_names(spec: remote.RunSpec, with_results: bool) -> list[str]:
    return [
        "jg.log",
        "time.txt",
        "exit_code",
        *(["results.json"] if with_results else []),
        *(["cpu_sample.txt"] if spec.sample_cpu else []),
    ]


def read_file_lists(args: argparse.Namespace, cwd: Path) -> list[flist.FileList]:
    """The --flist files of a manifest or record command, expanded with --var and the environment."""
    env = {**os.environ, **manifest.parse_settings(args.var)}
    return [
        flist.parse_flist(Path(p), env, cwd, relative_to_file=args.flist_relative)
        for p in args.flist
    ]


def print_completed(process: subprocess.CompletedProcess[str]) -> int:
    print(process.stdout, end="")
    print(process.stderr, end="", file=sys.stderr)
    return process.returncode


def fetch_and_summarize(
    target: remote.Target, run: str, out: Path
) -> results.RunRecord:
    remote.fetch(target, run, out)
    record = results.load_run(out)
    print(results.format_run(record))
    print(f"outputs: {out}")
    return record


def run_attached(target: remote.Target, run: str) -> int:
    """Run in the foreground; on Ctrl-C or SIGTERM stop the remote run before returning 130."""
    previous = signal.signal(signal.SIGTERM, raise_interrupt)
    try:
        return remote.start(target, run, detach=False)
    except KeyboardInterrupt:
        print_completed(remote.control(target, run, "kill"))
        return 130
    finally:
        signal.signal(signal.SIGTERM, previous)


def cmd_run(args: argparse.Namespace) -> int:
    target = remote.make_target(args.host, args.root)
    spec = run_spec(args, args.run)
    out = Path(args.out or f"{DEFAULT_OUT_ROOT}/{spec.run}")
    if not args.detach and out.exists():
        raise FileExistsError(f"{out} exists; choose a new --out or run name")
    if remote.upload_run(target, spec, Path.cwd()) != 0:
        raise RuntimeError(f"upload to {target.host}:{target.run_dir(spec.run)} failed")
    if args.detach:
        return remote.start(target, spec.run, detach=True)
    code = run_attached(target, spec.run)
    if code == 255:
        raise ConnectionError(
            f"ssh to {target.host} failed; check `jgu status {spec.run}`"
        )
    fetch_and_summarize(target, spec.run, out)
    return code


def cmd_push(args: argparse.Namespace) -> int:
    target = remote.make_target(args.host, args.root)
    return remote.push(target, Path.cwd(), args.paths)


def cmd_status(args: argparse.Namespace) -> int:
    return print_completed(
        remote.control(remote.make_target(args.host, args.root), args.run, "status")
    )


def cmd_kill(args: argparse.Namespace) -> int:
    return print_completed(
        remote.control(remote.make_target(args.host, args.root), args.run, "kill")
    )


def cmd_list(args: argparse.Namespace) -> int:
    return print_completed(remote.list_runs(remote.make_target(args.host, args.root)))


def run_state(target: remote.Target, run: str) -> str:
    completed = remote.control(target, run, "status")
    statuses = results.field_lines(completed.stdout, results.STATUS_PREFIX)
    if completed.returncode != 0 or not statuses:
        raise ConnectionError(f"no status for {run}: {completed.stderr.strip()}")
    print(completed.stdout, end="", flush=True)
    return statuses[-1].get("state", "?")


def cmd_wait(args: argparse.Namespace) -> int:
    """Poll until the run is no longer active; 0 when done, 3 when still active at --max."""
    target = remote.make_target(args.host, args.root)
    deadline = time.monotonic() + args.max
    state = run_state(target, args.run)
    while state in ACTIVE_STATES and time.monotonic() < deadline:
        time.sleep(args.poll)
        state = run_state(target, args.run)
    if state == "done" and args.fetch:
        fetch_and_summarize(
            target, args.run, Path(args.out or f"{DEFAULT_OUT_ROOT}/{args.run}")
        )
    return 0 if state == "done" else 3 if state in ACTIVE_STATES else 1


def cmd_fetch(args: argparse.Namespace) -> int:
    target = remote.make_target(args.host, args.root)
    fetch_and_summarize(
        target, args.run, Path(args.out or f"{DEFAULT_OUT_ROOT}/{args.run}")
    )
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    records = [results.load_run(Path(d)) for d in args.run_dirs]
    print("\n".join(results.format_run(r) for r in records))
    return 1 if any(r.results_errors for r in records) else 0


def optional_float(text: str | None) -> float | None:
    try:
        return float(text) if text not in (None, "-") else None
    except ValueError:
        return None


def remote_cpu_runs(
    target: remote.Target,
) -> list[tuple[str, results.TimeRecord | None, float | None]]:
    listing = remote.list_runs(target)
    if listing.returncode != 0:
        raise ConnectionError(listing.stderr.strip())
    return [
        (
            fields.get("run", "?"),
            results.time_from_fields(fields),
            optional_float(fields.get("sampled_cpu_s")),
        )
        for fields in results.field_lines(listing.stdout, results.STATUS_PREFIX)
    ]


def local_cpu_runs(
    run_dirs: Sequence[str],
) -> list[tuple[str, results.TimeRecord | None, float | None]]:
    dirs = [Path(d) for d in run_dirs] or sorted(
        p for p in Path(DEFAULT_OUT_ROOT).glob("*") if p.is_dir()
    )
    records = [results.load_run(d) for d in dirs]
    return [(r.name, r.time, r.sampled_cpu_s) for r in records]


def cmd_cpu(args: argparse.Namespace) -> int:
    runs = (
        remote_cpu_runs(remote.make_target(args.host, args.root))
        if args.remote
        else local_cpu_runs(args.run_dirs)
    )
    pattern = re.compile(args.group) if args.group else None
    print(results.format_cpu(results.cpu_rows(runs, pattern)))
    return 0


def cmd_manifest(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    files = manifest.collect_files(cwd, args.include, read_file_lists(args, cwd))
    base = manifest.load_manifest(Path(args.base)) if args.base else None
    built = manifest.build_manifest(files, manifest.parse_settings(args.setting), base)
    manifest.write_manifest(Path(args.out), built)
    print(f"wrote {args.out}")
    return 0


def record_script(skill: str | None) -> Path:
    script = (
        Path(skill or os.environ.get("JGU_SKILL", "accelerate-sva-proofs"))
        / "scripts"
        / "record_run.py"
    )
    if not script.is_file():
        raise FileNotFoundError(
            f"{script} not found; pass --skill DIR or set JGU_SKILL"
        )
    return script


def cmd_record(args: argparse.Namespace) -> int:
    """Record one `jgu run` with accelerate-sva-proofs' record_run.py."""
    target = remote.make_target(args.host, args.root)
    spec = run_spec(args, args.name)
    tool_version = args.tool_version or os.environ.get("JGU_TOOL_VERSION")
    if not tool_version:
        raise ValueError("give --tool-version or JGU_TOOL_VERSION (recorded verbatim)")
    cwd = Path.cwd()
    output, out = Path(args.proof_runs) / spec.run, Path(DEFAULT_OUT_ROOT) / spec.run
    taken = [str(p) for p in (output, out) if p.exists()]
    if taken or remote.remote_exists(target, target.run_dir(spec.run)):
        raise FileExistsError(
            f"run name {spec.run} is taken: {', '.join(taken) or target.run_dir(spec.run)}"
        )
    entries = [
        *args.include,
        *spec.sync,
        spec.tcl,
        *(str(p) for p in remote.SUPPORT_FILES.values()),
    ]
    files = manifest.collect_files(cwd, entries, read_file_lists(args, cwd))
    base = manifest.load_manifest(Path(args.manifest)) if args.manifest else None
    settings = {
        **record_settings(target, spec),
        **manifest.parse_settings(args.setting),
    }
    manifest_path = Path(args.proof_runs) / "manifests" / f"{spec.run}.json"
    manifest.write_manifest(
        manifest_path, manifest.build_manifest(files, settings, base)
    )
    reports = [
        flag
        for name in report_names(spec, not args.no_results)
        for flag in ("--report", f"{out}/{name}")
    ]
    command = [
        sys.executable,
        str(record_script(args.skill)),
        "--cwd",
        str(cwd),
        "--manifest",
        str(manifest_path),
        "--output",
        str(output),
        "--timeout",
        str(spec.timeout_s + FETCH_SLACK_S),
        "--tool-version",
        tool_version,
        *reports,
        "--",
        *run_command(target, spec, out),
    ]
    return subprocess.run(command, check=False).returncode


def cmd_vcd(args: argparse.Namespace) -> int:
    trace = vcd.parse_vcd(Path(args.file).read_text())
    if args.list or not args.sig:
        print("\n".join(f"{s.name}\t{s.width}" for s in trace.signals))
        return 0
    clock = vcd.single_signal(trace, args.clock, "clock")
    print(
        vcd.table(
            trace,
            vcd.find_signals(trace, args.sig),
            clock,
            args.radix,
            args.first_cycle,
        )
    )
    return 0


def cmd_flist(args: argparse.Namespace) -> int:
    env = {**os.environ, **manifest.parse_settings(args.var)}
    parsed = flist.parse_flist(
        Path(args.file), env, Path.cwd(), relative_to_file=args.F
    )
    missing = flist.missing_files(parsed)
    if args.json:
        print(
            json.dumps(
                {
                    key: [str(v) for v in getattr(parsed, key)]
                    for key in ("sources", "incdirs", "defines", "flists", "other")
                },
                indent=2,
            )
        )
    else:
        print("\n".join(str(p) for p in parsed.sources))
    if missing:
        print(
            f"jgu: missing: {', '.join(str(p) for p in missing[:5])}", file=sys.stderr
        )
    return 1 if missing else 0


def add_target_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--host",
        default=os.environ.get("JGU_HOST"),
        help="ssh host (default $JGU_HOST)",
    )
    parser.add_argument(
        "--root",
        default=os.environ.get("JGU_ROOT"),
        help="remote workspace, relative to $HOME unless absolute (default $JGU_ROOT)",
    )


def add_run_options(parser: argparse.ArgumentParser) -> None:
    add_target_options(parser)
    parser.add_argument(
        "--tcl",
        required=True,
        help="Jasper Tcl script, relative to the current directory",
    )
    parser.add_argument(
        "--sync",
        action="append",
        default=[],
        metavar="PATH",
        help="file or directory (relative) uploaded into the run directory; repeatable",
    )
    parser.add_argument(
        "--timeout",
        type=positive_int,
        default=env_int("JGU_TIMEOUT_S"),
        help="session wall limit in seconds, including elaboration (default $JGU_TIMEOUT_S)",
    )
    parser.add_argument(
        "--jobs",
        type=positive_int,
        default=env_int("JGU_JOBS") or 2,
        help="engine job cap exported as JGU_JOBS for jgu::caps (default $JGU_JOBS or 2)",
    )
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="environment variable for the Tcl script; repeatable",
    )
    parser.add_argument(
        "--jg", default=os.environ.get("JGU_JG", "jg"), help="jg executable on the host"
    )
    parser.add_argument(
        "--no-sample-cpu",
        action="store_true",
        help="skip the /proc CPU sampler (it catches engine CPU that GNU time misses "
        "when jg is killed)",
    )


def add_manifest_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="PATH",
        help="manifest file, directory or glob; repeatable",
    )
    parser.add_argument(
        "--flist",
        action="append",
        default=[],
        metavar="FILE",
        help="add a .f file, its sources and its include-dir files; repeatable",
    )
    parser.add_argument(
        "--flist-relative",
        action="store_true",
        help="--flist entries are relative to the .f file (like -F), not the current directory",
    )
    parser.add_argument(
        "--var",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="file-list variable (the environment is used too)",
    )
    parser.add_argument(
        "--setting",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="manifest setting",
    )


Handler = Callable[[argparse.Namespace], int]


def add_command(
    subparsers: argparse._SubParsersAction, name: str, handler: Handler, help_text: str
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(name, help=help_text, description=help_text)
    parser.set_defaults(handler=handler)
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jgu", description="Run and inspect JasperGold sessions on remote hosts."
    )
    commands = parser.add_subparsers(required=True, metavar="command")

    run = add_command(
        commands, "run", cmd_run, "upload inputs and run one Jasper session"
    )
    add_run_options(run)
    run.add_argument("--run", required=True, help="new run name (never reused)")
    run.add_argument(
        "--detach",
        action="store_true",
        help="return after starting; use wait/status/fetch later",
    )
    run.add_argument(
        "--out", help=f"local output directory (default {DEFAULT_OUT_ROOT}/RUN)"
    )

    record = add_command(
        commands, "record", cmd_record, "run one Jasper session under record_run.py"
    )
    add_run_options(record)
    record.add_argument(
        "--name",
        required=True,
        help="run name: remote run, jgu-runs/NAME and proof-runs/NAME",
    )
    record.add_argument(
        "--tool-version", help="prover version string (default $JGU_TOOL_VERSION)"
    )
    record.add_argument("--manifest", help="base manifest to extend")
    add_manifest_options(record)
    record.add_argument(
        "--skill",
        help="accelerate-sva-proofs directory (default $JGU_SKILL or ./accelerate-sva-proofs)",
    )
    record.add_argument(
        "--proof-runs",
        default="proof-runs",
        help="record output root (default proof-runs)",
    )
    record.add_argument(
        "--no-results",
        action="store_true",
        help="the Tcl script writes no results.json",
    )

    push = add_command(
        commands,
        "push",
        cmd_push,
        "upload shared inputs (e.g. sources) into the workspace root",
    )
    add_target_options(push)
    push.add_argument("paths", nargs="+", help="relative files or directories")

    for name, handler, text in (
        ("status", cmd_status, "print the state of one run"),
        ("kill", cmd_kill, "stop one run, keeping its time record"),
    ):
        sub = add_command(commands, name, handler, text)
        add_target_options(sub)
        sub.add_argument("run")

    wait = add_command(commands, "wait", cmd_wait, "poll a run until it finishes")
    add_target_options(wait)
    wait.add_argument("run")
    wait.add_argument(
        "--poll",
        type=positive_int,
        default=30,
        help="seconds between polls (default 30)",
    )
    wait.add_argument(
        "--max",
        type=positive_int,
        default=3600,
        help="give up after this many seconds (exit 3)",
    )
    wait.add_argument(
        "--fetch", action="store_true", help="fetch the outputs when done"
    )
    wait.add_argument(
        "--out",
        help=f"local output directory for --fetch (default {DEFAULT_OUT_ROOT}/RUN)",
    )

    fetch = add_command(
        commands,
        "fetch",
        cmd_fetch,
        "copy a run's outputs into a fresh local directory",
    )
    add_target_options(fetch)
    fetch.add_argument("run")
    fetch.add_argument(
        "--out", help=f"local directory (default {DEFAULT_OUT_ROOT}/RUN)"
    )

    listing = add_command(
        commands, "list", cmd_list, "print the state of every run in the workspace"
    )
    add_target_options(listing)

    summary = add_command(
        commands, "summary", cmd_summary, "summarize fetched run directories"
    )
    summary.add_argument("run_dirs", nargs="+")

    cpu = add_command(
        commands, "cpu", cmd_cpu, "total CPU time of runs (fetched, or --remote)"
    )
    add_target_options(cpu)
    cpu.add_argument(
        "run_dirs",
        nargs="*",
        help=f"fetched run directories (default {DEFAULT_OUT_ROOT}/*)",
    )
    cpu.add_argument(
        "--remote",
        action="store_true",
        help="read every run in the remote workspace instead",
    )
    cpu.add_argument(
        "--group",
        help="regex over run names; capture group 1 (or the match) names the group",
    )

    made = add_command(
        commands, "manifest", cmd_manifest, "write an input manifest for record_run.py"
    )
    made.add_argument("--out", required=True)
    made.add_argument("--base", help="manifest to extend")
    add_manifest_options(made)

    trace = add_command(
        commands, "vcd", cmd_vcd, "print a VCD trace as one row per clock cycle"
    )
    trace.add_argument("file")
    trace.add_argument(
        "--sig",
        action="append",
        default=[],
        metavar="REGEX",
        help="signals to show; repeatable",
    )
    trace.add_argument(
        "--clock", default=vcd.DEFAULT_CLOCK, help="regex matching the one clock signal"
    )
    trace.add_argument("--radix", choices=("hex", "bin", "dec"), default="hex")
    trace.add_argument(
        "--first-cycle",
        type=int,
        default=1,
        help="number of the first row (1 matches Jasper)",
    )
    trace.add_argument(
        "--list", action="store_true", help="list signal names and widths"
    )

    files = add_command(commands, "flist", cmd_flist, "expand a .f file list")
    files.add_argument("file")
    files.add_argument(
        "-F", action="store_true", help="entries are relative to the file's directory"
    )
    files.add_argument(
        "--var",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="file-list variable",
    )
    files.add_argument(
        "--json",
        action="store_true",
        help="print sources, incdirs, defines, flists and options",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (ValueError, TypeError, OSError, ConnectionError, RuntimeError) as error:
        print(f"jgu: {error}", file=sys.stderr)
        return 2

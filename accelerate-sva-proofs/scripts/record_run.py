#!/usr/bin/env python3
"""Record one bounded POSIX command without interpreting its proof outcome."""

import argparse
import math
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from proof_io import digest, load_json, resolve, write_json


def positive_timeout(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("timeout must be finite and positive")
    return number


def stop_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def record(args):
    if os.name != "posix":
        raise ValueError("timed recording requires POSIX process groups")
    cwd = Path(args.cwd).resolve(strict=True)
    if not cwd.is_dir():
        raise ValueError("cwd must be a directory")
    manifest = load_json(args.manifest)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise TypeError("manifest must contain a files list")
    if not manifest["files"] or any(
        not isinstance(p, str) or not p for p in manifest["files"]
    ):
        raise ValueError("manifest files must be nonempty path strings")
    if not isinstance(manifest.get("settings", {}), dict):
        raise TypeError("manifest settings must be an object")
    files = [resolve(cwd, p) for p in manifest["files"]]
    if len(set(files)) != len(files):
        raise ValueError("manifest contains duplicate resolved paths")
    before = {str(p): digest(p) for p in files}
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise ValueError("supply an executable and arguments after --")
    reports = [resolve(cwd, p) for p in args.report]
    if len(set(reports)) != len(reports):
        raise ValueError("duplicate report paths")
    if any(p.exists() for p in reports):
        raise ValueError(
            "report paths must be fresh; choose a new prover output location"
        )
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    timer = time.monotonic()
    result = {
        "schema_version": 1,
        "command": command,
        "cwd": str(cwd),
        "timeout_seconds": args.timeout,
        "tool_version": args.tool_version,
        "manifest": manifest,
        "inputs_before": before,
        "started_at": started,
        "status": "launch_error",
        "exit_code": None,
        "errors": [],
        "evidence": {},
    }
    process = None
    with (
        (output / "stdout.log").open("xb") as stdout,
        (output / "stderr.log").open("xb") as stderr,
    ):
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=stdout,
                stderr=stderr,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
            result["exit_code"] = process.wait(timeout=args.timeout)
            result["status"] = "completed"
        except subprocess.TimeoutExpired:
            result["status"] = "timeout"
            stop_group(process)
            result["exit_code"] = process.returncode
        except KeyboardInterrupt:
            result["status"] = "interrupted"
            if process is not None:
                stop_group(process)
                result["exit_code"] = process.returncode
        except OSError as exc:
            result["errors"].append(str(exc))
        finally:
            # A synchronous prover command must not leave workers writing evidence.
            if process is not None:
                stop_group(process)
    result["finished_at"] = time.time()
    result["elapsed_seconds"] = time.monotonic() - timer
    result["inputs_after"] = {}
    for path in files:
        try:
            result["inputs_after"][str(path)] = digest(path)
        except OSError as exc:
            result["inputs_after"][str(path)] = None
            result["errors"].append(f"input unavailable after run: {path}: {exc}")
    result["inputs_unchanged"] = before == result["inputs_after"]
    for name in ("stdout.log", "stderr.log"):
        result["evidence"][name] = digest(output / name)
    if reports:
        (output / "reports").mkdir()
    for index, report in enumerate(reports):
        name = f"reports/{index:03d}-{report.name}"
        try:
            # Explicit report paths are caller-selected; copied bytes are archived.
            with report.open("rb") as source, (output / name).open("xb") as dest:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    dest.write(chunk)
            result["evidence"][name] = digest(output / name)
        except OSError as exc:
            result["errors"].append(f"could not archive report {report}: {exc}")
    write_json(output / "run.json", result)
    print(
        f"{output / 'run.json'}\nsha256={digest(output / 'run.json')}\n"
        f"execution={result['status']} exit_code={result['exit_code']} (proof outcome not inferred)"
    )
    if result["status"] == "timeout":
        return 124
    if result["status"] == "interrupted":
        return 130
    return (
        0
        if (
            result["status"] == "completed"
            and result["exit_code"] == 0
            and result["inputs_unchanged"]
            and not result["errors"]
        )
        else 1
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument(
        "--output", required=True, help="new directory; never overwrite"
    )
    parser.add_argument("--timeout", required=True, type=positive_timeout)
    parser.add_argument(
        "--tool-version", default="", help="recorded verbatim; not probed"
    )
    parser.add_argument(
        "--report", action="append", default=[], help="report path relative to cwd"
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        return record(args)
    except (OSError, ValueError, TypeError) as exc:
        print(f"recording error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

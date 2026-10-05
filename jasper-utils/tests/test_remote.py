"""Tests for jgu.remote's pure builders and for record/run argv round trips in jgu.cli."""

import io
import os
import subprocess
import tarfile
import unittest
from pathlib import Path
from unittest import mock

from support import TempDirTest

from jgu import cli, remote

TARGET = remote.Target(host="prover-1", root="ws/task")


class Validation(unittest.TestCase):
    def test_roots(self) -> None:
        self.assertEqual(remote.normalize_root("~/ws/task/"), "ws/task")
        self.assertEqual(remote.normalize_root("/abs/ws"), "/abs/ws")
        for bad in ("ws/../x", "ws task", "ws;rm", "$HOME/x", ""):
            with self.assertRaises(ValueError, msg=bad):
                remote.normalize_root(bad)

    def test_names_and_hosts(self) -> None:
        self.assertEqual(remote.require_name("disc-01.b_2"), "disc-01.b_2")
        for bad in ("-x", "a/b", "a b", ""):
            with self.assertRaises(ValueError, msg=bad):
                remote.require_name(bad)
        with self.assertRaises(ValueError):
            remote.make_target("host;x", "ws")
        with self.assertRaises(ValueError):
            remote.make_target("prover-1", None)

    def test_env(self) -> None:
        self.assertEqual(remote.parse_env(["A=1", "B=x=y z"]), (("A", "1"), ("B", "x=y z")))
        for bad in (["JGU_JOBS=3"], ["1A=x"], ["novalue"]):
            with self.assertRaises(ValueError, msg=bad):
                remote.parse_env(bad)


class Commands(unittest.TestCase):
    def test_ssh_tokens_must_be_csh_safe(self) -> None:
        with self.assertRaises(ValueError):
            remote.ssh_argv("h", ["echo", "$(id)"])
        with self.assertRaises(ValueError):
            remote.ssh_argv("h", ["a", ";", "b"])

    def test_upload_creates_the_run_dir_atomically(self) -> None:
        argv = remote.upload_run_argv(TARGET, "r1")
        self.assertNotIn("-n", argv)
        tail = argv[argv.index("prover-1") + 1:]
        self.assertEqual(tail, ["mkdir", "-p", "ws/task/runs", "&&", "mkdir", "ws/task/runs/r1",
                                "&&", "tar", "-xf", "-", "-C", "ws/task/runs/r1"])

    def test_runner_and_list(self) -> None:
        self.assertEqual(remote.runner_argv(TARGET, "r1", "kill")[-3:], ["sh", "ws/task/runs/r1/.jgu/jgu_run.sh", "kill"])
        self.assertIn("-n", remote.runner_argv(TARGET, "r1", "status"))
        self.assertEqual(remote.list_argv(TARGET)[-4:], ["sh", "-s", "list", "ws/task"])

    def test_multiplexing_can_be_disabled(self) -> None:
        with mock.patch.dict(os.environ, {"JGU_SSH_MUX": "0"}):
            self.assertNotIn("ControlMaster=auto", remote.ssh_argv("h", ["true"]))
        with mock.patch.dict(os.environ, {"JGU_SSH_MUX": "1"}):
            self.assertIn("ControlMaster=auto", remote.ssh_argv("h", ["true"]))


class Params(TempDirTest):
    def test_params_survive_sh_quoting(self) -> None:
        spec = remote.RunSpec(run="r1", tcl="formal/run.tcl", sync=(), timeout_s=900, jobs=3,
                              env=(("NOTE", "it's \"quoted\" $HOME `x`"),))
        path = self.write("params.sh", remote.params_text(spec, TARGET))
        printed = subprocess.run(["sh", "-c", f". {path}; printf '%s|%s|%s|%s' \"$NOTE\" \"$JGU_ROOT\" "
                                 "\"$JGU_TIMEOUT_S\" \"$JGU_SAMPLE_CPU\""],
                                 capture_output=True, text=True, check=True).stdout
        self.assertEqual(printed, "it's \"quoted\" $HOME `x`|ws/task|900|1")


class Archive(TempDirTest):
    def test_archive_holds_sync_files_tcl_and_support_files(self) -> None:
        self.write("formal/run.tcl", "puts hi")
        self.write("formal/jgproj/db", "x")
        self.write("formal/__pycache__/c.pyc", "x")
        self.write("rtl/a.sv", "module a; endmodule")
        spec = remote.RunSpec(run="r1", tcl="formal/run.tcl", sync=("rtl",), timeout_s=60, jobs=1)
        files = remote.run_files(self.tmp, spec)
        self.assertEqual(files, ["formal/run.tcl", "rtl/a.sv"])
        stream = io.BytesIO()
        remote.write_archive(stream, self.tmp, files, remote.generated_files(spec, TARGET))
        stream.seek(0)
        with tarfile.open(fileobj=stream) as tar:
            members = {m.name: m for m in tar.getmembers()}
            self.assertEqual(sorted(members), sorted(files + list(remote.SUPPORT_FILES) + [".jgu/params.sh"]))
            self.assertEqual(members[".jgu/jgu_run.sh"].mode, 0o755)
            self.assertIn(b"JGU_RUN=r1", tar.extractfile(".jgu/params.sh").read())

    def test_sync_paths_must_stay_inside(self) -> None:
        for bad in ("../x", "/etc", "missing"):
            with self.assertRaises((ValueError, FileNotFoundError), msg=bad):
                remote.sync_files(self.tmp, [bad])


class RecordCommand(unittest.TestCase):
    def test_recorded_command_reproduces_the_spec(self) -> None:
        spec = remote.RunSpec(run="rec-1", tcl="f/run.tcl", sync=("f", "rtl"), timeout_s=900, jobs=4,
                              jg="/opt/jg", env=(("A", "x y"),), sample_cpu=False)
        argv = cli.run_command(TARGET, spec, Path("jgu-runs/rec-1"))
        args = cli.build_parser().parse_args(argv[2:])
        self.assertEqual(cli.run_spec(args, args.run), spec)
        self.assertEqual(remote.make_target(args.host, args.root), TARGET)
        self.assertEqual(args.out, "jgu-runs/rec-1")

    def test_report_names_follow_options(self) -> None:
        spec = remote.RunSpec(run="r", tcl="t.tcl", sync=(), timeout_s=1, jobs=1)
        self.assertEqual(cli.report_names(spec, with_results=True),
                         ["jg.log", "time.txt", "exit_code", "results.json", "cpu_sample.txt"])
        unsampled = remote.RunSpec(run="r", tcl="t.tcl", sync=(), timeout_s=1, jobs=1, sample_cpu=False)
        self.assertEqual(cli.report_names(unsampled, with_results=False), ["jg.log", "time.txt", "exit_code"])


if __name__ == "__main__":
    unittest.main()

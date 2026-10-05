"""Tests for remote/jgu_run.sh modes that run anywhere (status, list, pack, usage).

The start and kill modes need GNU time, timeout and setsid; the README's smoke test
exercises them on a Jasper host.
"""

import io
import os
import subprocess
import tarfile
import unittest

from support import PACKAGE_ROOT, TempDirTest

RUNNER = PACKAGE_ROOT / "remote" / "jgu_run.sh"


class Runner(TempDirTest):
    def make_run(self, name: str, files: dict[str, str]) -> None:
        self.write(f"ws/runs/{name}/.jgu/jgu_run.sh", RUNNER.read_text())
        for relative, text in files.items():
            self.write(f"ws/runs/{name}/{relative}", text)

    def runner(self, name: str, mode: str) -> subprocess.CompletedProcess[bytes]:
        script = self.tmp / f"ws/runs/{name}/.jgu/jgu_run.sh"
        no_mac_metadata = {**os.environ, "COPYFILE_DISABLE": "1"}
        return subprocess.run(
            ["sh", str(script), mode],
            capture_output=True,
            cwd=self.tmp,
            env=no_mac_metadata,
            check=False,
        )

    def test_status_of_a_finished_run(self) -> None:
        self.make_run(
            "done-1",
            {
                ".jgu/done": "",
                ".jgu/started": "100\n",
                ".jgu/finished": "142\n",
                "exit_code": "124\n",
                "time.txt": "Command exited with non-zero status 124\nJGU_TIME wall=42.0 user=1 sys=0 maxrss_kb=5\n",
                "cpu_sample.txt": "JGU_CPUSAMPLE total_cpu_s=40.50 procs=3\n",
            },
        )
        out = self.runner("done-1", "status").stdout.decode()
        self.assertEqual(
            out.split(),
            [
                "JGU_STATUS",
                "run=done-1",
                "state=done",
                "exit=124",
                "killed=no",
                "elapsed_s=42",
                "sampled_cpu_s=40.50",
                "wall=42.0",
                "user=1",
                "sys=0",
                "maxrss_kb=5",
            ],
        )

    def test_states_new_and_lost(self) -> None:
        self.make_run("new-1", {})
        self.assertIn("state=new", self.runner("new-1", "status").stdout.decode())
        self.make_run("lost-1", {".jgu/pgid": "999999\n", ".jgu/started": "1\n"})
        self.assertIn("state=lost", self.runner("lost-1", "status").stdout.decode())

    def test_kill_of_a_finished_run_only_reports(self) -> None:
        self.make_run("done-2", {".jgu/done": "", "exit_code": "0\n"})
        out = self.runner("done-2", "kill")
        self.assertEqual(out.returncode, 0)
        self.assertIn("state=done", out.stdout.decode())

    def test_list_reads_the_script_from_stdin(self) -> None:
        self.make_run("a-1", {".jgu/done": "", "exit_code": "0\n"})
        self.make_run("b-1", {})
        listing = subprocess.run(
            ["sh", "-s", "list", "ws"],
            input=RUNNER.read_bytes(),
            capture_output=True,
            env={**os.environ, "HOME": str(self.tmp)},
            check=True,
        ).stdout.decode()
        self.assertEqual(
            [line.split()[1] for line in listing.splitlines()], ["run=a-1", "run=b-1"]
        )

    def test_pack_tars_only_existing_outputs(self) -> None:
        self.make_run(
            "p-1",
            {
                "jg.log": "log",
                "results.json": "{}",
                "out/t.vcd": "v",
                "formal/run.tcl": "x",
                ".jgu/params.sh": "export JGU_RUN=p-1\n",
            },
        )
        packed = self.runner("p-1", "pack")
        self.assertEqual(packed.returncode, 0, packed.stderr)
        with tarfile.open(fileobj=io.BytesIO(packed.stdout)) as tar:
            names = {m.name for m in tar.getmembers() if m.isfile()}
        self.assertEqual(
            names, {"jg.log", "results.json", "out/t.vcd", ".jgu/params.sh"}
        )

    def test_unknown_mode_is_usage_error(self) -> None:
        self.make_run("u-1", {})
        self.assertEqual(self.runner("u-1", "bogus").returncode, 2)


if __name__ == "__main__":
    unittest.main()

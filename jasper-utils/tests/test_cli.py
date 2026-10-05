"""End-to-end tests of the local `jgu` subcommands (no ssh)."""

import json
import os
import subprocess
import sys
import unittest

from support import PACKAGE_ROOT, TempDirTest

JGU = PACKAGE_ROOT / "bin" / "jgu"
NO_REMOTE_ENV = {k: v for k, v in os.environ.items() if not k.startswith("JGU_")}


def jgu(*args: str, cwd: object = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(JGU), *args], capture_output=True, text=True, cwd=cwd,
                          env=NO_REMOTE_ENV)


class Local(TempDirTest):
    def test_summary_and_cpu_of_fetched_runs(self) -> None:
        self.write("jgu-runs/disc-1/time.txt", "JGU_TIME wall=10 user=8 sys=1 maxrss_kb=1\n")
        self.write("jgu-runs/disc-1/exit_code", "0\n")
        self.write("jgu-runs/disc-1/results.json", json.dumps({"properties": [
            {"id": "t", "kind": "assert", "status": "proven", "engine": "Hp", "assumed": []}]}))
        self.write("jgu-runs/disc-2/time.txt", "Command terminated by signal 15\nJGU_TIME wall=60 user=0 sys=0 maxrss_kb=1\n")
        self.write("jgu-runs/disc-2/cpu_sample.txt", "JGU_CPUSAMPLE total_cpu_s=55.0\n")
        summary = jgu("summary", "jgu-runs/disc-1", cwd=self.tmp)
        self.assertEqual(summary.returncode, 0, summary.stderr)
        self.assertIn("results=proven:1", summary.stdout)
        cpu = jgu("cpu", "--group", "^([a-z]+)-", cwd=self.tmp)
        total = json.loads(cpu.stdout.splitlines()[-1].split(" ", 1)[1])
        self.assertEqual((total["runs"], total["effective_cpu_s"], total["groups"]), (2, 64.0, {"disc": 64.0}))

    def test_manifest_and_flist(self) -> None:
        self.write("rtl/a.sv", "")
        self.write("rtl/files.f", "a.sv\n")
        self.write("formal/run.tcl", "")
        listed = jgu("flist", "rtl/files.f", "-F", cwd=self.tmp)
        self.assertEqual(listed.stdout.strip(), str(self.tmp / "rtl/a.sv"))
        made = jgu("manifest", "--out", "m.json", "--include", "formal", "--flist", "rtl/files.f", "--flist-relative",
                   "--setting", "top=a", cwd=self.tmp)
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertEqual(json.loads((self.tmp / "m.json").read_text()),
                         {"files": ["formal/run.tcl", "rtl/a.sv", "rtl/files.f"], "settings": {"top": "a"}})

    def test_remote_commands_need_a_target(self) -> None:
        missing = jgu("status", "r1", cwd=self.tmp)
        self.assertEqual(missing.returncode, 2)
        self.assertIn("--host", missing.stderr)

    def test_run_needs_a_timeout(self) -> None:
        result = jgu("run", "--host", "h", "--root", "ws", "--run", "r", "--tcl", "t.tcl", cwd=self.tmp)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--timeout", result.stderr)


if __name__ == "__main__":
    unittest.main()

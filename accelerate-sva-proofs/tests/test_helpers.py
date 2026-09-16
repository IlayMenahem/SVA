"""Behavioral tests use synthetic commands, not formal-verification results."""

import copy
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from audit_proof import audit
from proof_io import digest


@unittest.skipUnless(os.name == "posix", "recorder requires POSIX")
class Helpers(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "input.sv"
        self.source.write_text("original RTL snapshot\n")
        self.manifest = self.root / "inputs.json"
        self.manifest.write_text(json.dumps({"files": ["input.sv"]}))
        self.serial = 0

    def run_command(
        self,
        code="print('synthetic result')",
        timeout=5,
        extra=(),
        arguments=(),
        output=None,
    ):
        self.serial += 1
        folder = output or self.root / f"run-{self.serial}"
        command = [
            sys.executable,
            str(SCRIPTS / "record_run.py"),
            "--cwd",
            str(self.root),
            "--manifest",
            str(self.manifest),
            "--output",
            str(folder),
            "--timeout",
            str(timeout),
            "--tool-version",
            "synthetic test executable",
            *extra,
            "--",
            sys.executable,
            "-c",
            code,
            *arguments,
        ]
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=15, check=False
        )
        return result, folder

    def proved_node(self, name, deps=()):
        result, folder = self.run_command()
        self.assertEqual(result.returncode, 0, result.stderr)
        run = json.loads((folder / "run.json").read_text())
        return {
            "id": name,
            "statement": f"synthetic {name}",
            "scope": "test scope",
            "dependencies": list(deps),
            "premises": [],
            "outcome": "proved",
            "proof_kind": "unbounded",
            "run": str(folder / "run.json"),
            "run_sha256": digest(folder / "run.json"),
            "evidence": {
                "file": "stdout.log",
                "sha256": run["evidence"]["stdout.log"],
                "locator": "synthetic fixture, not a real proof",
            },
            "context_review": "synthetic bookkeeping fixture",
        }

    def ledger(self):
        helper = self.proved_node("helper")
        target = self.proved_node("target", ["helper"])
        return {
            "schema_version": 1,
            "target": "target",
            "premises": [],
            "transformations": [],
            "obligations": [helper, target],
        }

    def inspect(self, ledger):
        path = self.root / "ledger.json"
        path.write_text(json.dumps(ledger))
        try:
            return audit(path)
        except ValueError as exc:
            return {"bookkeeping_ok": False, "errors": [str(exc)]}

    def test_success_preserves_literal_arguments_and_does_not_infer_proof(self):
        args = ["a b", "$(touch NEVER)", "`literal`", "x;y", "a\nb"]
        result, folder = self.run_command(
            "import sys,json; print(json.dumps(sys.argv[1:]))", arguments=args
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((folder / "stdout.log").read_text()), args)
        run = json.loads((folder / "run.json").read_text())
        self.assertNotIn("proof_kind", run)
        self.assertNotIn("outcome", run)
        self.assertFalse((self.root / "NEVER").exists())

    def test_failure_timeout_and_launch_error(self):
        result, folder = self.run_command("import sys; sys.exit(7)")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads((folder / "run.json").read_text())["exit_code"], 7)
        result, folder = self.run_command("import time; time.sleep(10)", timeout=0.1)
        self.assertEqual(result.returncode, 124)
        self.assertEqual(
            json.loads((folder / "run.json").read_text())["status"], "timeout"
        )
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "record_run.py"),
                "--cwd",
                str(self.root),
                "--manifest",
                str(self.manifest),
                "--output",
                str(self.root / "missing"),
                "--timeout",
                "1",
                "--",
                str(self.root / "nonexistent"),
            ],
            capture_output=True,
            timeout=5,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            json.loads((self.root / "missing/run.json").read_text())["status"],
            "launch_error",
        )

    def test_no_overwrite_and_changed_input(self):
        result, folder = self.run_command()
        old = digest(folder / "run.json")
        result, _ = self.run_command(output=folder)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(digest(folder / "run.json"), old)
        result, folder = self.run_command(
            "from pathlib import Path; Path('input.sv').write_text('changed')"
        )
        self.assertEqual(result.returncode, 1)
        self.assertFalse(
            json.loads((folder / "run.json").read_text())["inputs_unchanged"]
        )

    def test_timeout_kills_child_workers(self):
        worker = "import time; from pathlib import Path; time.sleep(.6); Path('worker-survived').touch()"
        parent = (
            "import subprocess,sys,time; "
            f"subprocess.Popen([sys.executable, '-c', {worker!r}]); "
            "print('worker launched', flush=True); time.sleep(10)"
        )
        result, folder = self.run_command(parent, timeout=0.3)
        self.assertEqual(result.returncode, 124)
        self.assertIn("worker launched", (folder / "stdout.log").read_text())
        time.sleep(0.7)
        self.assertFalse((self.root / "worker-survived").exists())

    def test_reports_must_be_fresh_and_are_archived(self):
        result, folder = self.run_command(
            "from pathlib import Path; Path('result.txt').write_text('report')",
            extra=["--report", "result.txt"],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((folder / "reports/000-result.txt").read_text(), "report")
        result, _ = self.run_command(extra=["--report", "result.txt"])
        self.assertEqual(result.returncode, 2)
        result, folder = self.run_command(extra=["--report", "absent.txt"])
        self.assertEqual(result.returncode, 1)

    def test_valid_closure_and_unused_unresolved_candidate(self):
        ledger = self.ledger()
        ledger["obligations"].append(
            {
                "id": "unused",
                "statement": "unused",
                "scope": "test",
                "dependencies": [],
                "premises": [],
                "outcome": "failed",
            }
        )
        result = self.inspect(ledger)
        self.assertTrue(result["bookkeeping_ok"], result)
        self.assertEqual(result["formal_validity"], "not_certified")
        self.assertEqual(result["closure"], ["helper", "target"])

    def test_cycles_missing_dependencies_and_unresolved_outcomes(self):
        original = self.ledger()
        ledger = copy.deepcopy(original)
        ledger["obligations"][0]["dependencies"] = ["target"]
        self.assertIn("cycle", str(self.inspect(ledger)["errors"]))
        ledger = copy.deepcopy(original)
        ledger["obligations"][1]["dependencies"] = ["missing"]
        self.assertFalse(self.inspect(ledger)["bookkeeping_ok"])
        for outcome in ["unproved", "failed", "timeout", "bounded", "unknown", "error"]:
            with self.subTest(outcome=outcome):
                ledger = copy.deepcopy(original)
                ledger["obligations"][0]["outcome"] = outcome
                self.assertFalse(self.inspect(ledger)["bookkeeping_ok"])

    def test_stale_inputs_and_tampered_evidence(self):
        ledger = self.ledger()
        self.source.write_text("changed")
        self.assertIn("stale input", str(self.inspect(ledger)["errors"]))
        self.source.write_text("original RTL snapshot\n")
        folder = Path(ledger["obligations"][0]["run"]).parent
        (folder / "stdout.log").write_text("altered report")
        self.assertIn("evidence hash mismatch", str(self.inspect(ledger)["errors"]))

    def test_record_tamper_and_bounded_kind(self):
        original = self.ledger()
        ledger = copy.deepcopy(original)
        ledger["obligations"][1]["proof_kind"] = "bounded"
        self.assertFalse(self.inspect(ledger)["bookkeeping_ok"])
        path = Path(original["obligations"][0]["run"])
        path.write_text(path.read_text() + "\n")
        self.assertIn("record hash mismatch", str(self.inspect(original)["errors"]))

    def test_parent_can_run_before_helper_but_requires_final_validation(self):
        target = self.proved_node("target", ["helper"])
        helper = self.proved_node("helper")
        ledger = {
            "schema_version": 1,
            "target": "target",
            "premises": [],
            "transformations": [],
            "obligations": [target, helper],
        }
        result = self.inspect(ledger)
        self.assertTrue(result["bookkeeping_ok"], result)
        helper["outcome"] = "unproved"
        self.assertFalse(self.inspect(ledger)["bookkeeping_ok"])
        helper["outcome"] = "proved"
        helper["dependencies"] = ["target"]
        self.assertIn("cycle", str(self.inspect(ledger)["errors"]))

    def test_transformation_obligations(self):
        ledger = self.ledger()
        transform = {
            "id": "cut",
            "kind": "cutpoint",
            "description": "synthetic interface relation",
            "applies_to": ["target"],
            "obligations": ["helper"],
        }
        ledger["transformations"] = [transform]
        self.assertTrue(self.inspect(ledger)["bookkeeping_ok"])
        transform["obligations"] = []
        self.assertFalse(self.inspect(ledger)["bookkeeping_ok"])
        transform["obligations"] = ["helper"]
        ledger["obligations"][1]["dependencies"] = []
        self.assertFalse(self.inspect(ledger)["bookkeeping_ok"])

    def test_generated_premise_and_escaping_evidence(self):
        ledger = self.ledger()
        ledger["premises"] = [
            {
                "id": "bad",
                "kind": "generated",
                "statement": "test",
                "source": "agent",
                "scope": "test",
            }
        ]
        self.assertFalse(self.inspect(ledger)["bookkeeping_ok"])
        ledger["premises"] = []
        node = ledger["obligations"][0]
        path = Path(node["run"])
        run = json.loads(path.read_text())
        run["evidence"]["../input.sv"] = digest(self.source)
        path.write_text(json.dumps(run))
        node["run_sha256"] = digest(path)
        self.assertIn("escaping evidence", str(self.inspect(ledger)["errors"]))

    def test_invalid_json_fails_cleanly(self):
        path = self.root / "invalid.json"
        for content in ['{"schema_version":1,"schema_version":1}', '{"x":NaN}', "[]"]:
            path.write_text(content)
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "audit_proof.py"), str(path)],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertFalse(json.loads(result.stdout)["bookkeeping_ok"])
            self.assertNotIn("Traceback", result.stderr)

    def test_template_is_unproved_and_cli_reports_it(self):
        template = SCRIPTS.parent / "assets/proof-ledger.json"
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "audit_proof.py"), str(template)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("unproved", str(json.loads(result.stdout)["errors"]))


if __name__ == "__main__":
    unittest.main()

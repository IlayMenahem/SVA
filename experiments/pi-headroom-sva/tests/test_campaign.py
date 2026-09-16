import tempfile
import unittest
from pathlib import Path

from campaign import audit_replay
from core import (
    EBMC,
    ROOT,
    Pause,
    State,
    atomic_json,
    baseline,
    parse_result,
    read_json,
    task_context,
)
from verifier import Verifier


class CampaignTests(unittest.TestCase):
    def test_baseline_formats(self):
        self.assertEqual(baseline("vcf", "02:24:24")["seconds"], 8664)
        self.assertEqual(baseline("vcf", "TIMEOUT")["outcome"], "timeout")
        self.assertEqual(
            baseline("jasper", {"error": "CEX", "time": None})["outcome"],
            "counterexample",
        )
        self.assertEqual(baseline("ric3", {})["outcome"], "missing")

    def test_parser_rejects_bounded_and_requires_exact_id(self):
        run = {
            "status": "completed",
            "inputs_unchanged": True,
            "errors": [],
            "exit_code": 0,
        }
        report = {
            "properties": [{"identifier": "p", "status": "PROVED up to bound 30"}]
        }
        self.assertEqual(
            parse_result(report, "p", "bounded", run)["outcome"], "bounded"
        )
        self.assertEqual(
            parse_result(report, "other", "bounded", run)["outcome"], "setup_error"
        )
        self.assertEqual(
            parse_result(
                {"properties": [{"identifier": "p", "status": "INCONCLUSIVE"}]},
                "p",
                "k-induction",
                run,
            )["outcome"],
            "induction_failure",
        )

    def test_budget_and_resume_hashes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "input"
            p.write_text("a")
            cfg = {
                "api_cap_usd": "1",
                "campaign_seconds": 10,
                "replay_reserve_seconds": 2,
            }
            s = State(Path(td) / "state")
            s.initialize([p], cfg)
            s.reserve("one", ".6")
            with self.assertRaises(Pause):
                s.reserve("two", ".5")
            s.reconcile("one", ".4", {"input": 1})
            self.assertEqual(s.snapshot()["spent_usd"], "0.4")
            p.write_text("b")
            with self.assertRaises(Pause):
                s.initialize([p], cfg)

    def test_real_ebmc_reset_bounded_and_unbounded(self):
        if not EBMC.exists():
            self.skipTest("EBMC is not built")
        cfg = read_json(ROOT / "config.json")
        with tempfile.TemporaryDirectory() as td:
            task = task_context(ROOT / "tests/fixtures/pass.sv")
            task_dir = Path(td) / "pass"
            unbounded = Verifier(cfg).run(
                task, {}, "target", [], "k-induction", task_dir
            )
            self.assertEqual(unbounded["outcome"], "proved")
            self.assertTrue(
                audit_replay(task, task_dir, {}, [], unbounded)["bookkeeping_ok"]
            )
            bounded = Verifier(cfg).run(
                task, {}, "target", [], "bounded", Path(td) / "bounded"
            )
            self.assertEqual(bounded["outcome"], "bounded")
            failing = task_context(ROOT / "tests/fixtures/fail.sv")
            failed = Verifier(cfg).run(
                failing, {}, "target", [], "k-induction", Path(td) / "fail"
            )
            self.assertEqual(failed["outcome"], "induction_failure")
            failed_bounded = Verifier(cfg).run(
                failing, {}, "target", [], "bounded", Path(td) / "fail-bounded"
            )
            self.assertEqual(failed_bounded["outcome"], "counterexample")

    def test_helper_then_parent_audits(self):
        if not EBMC.exists():
            self.skipTest("EBMC is not built")
        cfg = read_json(ROOT / "config.json")
        task = task_context(ROOT / "tests/fixtures/pass.sv")
        candidates = {
            "safe": {
                "expression": "@(posedge clk) disable iff (rst) bit_state == 1'b0",
                "dependencies": [],
                "includes_target": False,
                "retracted": False,
                "outcome": "unproved",
            }
        }
        with tempfile.TemporaryDirectory() as td:
            task_dir = Path(td) / "task"
            helper = Verifier(cfg).run(
                task, candidates, "safe", [], "k-induction", task_dir
            )
            self.assertEqual(helper["outcome"], "proved")
            candidates["safe"]["outcome"] = "proved"
            parent = Verifier(cfg).run(
                task, candidates, "target", ["safe"], "k-induction", task_dir
            )
            self.assertEqual(parent["outcome"], "proved")
            atomic_json(
                task_dir / "candidates.json",
                {"candidates": candidates, "runs": [helper, parent]},
            )
            self.assertTrue(
                audit_replay(task, task_dir, candidates, ["safe"], parent)[
                    "bookkeeping_ok"
                ]
            )

    def test_model_selected_induction_depth_reaches_ebmc(self):
        if not EBMC.exists():
            self.skipTest("EBMC is not built")
        cfg = read_json(ROOT / "config.json")
        task = task_context(ROOT / "tests/fixtures/two_induction.sv")
        with tempfile.TemporaryDirectory() as td:
            verifier = Verifier(cfg)
            one = verifier.run(
                task, {}, "target", [], "k-induction", Path(td) / "one", bound=1
            )
            self.assertEqual(one["outcome"], "induction_failure")
            two = verifier.run(
                task,
                {},
                "target",
                [],
                "k-induction",
                Path(td) / "two",
                bound=2,
                timeout_seconds=7,
            )
            self.assertEqual(two["outcome"], "proved")
            self.assertEqual(two["bound"], 2)
            self.assertEqual(two["timeout_seconds"], 7)
            replay = verifier.run(
                task,
                {},
                "target",
                [],
                two["mode"],
                Path(td) / "replay",
                bound=two["bound"],
                timeout_seconds=two["timeout_seconds"],
            )
            self.assertEqual(replay["outcome"], "proved")
            self.assertTrue(
                audit_replay(task, Path(td) / "replay", {}, [], replay)[
                    "bookkeeping_ok"
                ]
            )

    def test_bdd_proof_and_invalid_options(self):
        if not EBMC.exists():
            self.skipTest("EBMC is not built")
        cfg = read_json(ROOT / "config.json")
        task = task_context(ROOT / "tests/fixtures/pass.sv")
        with tempfile.TemporaryDirectory() as td:
            verifier = Verifier(cfg)
            result = verifier.run(task, {}, "target", [], "bdd", Path(td) / "bdd")
            self.assertEqual(result["outcome"], "proved")
            self.assertTrue(
                audit_replay(task, Path(td) / "bdd", {}, [], result)["bookkeeping_ok"]
            )
            for options in (
                {"bound": 0},
                {"bound": True},
                {"timeout_seconds": float("inf")},
                {"timeout_seconds": -1},
            ):
                with self.assertRaises(ValueError):
                    verifier.run(
                        task,
                        {},
                        "target",
                        [],
                        "k-induction",
                        Path(td) / "invalid",
                        **options,
                    )
            with self.assertRaises(ValueError):
                verifier.run(
                    task, {}, "target", [], "bdd", Path(td) / "invalid", bound=2
                )


if __name__ == "__main__":
    unittest.main()

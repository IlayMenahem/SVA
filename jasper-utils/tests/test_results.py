"""Tests for jgu.results: time/sample/log parsing, results.json schema, CPU tallies."""

import json
import re
import unittest

from support import TempDirTest

from jgu import results

TIME_KILLED = "Command terminated by signal 15\nJGU_TIME wall=41.78 user=0.07 sys=0.01 maxrss_kb=83952\n"
TIME_DONE = "JGU_TIME wall=33.02 user=30.48 sys=0.16 maxrss_kb=413624\n"
VALID = {
    "properties": [
        {"id": "le9", "kind": "assert", "status": "proven", "engine": "Hp", "assumed": [], "time_s": 0.1},
        {"id": "reach9", "kind": "cover", "status": "covered", "engine": "Ht", "assumed": []},
    ]
}


class Parsing(unittest.TestCase):
    def test_fields_require_the_prefix(self) -> None:
        self.assertEqual(results.parse_fields("JGU_X a=1 b=c=d junk", "JGU_X"), {"a": "1", "b": "c=d"})
        self.assertIsNone(results.parse_fields("JGU_XY a=1", "JGU_X"))

    def test_time_skips_the_gnu_status_line(self) -> None:
        record = results.parse_time(TIME_KILLED)
        self.assertEqual((record.wall_s, record.maxrss_kb), (41.78, 83952))
        self.assertAlmostEqual(record.cpu_s, 0.08)
        self.assertIsNone(results.parse_time("Command exited with non-zero status 1\n"))

    def test_sample_takes_the_last_line(self) -> None:
        text = "JGU_CPUSAMPLE total_cpu_s=1.5 procs=2\nJGU_CPUSAMPLE total_cpu_s=39.47 procs=8\n"
        self.assertEqual(results.parse_sample(text), 39.47)
        self.assertIsNone(results.parse_sample("nothing"))

    def test_log_results(self) -> None:
        log = "noise\nJGU_RESULT tag=node id=le9 kind=assert status=proven engine=Hp time_s=0.1 depth=infinite\n"
        (only,) = results.parse_log_results(log)
        self.assertEqual((only.id, only.status, only.depth), ("le9", "proven", "infinite"))


class Schema(unittest.TestCase):
    def test_valid_document(self) -> None:
        self.assertEqual(results.results_errors(VALID), [])

    def test_each_rule(self) -> None:
        bad = {"properties": [
            {"id": "a", "kind": "assume", "status": "proven", "engine": "Hp", "assumed": []},
            {"id": "a", "kind": "assert", "status": "", "engine": "Hp", "assumed": ["x", "x"]},
            {"id": "b", "kind": "cover", "status": "covered", "engine": "Ht", "assumed": "x", "time_s": "1"},
            "not an object",
        ]}
        errors = "\n".join(results.results_errors(bad))
        for expected in ("properties[0].kind", "properties[1].status", "properties[1].assumed has duplicate",
                         "properties[2].assumed must be", "properties[2].time_s", "properties[3] must be an object",
                         "duplicate property id: a"):
            self.assertIn(expected, errors)
        self.assertEqual(results.results_errors([]), ["results must be an object with a properties list"])


class Cpu(unittest.TestCase):
    def test_effective_cpu_prefers_the_larger_measurement(self) -> None:
        killed, done = results.parse_time(TIME_KILLED), results.parse_time(TIME_DONE)
        self.assertEqual(results.effective_cpu(killed, 39.47), 39.47)
        self.assertAlmostEqual(results.effective_cpu(done, 29.54), 30.64)
        self.assertIsNone(results.effective_cpu(None, None))

    def test_rows_group_by_regex(self) -> None:
        runs = [
            ("disc-001", results.parse_time(TIME_DONE), 29.5),
            ("disc-002", results.parse_time(TIME_KILLED), 39.47),
            ("replay-001", None, None),
        ]
        rows = results.cpu_rows(runs, re.compile(r"^([a-z]+)-"))
        self.assertEqual([r.group for r in rows], ["disc", "replay"])
        disc = rows[0]
        self.assertEqual((disc.runs, disc.untimed), (2, 0))
        self.assertAlmostEqual(disc.effective_cpu_s, 30.64 + 39.47)
        self.assertEqual((rows[1].runs, rows[1].untimed, rows[1].effective_cpu_s), (1, 1, 0))
        total = json.loads(results.format_cpu(rows).splitlines()[-1].split(" ", 1)[1])
        self.assertEqual(total["runs"], 3)
        self.assertAlmostEqual(total["effective_cpu_s"], 70.11)

    def test_without_pattern_everything_is_one_group(self) -> None:
        self.assertEqual([r.group for r in results.cpu_rows([("a", None, None)], None)], ["all"])


class LoadRun(TempDirTest):
    def test_loads_a_fetched_run(self) -> None:
        run = self.tmp / "counter-003"
        self.write("counter-003/exit_code", "0\n")
        self.write("counter-003/time.txt", TIME_DONE)
        self.write("counter-003/cpu_sample.txt", "JGU_CPUSAMPLE total_cpu_s=29.54 procs=9\n")
        self.write("counter-003/results.json", json.dumps(VALID))
        record = results.load_run(run)
        self.assertEqual((record.name, record.exit_code, record.results_errors), ("counter-003", 0, ()))
        summary = results.format_run(record)
        self.assertIn("results=covered:1,proven:1", summary)
        self.assertIn("effective_cpu_s=30.6", summary)
        self.assertIn("results_json=ok", summary)

    def test_reports_missing_and_invalid_results(self) -> None:
        self.write("empty/exit_code", "124\n")
        self.assertIn("results_json=missing", results.format_run(results.load_run(self.tmp / "empty")))
        self.write("bad/results.json", "{")
        self.assertIn("results_json=invalid", results.format_run(results.load_run(self.tmp / "bad")))


if __name__ == "__main__":
    unittest.main()

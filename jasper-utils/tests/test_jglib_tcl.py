"""Run tcl/jglib.tcl in tclsh against stub Jasper commands (skipped without tclsh)."""

import json
import shutil
import subprocess
import unittest

from support import PACKAGE_ROOT, TempDirTest

JGLIB = PACKAGE_ROOT / "tcl" / "jglib.tcl"

STUBS = r"""
set ::calls {}
array set ::status {}
array set ::kind {}
proc short {p} { return [string map {<embedded>:: {}} $p] }
proc declare {kind args} {
    lappend ::calls [list $kind {*}$args]
    if {[lindex $args 0] eq "-name"} {
        set ::kind([lindex $args 1]) $kind
        set ::status([lindex $args 1]) unprocessed
    }
}
proc assert {args} { declare assert {*}$args }
proc assume {args} { declare assume {*}$args }
proc cover {args} { declare cover {*}$args }
foreach command {set_engine_mode set_prove_time_limit set_proofgrid_max_jobs
                 set_proofgrid_per_engine_max_jobs set_proven_directive set_prove_invariants_import
                 stopat} {
    proc $command {args} "lappend ::calls \[list $command {*}\$args\]"
}
proc prove {flag props} {
    lappend ::calls [list prove $flag $props]
    foreach p $props { set ::status([short $p]) [expr {$::kind([short $p]) eq "cover" ? "covered" : "proven"}] }
}
proc get_status {p} { return $::status([short $p]) }
proc get_property_info {p flag field} {
    switch -- $field {
        type { return $::kind([short $p]) }
        engine { return Hp }
        time { return "1.5 s" }
        min_length { return infinite }
        default { error "unknown field $field" }
    }
}
proc get_property_list {flag spec} {
    set type [lindex $spec 1]
    set names {}
    foreach name [lsort [array names ::kind]] {
        if {$::kind($name) eq $type} { lappend names <embedded>::$name }
    }
    return $names
}
"""

SCENARIO = r"""
source {JGLIB}
puts "CAPS [jgu::caps 3]"
jgu::dag_init
jgu::lemma l1 {a}
assert -name {t"x} {b}
cover -name c1 {c}
assert -name l1:precondition1 {d}
cover -name l1:precondition1 {d}
set premise [jgu::rigid {top.k[0]}]
puts "PREMISE $premise"
puts "STATUS [jgu::prove_node l1 {} Hp 60]"
jgu::prove_node {t"x} {l1} N 900 tq [list $premise]
jgu::prove_node c1 {} Ht 30
puts "PRECOVERS [jgu::precondition_covers [list <embedded>::l1]]"
puts "SNAPSHOT [jgu::snapshot [list <embedded>::l1 c1]]"
puts "LIMIT [jgu::limit 900] [jgu::limit 1h]"
puts "SCRIPT_DIR [jgu::script_dir]"
puts "ESCAPED [jgu::json_string "a\"b\\c\nd\te\x01"]"
if {[catch {jgu::record tq assert proven N {}} message]} { puts "DUPLICATE $message" }
foreach call $::calls { puts "CALL $call" }
puts "JSON_BEGIN"
puts -nonewline [jgu::results_json]
puts "JSON_END"
"""


@unittest.skipUnless(shutil.which("tclsh"), "tclsh not installed")
class Jglib(TempDirTest):
    def setUp(self) -> None:
        super().setUp()
        script = self.write("scenario.tcl", STUBS + SCENARIO.replace("{JGLIB}", "{" + str(JGLIB) + "}"))
        env = {"JGU_TCL": str(self.tmp / "formal/run.tcl"), "PATH": "/usr/bin:/bin:/opt/homebrew/bin"}
        run = subprocess.run(["tclsh", str(script)], capture_output=True, text=True, env=env)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.lines = run.stdout.splitlines()

    def value(self, prefix: str) -> str:
        return next(line[len(prefix) + 1:] for line in self.lines if line.startswith(prefix + " "))

    def calls(self) -> list[str]:
        return [line[5:] for line in self.lines if line.startswith("CALL ")]

    def test_results_json_matches_the_skill_schema(self) -> None:
        text = "\n".join(self.lines[self.lines.index("JSON_BEGIN") + 1: self.lines.index("JSON_END")])
        properties = json.loads(text)["properties"]
        self.assertEqual(properties, [
            {"id": "l1", "kind": "assert", "status": "proven", "engine": "Hp", "assumed": [], "time_s": 1.5},
            {"id": "tq", "kind": "assert", "status": "proven", "engine": "Hp",
             "assumed": ["l1", "jgu_rigid_top_k_0_"], "time_s": 1.5},
            {"id": "c1", "kind": "cover", "status": "covered", "engine": "Hp", "assumed": [], "time_s": 1.5},
        ])

    def test_prove_node_enables_only_dependency_twins_around_the_prove(self) -> None:
        calls = self.calls()
        declared_disabled = calls.index("assume -disable l1__twin")
        enable = calls.index("assume -enable l1__twin")
        prove = calls.index(r'prove -property {t\"x}')
        disable = calls.index("assume -disable l1__twin", enable)
        self.assertLess(declared_disabled, enable)
        self.assertLess(enable, prove)
        self.assertLess(prove, disable)
        self.assertEqual(calls.count("assume -enable l1__twin"), 1)
        self.assertIn("set_proven_directive false", calls)
        self.assertIn("set_prove_invariants_import off", calls)
        self.assertIn("set_engine_mode N", calls)
        self.assertIn("set_prove_time_limit 900s", calls)

    def test_setup_helpers(self) -> None:
        self.assertEqual(self.value("CAPS"), "3")
        self.assertIn("set_proofgrid_max_jobs 3", self.calls())
        self.assertIn("assume -name jgu_rigid_top_k_0_ {##1 $stable(top.k[0])}", self.calls())
        self.assertEqual(self.value("STATUS"), "proven")
        self.assertEqual(self.value("PRECOVERS"), "<embedded>::l1:precondition1")
        self.assertEqual(self.value("SNAPSHOT"), "l1 proven c1 covered")
        self.assertEqual(self.value("LIMIT"), "900s 1h")
        self.assertEqual(self.value("SCRIPT_DIR"), str(self.tmp / "formal"))
        self.assertIn("already recorded", self.value("DUPLICATE"))

    def test_report_lines_are_parseable(self) -> None:
        reports = [line for line in self.lines if line.startswith("JGU_RESULT ")]
        self.assertEqual(len(reports), 3)
        self.assertIn("id=t\"x kind=assert status=proven engine=Hp time_s=1.5 depth=infinite", reports[1])

    def test_json_string_escapes(self) -> None:
        self.assertEqual(json.loads(self.value("ESCAPED")), 'a"b\\c\nd\te')


if __name__ == "__main__":
    unittest.main()

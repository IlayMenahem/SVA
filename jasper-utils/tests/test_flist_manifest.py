"""Tests for jgu.flist and jgu.manifest."""

import json
import unittest

from support import TempDirTest

from jgu import flist, manifest


class FileLists(TempDirTest):
    def setUp(self) -> None:
        super().setUp()
        self.write("rtl/a.sv", "")
        self.write("rtl/b.sv", "")
        self.write("rtl/inc/defs.svh", "")
        self.write("lib/cell.v", "")
        self.write("rtl/sub.f", "// nested, relative to this file\nb.sv\n+incdir+inc\n")
        self.write("top.f", "# top list\n${SRC}/a.sv -F rtl/sub.f\n+define+A=1+B\n-v lib/cell.v -sv +libext+.v\n")

    def test_expands_variables_nesting_and_options(self) -> None:
        parsed = flist.parse_flist(self.tmp / "top.f", {"SRC": "rtl"}, self.tmp)
        self.assertEqual(parsed.sources, (self.tmp / "rtl/a.sv", self.tmp / "rtl/b.sv", self.tmp / "lib/cell.v"))
        self.assertEqual(parsed.incdirs, (self.tmp / "rtl/inc",))
        self.assertEqual(parsed.defines, ("A=1", "B"))
        self.assertEqual(parsed.flists, (self.tmp / "top.f", self.tmp / "rtl/sub.f"))
        self.assertEqual(parsed.other, ("-sv", "+libext+.v"))
        self.assertEqual(flist.missing_files(parsed), [])

    def test_lowercase_f_resolves_against_cwd(self) -> None:
        self.write("cwd_rel.f", "-f rtl/plain.f\n")
        self.write("rtl/plain.f", "rtl/a.sv\n")
        parsed = flist.parse_flist(self.tmp / "cwd_rel.f", {}, self.tmp)
        self.assertEqual(parsed.sources, (self.tmp / "rtl/a.sv",))

    def test_unknown_variables_are_errors(self) -> None:
        with self.assertRaisesRegex(ValueError, "SRC"):
            flist.parse_flist(self.tmp / "top.f", {}, self.tmp)

    def test_missing_files_are_reported(self) -> None:
        self.write("missing.f", "nope.sv\n")
        parsed = flist.parse_flist(self.tmp / "missing.f", {}, self.tmp)
        self.assertEqual(flist.missing_files(parsed), [self.tmp / "nope.sv"])


class Manifests(TempDirTest):
    def setUp(self) -> None:
        super().setUp()
        self.write("formal/run.tcl", "")
        self.write("formal/jgproj/ignored.db", "")
        self.write("formal/__pycache__/x.pyc", "")
        self.write("rtl/a.sv", "")
        self.write("rtl/inc/defs.svh", "")
        self.write("rtl/list.f", "a.sv\n+incdir+inc\n")

    def test_collects_dirs_globs_and_file_lists(self) -> None:
        file_lists = [flist.parse_flist(self.tmp / "rtl/list.f", {}, self.tmp, relative_to_file=True)]
        files = manifest.collect_files(self.tmp, ["formal", "rtl/*.sv"], file_lists)
        self.assertEqual(files, ["formal/run.tcl", "rtl/a.sv", "rtl/inc/defs.svh", "rtl/list.f"])

    def test_missing_entries_fail(self) -> None:
        with self.assertRaises(FileNotFoundError):
            manifest.collect_files(self.tmp, ["nope"], [])

    def test_paths_outside_cwd_stay_absolute(self) -> None:
        inner = self.tmp / "formal"
        files = manifest.collect_files(inner, [str(self.tmp / "rtl/a.sv")], [])
        self.assertEqual(files, [str(self.tmp / "rtl/a.sv")])

    def test_build_merges_base(self) -> None:
        base = {"files": ["x.sv"], "settings": {"top": "t", "engine": "old"}}
        built = manifest.build_manifest(["a.sv", "x.sv"], {"engine": "Hp"}, base)
        self.assertEqual(built, {"files": ["a.sv", "x.sv"], "settings": {"top": "t", "engine": "Hp"}})
        with self.assertRaises(ValueError):
            manifest.build_manifest([], {})

    def test_settings_and_round_trip(self) -> None:
        self.assertEqual(manifest.parse_settings(["a=1", "b=x=y", "a=2"]), {"a": "2", "b": "x=y"})
        with self.assertRaises(ValueError):
            manifest.parse_settings(["novalue"])
        path = self.tmp / "out/inputs.json"
        manifest.write_manifest(path, {"files": ["a"], "settings": {}})
        self.assertEqual(manifest.load_manifest(path), json.loads(path.read_text()))


if __name__ == "__main__":
    unittest.main()

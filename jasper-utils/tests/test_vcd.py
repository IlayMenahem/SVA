"""Tests for jgu.vcd on a trace shaped like Jasper's `visualize -save -vcd` output."""

import contextlib
import io
import unittest

from support import TempDirTest

from jgu import vcd

JASPER_VCD = """$date Mon Oct  5 13:58:32 2026
 $end
$version JasperGold $end
$timescale 1 ns $end
$scope module counter $end
$var wire 1 ! :jasper_formal_reset $end
$var wire 1 " rst $end
$var wire 1 # en $end
$var reg 4 % q [3:0] $end
$var wire 1 ' clk $end
$scope module sub $end
$var wire 8 ( data [7:0] $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
0!
0"
1#
b0000 %
1'
bxxxx0001 (
$end
#5
0'
#10
1'
b0001 %
0#
b00000010 (
#15
0'
#20
1'
#25
0'
"""


class Parse(unittest.TestCase):
    def setUp(self) -> None:
        self.trace = vcd.parse_vcd(JASPER_VCD)

    def test_signals_get_full_scope_names(self) -> None:
        names = [(s.name, s.width) for s in self.trace.signals]
        self.assertIn(("counter.q", 4), names)
        self.assertIn(("counter.sub.data", 8), names)

    def test_rising_edges(self) -> None:
        clock = vcd.single_signal(self.trace, vcd.DEFAULT_CLOCK, "clock")
        self.assertEqual(vcd.rising_edges(self.trace, clock), [0, 10, 20])

    def test_table_rows_hold_values_between_edges(self) -> None:
        clock = vcd.single_signal(self.trace, vcd.DEFAULT_CLOCK, "clock")
        signals = vcd.find_signals(self.trace, [r"\.q$", r"\.en$", "data"])
        lines = vcd.table(self.trace, signals, clock).splitlines()
        self.assertEqual(lines[0], "cycle\tcounter.en\tcounter.q\tcounter.sub.data")
        self.assertEqual(lines[1:], ["1\t1\t0x0\txxxx0001", "2\t0\t0x1\t0x02", "3\t0\t0x1\t0x02"])

    def test_radix_and_first_cycle(self) -> None:
        clock = vcd.single_signal(self.trace, vcd.DEFAULT_CLOCK, "clock")
        q = vcd.find_signals(self.trace, [r"\.q$"])
        self.assertEqual(vcd.table(self.trace, q, clock, "dec", first_cycle=0).splitlines()[2], "1\t1")
        self.assertEqual(vcd.table(self.trace, q, clock, "bin").splitlines()[2], "2\t0001")

    def test_clock_pattern_must_match_one_signal(self) -> None:
        with self.assertRaises(ValueError):
            vcd.single_signal(self.trace, "counter", "clock")

    def test_rejects_non_vcd(self) -> None:
        with self.assertRaises(ValueError):
            vcd.parse_vcd("hello")


class FormatValue(unittest.TestCase):
    def test_values(self) -> None:
        self.assertEqual(vcd.format_value("1", 1, "hex"), "1")
        self.assertEqual(vcd.format_value("101", 12, "hex"), "0x005")
        self.assertEqual(vcd.format_value("1x1", 3, "hex"), "1x1")


class Cli(TempDirTest):
    def test_jgu_vcd_lists_signals(self) -> None:
        from jgu.cli import main

        path = self.write("t.vcd", JASPER_VCD)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            self.assertEqual(main(["vcd", str(path), "--list"]), 0)
        self.assertIn("counter.sub.data\t8", printed.getvalue())


if __name__ == "__main__":
    unittest.main()

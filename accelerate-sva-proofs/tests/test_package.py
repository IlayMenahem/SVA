"""Check installable package references without external dependencies."""

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Package(unittest.TestCase):
    def test_local_markdown_links_resolve(self):
        for document in ROOT.rglob("*.md"):
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", document.read_text()):
                if "://" not in target and not target.startswith("#"):
                    with self.subTest(document=document.name, target=target):
                        self.assertTrue((document.parent / target.split("#")[0]).is_file())

    def test_json_assets_parse_and_start_unproved(self):
        ledger = json.loads((ROOT / "assets/proof-ledger.json").read_text())
        self.assertEqual(ledger["schema_version"], 1)
        self.assertTrue(all(node["outcome"] == "unproved" for node in ledger["obligations"]))


if __name__ == "__main__":
    unittest.main()

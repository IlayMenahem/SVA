from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import digest

ebmc = ROOT / "vendor/hw-cbmc/src/ebmc/ebmc"


def output(*args):
    return subprocess.check_output(args, text=True).strip()


data = {
    "platform": platform.platform(),
    "machine": platform.machine(),
    "ebmc_version": output(str(ebmc), "--version"),
    "ebmc_sha256": digest(ebmc),
    "ebmc_git": output(
        "git",
        "-C",
        str(ROOT / "vendor/hw-cbmc"),
        "describe",
        "--tags",
        "--always",
        "--dirty",
    ),
    "cbmc_submodule": output(
        "git", "-C", str(ROOT / "vendor/hw-cbmc"), "submodule", "status", "lib/cbmc"
    ),
    "build_command": "make -C vendor/hw-cbmc/src -j2 YACC=/opt/homebrew/opt/bison/bin/bison LEX=/opt/homebrew/opt/flex/bin/flex",
    "bison": output("/opt/homebrew/opt/bison/bin/bison", "--version").splitlines()[0],
    "flex": output("/opt/homebrew/opt/flex/bin/flex", "--version"),
    "node": output("node", "--version"),
    "pi_package": "@earendil-works/pi-coding-agent@0.85.1",
    "headroom_python": "headroom-ai[proxy]==0.37.0",
    "headroom_typescript": "headroom-ai@0.37.0",
}
(ROOT / "setup/setup.json").write_text(json.dumps(data, indent=2) + "\n")
print(json.dumps(data, indent=2))

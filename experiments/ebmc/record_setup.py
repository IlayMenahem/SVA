from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "pi"))
from core import digest

ebmc = ROOT / "hw-cbmc/src/ebmc/ebmc"


def output(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


data = {
    "platform": platform.platform(),
    "machine": platform.machine(),
    "ebmc_version": output(str(ebmc), "--version"),
    "ebmc_sha256": digest(ebmc),
    "ebmc_git": output(
        "git",
        "-C",
        str(ROOT / "hw-cbmc"),
        "describe",
        "--tags",
        "--always",
        "--dirty",
    ),
    "cbmc_submodule": output(
        "git", "-C", str(ROOT / "hw-cbmc"), "submodule", "status", "lib/cbmc"
    ),
    "build_command": "make -C ebmc/hw-cbmc/src -j2 YACC=/opt/homebrew/opt/bison/bin/bison LEX=/opt/homebrew/opt/flex/bin/flex",
    "bison": output("/opt/homebrew/opt/bison/bin/bison", "--version").splitlines()[0],
    "flex": output("/opt/homebrew/opt/flex/bin/flex", "--version"),
    "node": output("node", "--version"),
    "pi_package": "@earendil-works/pi-coding-agent@0.85.1",
    "context_compression": "lean-ctx",
    "lean_ctx_version": output(
        os.environ.get("LEAN_CTX_BIN")
        or (
            "/opt/homebrew/bin/lean-ctx"
            if Path("/opt/homebrew/bin/lean-ctx").exists()
            else "lean-ctx"
        ),
        "--version",
    ),
}
(ROOT / "setup.json").write_text(json.dumps(data, indent=2) + "\n")
print(json.dumps(data, indent=2))

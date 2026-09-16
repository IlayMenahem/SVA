"""Check actual Pi tool registration without sending a model request."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path = [str(ROOT)] + [p for p in sys.path if Path(p).resolve() != ROOT / "setup"]
import json
import subprocess
import tempfile

from core import State, read_json

with tempfile.TemporaryDirectory(prefix="sva-interface-") as directory:
    run = Path(directory)
    cfg = read_json(ROOT / "config-ex3-glm53-high.json")
    State(run).initialize([], cfg)
    env = {
        **os.environ,
        "PI_CODING_AGENT_DIR": str(ROOT / "pi-config"),
        "PI_OFFLINE": "1",
        "PI_SKIP_VERSION_CHECK": "1",
        "PI_TELEMETRY": "0",
        "SVA_RUN_ROOT": str(run),
        "SVA_TASK_ID": "ex3",
    }
    cmd = [
        str(ROOT / "node_modules/.bin/pi"),
        "--mode",
        "rpc",
        "--provider",
        "openrouter",
        "--model",
        cfg["model"],
        "--session-dir",
        str(run / "session"),
        "-e",
        str(ROOT / "pi-extension.ts"),
        "--no-context-files",
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=run,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = proc.communicate(
            json.dumps({"id": "state", "type": "get_state"}) + "\n", timeout=15
        )
    except subprocess.TimeoutExpired:
        proc.terminate()
        stdout, stderr = proc.communicate(timeout=5)
    records = [json.loads(line) for line in stdout.splitlines() if line.startswith("{")]
    errors = [r for r in records if r.get("type") == "extension_error"]
    if errors:
        raise SystemExit(json.dumps(errors))
    interface = read_json(run / "tasks/ex3/interface.json")
    required = {
        "read",
        "write",
        "edit",
        "bash",
        "grep",
        "find",
        "ls",
        "read_task",
        "submit_candidate",
        "invoke_ebmc",
        "inspect_evidence",
        "retract_candidate",
    }
    missing = required - set(interface["tools"])
    if missing:
        raise SystemExit("Missing tools: " + str(missing))
    if interface["thinking"] != "high":
        raise SystemExit("Thinking setting was not applied")
    print(json.dumps(interface, indent=2))

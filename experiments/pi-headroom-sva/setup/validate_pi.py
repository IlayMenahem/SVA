from __future__ import annotations

import json
import os
import select
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
run = ROOT / "runs/pi-validation"
(run / "session").mkdir(parents=True, exist_ok=True)
env = {
    **os.environ,
    "OPENROUTER_API_KEY": "validation-placeholder",
    "PI_CODING_AGENT_DIR": str(ROOT / "pi-config"),
    "PI_CODING_AGENT_SESSION_DIR": str(run / "session"),
    "PI_OFFLINE": "1",
    "PI_SKIP_VERSION_CHECK": "1",
    "PI_TELEMETRY": "0",
    "SVA_RUN_ROOT": str(ROOT / "runs/audit"),
    "SVA_TASK_ID": "ex3",
}
cmd = [
    str(ROOT / "node_modules/.bin/pi"),
    "--mode",
    "rpc",
    "--provider",
    "openrouter",
    "--model",
    "google/gemini-3.8-flash",
    "--session-dir",
    str(run / "session"),
    "-e",
    str(ROOT / "pi-extension.ts"),
    "--no-context-files",
]
p = subprocess.Popen(
    cmd,
    cwd=ROOT,
    env=env,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    start_new_session=True,
)
try:
    p.stdin.write(
        json.dumps({"id": "state", "type": "get_state"})
        + "\n"
        + json.dumps({"id": "compact", "type": "set_auto_compaction", "enabled": False})
        + "\n"
    )
    p.stdin.flush()
    records = []
    deadline = time.time() + 15
    while (
        time.time() < deadline
        and len([r for r in records if r.get("type") == "response"]) < 2
    ):
        ready, _, _ = select.select([p.stdout], [], [], 0.5)
        if ready:
            line = p.stdout.readline()
            if line:
                records.append(json.loads(line))
    errors = [r for r in records if r.get("type") == "extension_error"]
    responses = {r.get("id"): r for r in records if r.get("type") == "response"}
    if (
        errors
        or not responses.get("state", {}).get("success")
        or not responses.get("compact", {}).get("success")
    ):
        raise RuntimeError(json.dumps({"records": records, "stderr": p.stderr.read()}))
    result = {
        "pi_rpc": True,
        "extension_loaded": True,
        "auto_compaction_disabled": True,
        "model": responses["state"].get("data", {}).get("model"),
    }
    (ROOT / "setup/pi-validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
finally:
    p.terminate()
    try:
        p.wait(5)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()

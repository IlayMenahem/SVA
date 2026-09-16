import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
models = json.loads((root / "setup/openrouter-models.json").read_text())["data"]
model = next((m for m in models if m["id"] == "google/gemini-3.8-flash"), None)
lean_ctx = shutil.which("lean-ctx") or "/opt/homebrew/bin/lean-ctx"
lean_ctx_version = subprocess.check_output([lean_ctx, "--version"], text=True).strip()
info = {
    "platform": platform.platform(),
    "machine": platform.machine(),
    "node": shutil.which("node"),
    "credential_present": bool(os.getenv("OPENROUTER_API_KEY")),
    "context_compression": "lean-ctx",
    "lean_ctx_version": lean_ctx_version,
    "model": model,
}
(root / "setup/preflight.json").write_text(json.dumps(info, indent=2) + "\n")
print(json.dumps(info, indent=2))

import json
import os
import platform
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
pypi = json.loads(Path("/tmp/sva-headroom-pypi.json").read_text())["info"]
models = json.loads((root / "setup/openrouter-models.json").read_text())["data"]
model = next((m for m in models if m["id"] == "google/gemini-3.8-flash"), None)
info = {
    "platform": platform.platform(),
    "machine": platform.machine(),
    "node": shutil.which("node"),
    "credential_present": bool(os.getenv("OPENROUTER_API_KEY")),
    "headroom_version": pypi["version"],
    "headroom_python": pypi["requires_python"],
    "model": model,
}
(root / "setup/preflight.json").write_text(json.dumps(info, indent=2) + "\n")
print(json.dumps(info, indent=2))

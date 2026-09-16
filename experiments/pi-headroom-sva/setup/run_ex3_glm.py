"""Load only the API credential as data, then run the isolated ex3 experiment."""

import os
import runpy
import shlex
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
for line in (root / ".env").read_text().splitlines():
    line = line.strip().removeprefix("export ")
    name, sep, value = line.partition("=")
    if sep and name.strip() == "OPENROUTER_API_KEY":
        parts = shlex.split(value, comments=True)
        if len(parts) != 1:
            raise SystemExit("Invalid OPENROUTER_API_KEY entry in .env")
        os.environ["OPENROUTER_API_KEY"] = parts[0]
        break
if not os.environ.get("OPENROUTER_API_KEY"):
    raise SystemExit("No API credential found")
os.chdir(root)
sys.path = [str(root)] + [p for p in sys.path if Path(p).resolve() != root / "setup"]
run_root = sys.argv[1] if len(sys.argv) > 1 else "runs/ex3-glm53-high"
sys.argv = [
    "campaign.py",
    "run",
    "--config",
    "config-ex3-glm53-high.json",
    "--run-root",
    run_root,
]
runpy.run_path(str(root / "campaign.py"), run_name="__main__")

import json
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "runs/ex3-glm53-high-retry"
s = json.loads((root / "checkpoint.json").read_text())
print(json.dumps({k: s.get(k) for k in ("status", "spent_usd", "tasks")}, indent=2))
print("Completed requests:", len(s["charges"]))
print("Elapsed seconds:", round(time.time() - s["started_at"]))
print(
    "Reasoning tokens:",
    sum(c.get("usage", {}).get("reasoning", 0) for c in s["charges"]),
)
p = root / "tasks/ex3/candidates.json"
if p.exists():
    data = json.loads(p.read_text())
    print(json.dumps(data, indent=2))
for p in sorted((root / "requests").glob("*.json"))[:1]:
    print("Request settings:", p.read_text())

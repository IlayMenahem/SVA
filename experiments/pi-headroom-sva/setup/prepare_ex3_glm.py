"""Prepare a single-task GLM 5.3 high-thinking configuration."""

import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
cfg = json.loads((root / "config.json").read_text())
cfg.update(
    model="z-ai/glm-5.3",
    thinking="high",
    task="ex3",
    workers=1,
    campaign_seconds=1020,
    replay_reserve_seconds=300,
    max_prompt_usd_per_million="1.4",
    max_completion_usd_per_million="4.4",
)
(root / "config-ex3-glm53-high.json").write_text(json.dumps(cfg, indent=2) + "\n")
path = root / "pi-config/models.json"
models = json.loads(path.read_text())
entries = models["providers"]["openrouter"]["models"]
if not any(m["id"] == cfg["model"] for m in entries):
    entries.append(
        {
            "id": cfg["model"],
            "name": "GLM 5.3",
            "reasoning": True,
            "input": ["text"],
            "contextWindow": 202752,
            "maxTokens": 16384,
            "cost": {"input": 1.4, "output": 4.4, "cacheRead": 0.26, "cacheWrite": 0},
        }
    )
    path.write_text(json.dumps(models, indent=2) + "\n")
print("Prepared ex3: z-ai/glm-5.3, reasoning effort high, 720-second discovery budget.")

import json
import os
import urllib.request

print("credential_present:", bool(os.getenv("OPENROUTER_API_KEY")))
with urllib.request.urlopen(
    "https://openrouter.ai/api/v1/models", timeout=30
) as response:
    models = json.load(response)["data"]
print(
    json.dumps(
        [
            {
                k: m.get(k)
                for k in ("id", "pricing", "reasoning", "supported_parameters")
            }
            for m in models
            if "glm-5.3" in m["id"]
        ],
        indent=2,
    )
)

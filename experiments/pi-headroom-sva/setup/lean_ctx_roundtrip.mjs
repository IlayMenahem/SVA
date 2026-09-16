import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";

const leanCtxBin =
  process.env.LEAN_CTX_BIN ||
  (existsSync("/opt/homebrew/bin/lean-ctx")
    ? "/opt/homebrew/bin/lean-ctx"
    : "lean-ctx");

const rows = Array.from({ length: 700 }, (_, i) => ({
  cycle: i,
  status: "diagnostic",
  warning: "repeated wide arithmetic cone",
  signal: "counter_state",
  value: i % 4,
}));

const original = JSON.stringify({ tool: "inspect_evidence", rows }, null, 2);

const started = performance.now();
const proc = spawnSync(leanCtxBin, ["-c", "cat"], {
  input: original,
  encoding: "utf8",
  maxBuffer: 64 * 1024 * 1024,
});
const latency_ms = performance.now() - started;

if (proc.status !== 0 || !proc.stdout) {
  throw new Error(proc.stderr || "lean-ctx compression failed");
}

const compressed = proc.stdout;
writeFileSync("setup/lean-ctx-roundtrip-original.txt", original);
writeFileSync("setup/lean-ctx-roundtrip-compressed.txt", compressed);
const retrieved = readFileSync("setup/lean-ctx-roundtrip-original.txt", "utf8");

const tokensBefore = original.trim().split(/\s+/).length;
const tokensAfter = compressed.trim().split(/\s+/).length;
const stats = {
  tokens_before: tokensBefore,
  tokens_after: tokensAfter,
  latency_ms,
  compressed: tokensAfter < tokensBefore,
  exact_original_retrieval: retrieved === original,
};

writeFileSync(
  "setup/lean-ctx-roundtrip.json",
  JSON.stringify(stats, null, 2) + "\n"
);

if (!stats.compressed || !stats.exact_original_retrieval) {
  throw new Error(JSON.stringify(stats));
}

console.log(JSON.stringify(stats));

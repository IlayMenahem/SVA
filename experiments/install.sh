#!/usr/bin/env bash
# Idempotent setup: EBMC 6.0, the Pi harness, and the Large Lemma Miners benchmarks.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EBMC_DIR="$HERE/ebmc/hw-cbmc"
EBMC_TAG="ebmc-6.0"
BENCH_DIR="$HERE/../datasets/raw/large-lemma-miners"
BENCH_REV="ffc5b03e28b7b352621ff4811fa1dfd4edfad989"
BREW="${HOMEBREW_PREFIX:-/opt/homebrew}"

install_brew_deps() {
  local missing=()
  for pkg in bison flex node uv; do
    brew list --versions "$pkg" >/dev/null || missing+=("$pkg")
  done
  if ((${#missing[@]})); then brew install "${missing[@]}"; fi
  command -v lean-ctx >/dev/null || [[ -x "$BREW/bin/lean-ctx" ]] ||
    echo "warning: lean-ctx not found; install it before running campaigns" >&2
}

install_ebmc() {
  [[ -d "$EBMC_DIR/.git" ]] ||
    git clone --branch "$EBMC_TAG" --depth 1 https://github.com/diffblue/hw-cbmc.git "$EBMC_DIR"
  git -C "$EBMC_DIR" submodule update --init --recursive
  make -C "$EBMC_DIR/src" -j2 YACC="$BREW/opt/bison/bin/bison" LEX="$BREW/opt/flex/bin/flex" \
    >"$HERE/ebmc/build.log" 2>&1
  "$EBMC_DIR/src/ebmc/ebmc" --version
}

install_pi() {
  (cd "$HERE/pi" && npm ci && uv sync --frozen)
}

install_benchmarks() {
  [[ -d "$BENCH_DIR/.git" ]] ||
    git clone https://github.com/TechnionFV/large_lemma_miners.git "$BENCH_DIR"
  git -C "$BENCH_DIR" checkout --quiet "$BENCH_REV"
}

install_brew_deps
install_ebmc
install_pi
install_benchmarks
"$HERE/pi/.venv/bin/python" "$HERE/ebmc/record_setup.py" >/dev/null
echo "setup recorded in ebmc/setup.json"

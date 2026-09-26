#!/bin/sh
# Usage (on vlsi): sh kill_mine.sh <dir substring>
# Kills only this run's Jasper processes (console, session, engines), identified by working directory.
for p in $(pgrep -u "$(id -un)"); do
  if readlink "/proc/$p/cwd" 2>/dev/null | grep -q "$1"; then kill -9 "$p"; fi
done

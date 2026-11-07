#!/usr/bin/env bash
set -euo pipefail
cd /workspace/Radar
# Existing checkout is already isolated. Never create a worktree during setup.
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -c 'import tkinter, numpy, faster_whisper, opentimelineio'
command -v ffmpeg
command -v ffprobe
# Optional editor integration, pinned official release with checksum verification.
if [ ! -x /workspace/tools/filmcraft/bin/filmcraft-cli ]; then
  task_tmp=$(mktemp -d)
  trap 'rm -rf "$task_tmp"' EXIT
  curl -fsSL https://github.com/storytold/filmcraft/releases/download/v0.18.0/filmcraft-0.18.0-linux-x86_64.tar.gz -o "$task_tmp/filmcraft-0.18.0-linux-x86_64.tar.gz"
  curl -fsSL https://github.com/storytold/filmcraft/releases/download/v0.18.0/SHA256SUMS.txt -o "$task_tmp/SHA256SUMS.txt"
  .venv/bin/python - "$task_tmp" <<'PY'
from pathlib import Path
import hashlib, sys
folder = Path(sys.argv[1])
name = 'filmcraft-0.18.0-linux-x86_64.tar.gz'
expected = next(line.split()[0] for line in (folder / 'SHA256SUMS.txt').read_text().splitlines() if line.endswith(name))
assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == expected, 'FilmCraft checksum mismatch'
PY
  mkdir -p /workspace/tools/filmcraft
  tar -xzf "$task_tmp/filmcraft-0.18.0-linux-x86_64.tar.gz" -C /workspace/tools/filmcraft --strip-components=1
fi
export FILMCRAFT_CLI=/workspace/tools/filmcraft/bin/filmcraft-cli
.venv/bin/python -c 'import os; from radar.filmcraft import capabilities; capabilities(os.environ["FILMCRAFT_CLI"])'
.venv/bin/python -m radar --help
# No model download here: basic audiovisual mode works offline. See README for model provisioning.

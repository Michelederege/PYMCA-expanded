#!/bin/sh
# One-command build. On Windows this still works from Git Bash; otherwise run: python build.py
set -eu
cd "$(dirname "$0")"
exec python3 build.py

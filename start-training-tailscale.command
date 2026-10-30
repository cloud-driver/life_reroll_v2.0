#!/bin/zsh
set -eu
cd "${0:A:h}"
exec ./backend/.venv/bin/python scripts/training-tailscale.py

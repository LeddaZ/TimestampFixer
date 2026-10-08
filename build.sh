#!/bin/sh
# Rebuild dist/TimestampFixer (Linux) or dist/TimestampFixer.app (macOS) from source.
cd "$(dirname "$0")" || exit 1
exec .venv/bin/python -m PyInstaller --noconfirm TimestampFixer.spec

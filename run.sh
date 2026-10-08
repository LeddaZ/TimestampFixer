#!/bin/sh
# Launch the GUI using the project's virtual environment.
dir=$(dirname "$0")
exec "$dir/.venv/bin/python" "$dir/main.py"

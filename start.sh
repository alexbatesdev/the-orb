#!/usr/bin/env bash
set -eu

if [ "$#" -gt 0 ]; then
    case "$1" in
        -h|--help)
            if [ "$#" -eq 1 ]; then
                echo "Usage: bash start.sh"
                echo "Starts the Discord bot using the project .venv, if present."
                exit 0
            fi
            ;;
    esac
    echo "Usage: bash start.sh" >&2
    exit 2
fi

cd -- "$(dirname -- "$0")"

if [ -x .venv/bin/python ]; then
    exec .venv/bin/python -m wisest_wizard
elif [ -x .venv/Scripts/python.exe ]; then
    exec .venv/Scripts/python.exe -m wisest_wizard
elif command -v python3 >/dev/null 2>&1; then
    exec python3 -m wisest_wizard
elif command -v python >/dev/null 2>&1; then
    exec python -m wisest_wizard
else
    echo "Python not found. Install Python 3.12 or newer and the project dependencies." >&2
    exit 1
fi

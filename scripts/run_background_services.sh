#!/bin/zsh
cd "/Users/adarshupadhyay/Documents/New project" || exit 1
export PYTHONPATH=.
export DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib
exec .venv/bin/python scripts/run_background_services.py >> .tmp/background.log 2>&1

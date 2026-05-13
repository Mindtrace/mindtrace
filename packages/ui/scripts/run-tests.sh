#!/bin/bash
#
# Vitest runner for @mindtrace/ui. Lives inside the package so the
# package stays portable — works the same whether it's invoked via
# `npm test`, from the monorepo via `ds test_ui`, or in a CI pipeline
# that just clones this directory.
#
# Usage (from this directory or via wrappers):
#   bash scripts/run-tests.sh                     # run once
#   bash scripts/run-tests.sh --watch             # watch mode
#   bash scripts/run-tests.sh --coverage          # coverage report
#   bash scripts/run-tests.sh src/components/...  # specific path
#
# `--unit` / `--integration` / `--stress` are accepted for parity with
# the Python suite (when launched via `ds test_ui`) but no-op here.

set -e

# Move to the package directory regardless of where this script is invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PACKAGE_DIR"

if [ ! -d node_modules ]; then
    echo "Installing @mindtrace/ui dependencies..."
    npm install --silent
fi

ARGS=()
WATCH=false
COVERAGE=false
for arg in "$@"; do
    case "$arg" in
        --unit | --integration | --stress | --utils) ;;  # Python-suite flags; no-op here.
        --watch) WATCH=true ;;
        --coverage) COVERAGE=true ;;
        *) ARGS+=("$arg") ;;
    esac
done

if [ "$WATCH" = true ]; then
    exec npx vitest "${ARGS[@]}"
elif [ "$COVERAGE" = true ]; then
    exec npx vitest run --coverage "${ARGS[@]}"
else
    exec npx vitest run "${ARGS[@]}"
fi

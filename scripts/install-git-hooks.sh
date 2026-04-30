#!/usr/bin/env bash

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"

chmod +x "${repo_root}/.githooks/pre-push"

git -C "${repo_root}" config core.hooksPath .githooks

echo "Git hooks path set to .githooks"
echo "The pre-push hook will now run before every push."

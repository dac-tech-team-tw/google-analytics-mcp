#!/usr/bin/env bash

set -euo pipefail

RULESET_NAME="${RULESET_NAME:-protect-main-with-pr}"
TARGET_BRANCH="${TARGET_BRANCH:-main}"
REPO_SLUG="${REPO_SLUG:-}"
API_VERSION="${GITHUB_API_VERSION:-2026-03-10}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

parse_repo_slug() {
  local remote_url

  remote_url="$(git remote get-url origin)"

  case "$remote_url" in
    git@github.com:*.git)
      printf '%s\n' "${remote_url#git@github.com:}" | sed 's/\.git$//'
      ;;
    https://github.com/*.git)
      printf '%s\n' "${remote_url#https://github.com/}" | sed 's/\.git$//'
      ;;
    https://github.com/*)
      printf '%s\n' "${remote_url#https://github.com/}"
      ;;
    *)
      echo "Unsupported origin remote: $remote_url" >&2
      exit 1
      ;;
  esac
}

require_command git
require_command gh
require_command mktemp
require_command sed

if ! gh auth status >/dev/null 2>&1; then
  echo "gh is not authenticated. Run: gh auth login -h github.com" >&2
  exit 1
fi

if [[ -z "$REPO_SLUG" ]]; then
  REPO_SLUG="$(parse_repo_slug)"
fi

tmp_json="$(mktemp)"
trap 'rm -f "$tmp_json"' EXIT

cat >"$tmp_json" <<JSON
{
  "name": "${RULESET_NAME}",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": {
    "ref_name": {
      "include": ["refs/heads/${TARGET_BRANCH}"],
      "exclude": []
    }
  },
  "rules": [
    {
      "type": "pull_request",
      "parameters": {
        "allowed_merge_methods": ["merge", "squash", "rebase"],
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_approving_review_count": 0,
        "required_review_thread_resolution": false
      }
    },
    {
      "type": "non_fast_forward"
    },
    {
      "type": "deletion"
    }
  ]
}
JSON

existing_id="$(
  gh api \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: ${API_VERSION}" \
    "repos/${REPO_SLUG}/rulesets" \
    --jq ".[] | select(.name == \"${RULESET_NAME}\") | .id" \
    | head -n 1
)"

if [[ -n "$existing_id" ]]; then
  echo "Updating existing ruleset '${RULESET_NAME}' on ${REPO_SLUG} (id: ${existing_id})"
  gh api \
    --method PUT \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: ${API_VERSION}" \
    "repos/${REPO_SLUG}/rulesets/${existing_id}" \
    --input "$tmp_json"
else
  echo "Creating ruleset '${RULESET_NAME}' on ${REPO_SLUG}"
  gh api \
    --method POST \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: ${API_VERSION}" \
    "repos/${REPO_SLUG}/rulesets" \
    --input "$tmp_json"
fi


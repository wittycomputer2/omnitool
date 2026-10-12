#!/usr/bin/env bash
# Run from a terminal with GitHub network access and gh authentication.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v gh >/dev/null || { echo 'Install GitHub CLI (gh) before publishing.' >&2; exit 1; }
sha256sum -c scripts/OmniTool-v3.2.0.sha256
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    echo 'Commit tracked changes before publishing.' >&2
    exit 1
fi

gh auth status
git push origin HEAD:main
gh release create v3.2.0 \
    OmniTool-x86_64.AppImage \
    scripts/OmniTool-v3.2.0.sha256 \
    --repo wittycomputer2/omnitool \
    --target "$(git rev-parse HEAD)" \
    --title 'OmniTool v3.2.0' \
    --notes-file scripts/RELEASE_NOTES_v3.2.0.md

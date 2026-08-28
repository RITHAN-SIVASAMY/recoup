#!/usr/bin/env bash
# Swap the local-path docs submodule for the public GitHub remotes.
# Run once, after creating both repositories on GitHub.
#
#   ./scripts/link-remotes.sh <github-username>
set -euo pipefail
USER="${1:?usage: link-remotes.sh <github-username>}"

git -C docs remote add origin "https://github.com/${USER}/recoup-docs.git" 2>/dev/null \
  || git -C docs remote set-url origin "https://github.com/${USER}/recoup-docs.git"
git -C docs branch -M main
git -C docs push -u origin main

git config -f .gitmodules submodule.docs.url "https://github.com/${USER}/recoup-docs.git"
git submodule sync docs

git remote add origin "https://github.com/${USER}/recoup.git" 2>/dev/null \
  || git remote set-url origin "https://github.com/${USER}/recoup.git"
git branch -M main
git add .gitmodules && git commit -m "chore(docs): point submodule at the public remote" || true
git push -u origin main

echo "✓ both repositories are now public remotes; clone with --recurse-submodules"

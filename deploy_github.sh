#!/usr/bin/env bash
set -euo pipefail

GITHUB_REPO="https://github.com/Alan116642/g9-dashboard.git"

echo "Publishing G9 dashboard to GitHub..."

git config user.name "G9-Analytics"
git config user.email "g9@analytics.dev"

git add dashboard/ src/ data_demo/ requirements.txt .gitignore README.md deploy_github.sh run.py
git commit -m "Update G9 dashboard deployment files" || true

git remote remove origin 2>/dev/null || true
git remote add origin "$GITHUB_REPO"
git branch -M main
git push -u origin main

echo "Done: $GITHUB_REPO"

#!/usr/bin/env bash
set -euo pipefail

# -----------------------------
# EDIT THESE TWO PATHS
# -----------------------------

# Where your Python script saves the daily maps
SOURCE_DIR="/c/Users/ehakm/OneDrive/Documents/Sankey/Corn Map"

# Your local clone of the GitHub repo
REPO_DIR="/c/Users/ehakm/Documents/ELHApp-backend"

# Target files inside the repo
TARGET_DIR="$REPO_DIR/static_data"
TARGET_WITH_SPACE="$TARGET_DIR/Current Basis.html"
TARGET_NO_SPACE="$TARGET_DIR/Current_Basis.html"   # recommended

# -----------------------------
# DO NOT EDIT BELOW (unless you want to)
# -----------------------------

echo "==> Finding newest ethanol_map_*.html in: $SOURCE_DIR"
LATEST_FILE="$(ls -t "$SOURCE_DIR"/ethanol_map_*.html 2>/dev/null | head -n 1 || true)"

if [[ -z "${LATEST_FILE}" ]]; then
  echo "ERROR: No files found matching: $SOURCE_DIR/ethanol_map_*.html"
  exit 1
fi

echo "==> Latest file: $LATEST_FILE"

# Basic sanity check: ensure it's real HTML (Folium output)
if ! head -n 5 "$LATEST_FILE" | grep -qiE '<!DOCTYPE html>|<html'; then
  echo "ERROR: Latest file does not look like full HTML (missing <!DOCTYPE html> or <html>)."
  echo "Refusing to publish. Check the source file content."
  exit 1
fi

echo "==> Copying into repo..."
mkdir -p "$TARGET_DIR"
cp -f "$LATEST_FILE" "$TARGET_WITH_SPACE"
cp -f "$LATEST_FILE" "$TARGET_NO_SPACE"

echo "==> Committing + pushing..."
cd "$REPO_DIR"

git add "static_data/Current Basis.html" "static_data/Current_Basis.html"

# If nothing changed, exit cleanly
if git diff --cached --quiet; then
  echo "No changes detected. Nothing to commit."
  exit 0
fi

STAMP="$(date +"%Y-%m-%d %H:%M")"
git commit -m "Update Current Basis map ($STAMP)"
git push

echo "==> Done."
echo "Pages (no-space link): https://ehakmiller.github.io/ELHApp-backend/static_data/Current_Basis.html"
echo "Pages (space link):    https://ehakmiller.github.io/ELHApp-backend/static_data/Current%20Basis.html"

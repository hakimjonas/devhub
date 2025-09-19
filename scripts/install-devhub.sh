#!/usr/bin/env bash
# DevHub Quick Installer
# Run with: curl -sSL https://devhub.io/install.sh | bash

set -e

REPO_URL="https://github.com/hakimjonas/devhub.git"
TEMP_DIR=$(mktemp -d)

echo "DevHub Quick Installer"
echo "======================"
echo ""

# Clone the repository
echo "→ Downloading DevHub..."
git clone --quiet --depth 1 "$REPO_URL" "$TEMP_DIR/devhub" 2>/dev/null || {
    echo "Error: Failed to download DevHub"
    exit 1
}

# Run the installer
cd "$TEMP_DIR/devhub"
bash install.sh

# Cleanup
cd "$HOME"
rm -rf "$TEMP_DIR"
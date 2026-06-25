#!/usr/bin/env bash
# OverCR Release Packaging Script
# Creates clean tar.gz and zip archives from the source tree,
# excluding runtime state, task files, audit logs, and packaging artifacts.
#
# Usage:
#   ./scripts/package_release.sh [version]
#
# Examples:
#   ./scripts/package_release.sh          # uses version from runtime/__init__.py
#   ./scripts/package_release.sh 0.2.4   # explicit version
#
# Output:
#   dist/overcr-<version>.tar.gz
#   dist/overcr-<version>.zip

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION="${1:-}"

# Auto-detect version from runtime/__init__.py if not specified
if [ -z "$VERSION" ]; then
    VERSION="$(python3 -c "
import sys
sys.path.insert(0, '$ROOT')
from runtime import __version__
print(__version__)
")"
    if [ -z "$VERSION" ]; then
        echo "ERROR: Could not detect version from runtime/__init__.py"
        exit 1
    fi
    echo "Detected version: $VERSION"
fi

PKG_NAME="overcr-${VERSION}"
DIST_DIR="${ROOT}/dist"

echo "========================================"
echo "OverCR Release Packaging"
echo "========================================"
echo "  Version:  $VERSION"
echo "  Source:   $ROOT"
echo "  Output:   $DIST_DIR/"
echo ""

# Create dist directory
mkdir -p "$DIST_DIR"

# Clean any previous artifacts
rm -f "$DIST_DIR/$PKG_NAME.tar.gz" "$DIST_DIR/$PKG_NAME.zip"

# ── EXCLUSIONS ──
# These are never included in a release package.
EXCLUDES=(
    # Runtime state (generated at boot, not source)
    "--exclude=overcr_state.json"
    "--exclude=HQ_BOOT_MANIFEST.md"
    "--exclude=HQ_ROUTE_MARKER"
    "--exclude=HQ_BOOT_VERIFICATION.txt"
    "--exclude=prompts/hq_boot_context_bundle.txt"
    "--exclude=prompts/hq_raw_boot_context.txt"

    # Runtime directories
    "--exclude=sessions"
    "--exclude=logs"

    # Task state (generated at runtime)
    "--exclude=orchestration/tasks/task-*.json"

    # Audit log (generated at runtime)
    "--exclude=runtime/audit.jsonl"

    # Filled config files (templates are source, fills are runtime)
    "--exclude=configs/cag-memory-config.json"
    "--exclude=configs/session-ingestion-config.json"
    "--exclude=configs/release-preservation-config.txt"

    # Python bytecode
    "--exclude=__pycache__"
    "--exclude=*.pyc"
    "--exclude=*.pyo"

    # Packaging artifacts
    "--exclude=dist"
    "--exclude=*.tar.gz"
    "--exclude=*.zip"

    # OS artifacts
    "--exclude=.DS_Store"
    "--exclude=Thumbs.db"

    # Editor artifacts
    "--exclude=.vscode"
    "--exclude=.idea"
    "--exclude=*.swp"
    "--exclude=*.swo"
    "--exclude=*~"

    # Git (not included in source tarball)
    "--exclude=.git"
)

# ── Create tar.gz ──
echo "Creating tar.gz..."
tar czf "$DIST_DIR/$PKG_NAME.tar.gz" \
    "${EXCLUDES[@]}" \
    -C "$(dirname "$ROOT")" \
    "$(basename "$ROOT")"

TAR_SIZE="$(du -h "$DIST_DIR/$PKG_NAME.tar.gz" | cut -f1)"
TAR_SHA="$(sha256sum "$DIST_DIR/$PKG_NAME.tar.gz" | cut -d' ' -f1)"
echo "  $DIST_DIR/$PKG_NAME.tar.gz ($TAR_SIZE)"
echo "  SHA256: $TAR_SHA"

# ── Create zip ──
echo "Creating zip..."
(
    cd "$(dirname "$ROOT")"
    # Build exclude list for zip
    ZIP_EXCLUDES=(
        -x "overcr_state.json"
        -x "HQ_BOOT_MANIFEST.md"
        -x "HQ_ROUTE_MARKER"
        -x "HQ_BOOT_VERIFICATION.txt"
        -x "prompts/hq_boot_context_bundle.txt"
        -x "prompts/hq_raw_boot_context.txt"
        -x "sessions/*"
        -x "logs/*"
        -x "orchestration/tasks/task-*.json"
        -x "runtime/audit.jsonl"
        -x "configs/cag-memory-config.json"
        -x "configs/session-ingestion-config.json"
        -x "configs/release-preservation-config.txt"
        -x "__pycache__/*"
        -x "*.pyc"
        -x "*.pyo"
        -x ".git/*"
        -x ".DS_Store"
        -x "Thumbs.db"
        -x ".vscode/*"
        -x ".idea/*"
        -x "*.swp"
        -x "*.swo"
        -x "*~"
        -x "dist/*"
        -x "*.tar.gz"
        -x "*.zip"
    )
    zip -r "$DIST_DIR/$PKG_NAME.zip" "$(basename "$ROOT")" "${ZIP_EXCLUDES[@]}" -q
)

ZIP_SIZE="$(du -h "$DIST_DIR/$PKG_NAME.zip" | cut -f1)"
ZIP_SHA="$(sha256sum "$DIST_DIR/$PKG_NAME.zip" | cut -d' ' -f1)"
echo "  $DIST_DIR/$PKG_NAME.zip ($ZIP_SIZE)"
echo "  SHA256: $ZIP_SHA"

# ── Summary ──
echo ""
echo "========================================"
echo "Package Summary"
echo "========================================"
echo "  Package:   $PKG_NAME"
echo "  Version:   $VERSION"
echo "  tar.gz:    $DIST_DIR/$PKG_NAME.tar.gz ($TAR_SIZE)"
echo "             SHA256: $TAR_SHA"
echo "  zip:       $DIST_DIR/$PKG_NAME.zip ($ZIP_SIZE)"
echo "             SHA256: $ZIP_SHA"
echo ""
echo "  Run release cleanliness check:"
echo "    python3 $ROOT/scripts/check_release_clean.py --archive $DIST_DIR/$PKG_NAME.tar.gz"
echo ""
# OverCR HQ Boot Verification
# Run this to confirm stable operational continuity
# All paths are environment-driven for portability

OVERCR_ROOT="${OVERCR_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
echo "=== OverCR HQ Boot Verification ==="
echo "Instance: ${OVERCR_INSTANCE_ID:-overcr-hq-local}"
echo "Root: $OVERCR_ROOT"
echo ""

echo "1. State File Integrity"
if [ -f "$OVERCR_ROOT/overcr_state.json" ]; then
    echo "   [OK] overcr_state.json exists"
else
    echo "   [FAIL] overcr_state.json missing"
    exit 1
fi

echo ""
echo "2. Soul Reference Integrity"
if [ -f "$OVERCR_ROOT/soul_reference.md" ]; then
    echo "   [OK] soul_reference.md exists"
else
    echo "   [FAIL] soul_reference.md missing"
    exit 1
fi

echo ""
echo "3. HQ Route Marker"
if [ -f "$OVERCR_ROOT/HQ_ROUTE_MARKER" ]; then
    echo "   [OK] HQ_ROUTE_MARKER exists"
else
    echo "   [FAIL] HQ_ROUTE_MARKER missing"
    exit 1
fi

echo ""
echo "4. Config Files"
if [ -f "$OVERCR_ROOT/configs/cag-memory-config.json" ]; then
    echo "   [OK] cag-memory-config.json exists"
else
    echo "   [FAIL] cag-memory-config.json missing"
fi

if [ -f "$OVERCR_ROOT/configs/session-ingestion-config.json" ]; then
    echo "   [OK] session-ingestion-config.json exists"
else
    echo "   [FAIL] session-ingestion-config.json missing"
fi

echo ""
echo "5. Release Artifacts Separation"
ARCHIVE_ROOT="${OVERCR_RELEASE_ARCHIVE:-${OVERCR_ROOT}/../releases}"
if [ -d "$ARCHIVE_ROOT" ]; then
    echo "   [OK] Release archive at $ARCHIVE_ROOT"
else
    echo "   [WARN] Release archive not found at $ARCHIVE_ROOT (may not exist yet)"
fi

echo ""
echo "6. Environment Check"
echo "   OVERCR_ROOT: $OVERCR_ROOT"
echo "   HERMES_HOME: ${HERMES_HOME:-$HOME/.hermes}"
echo "   OVERCR_INSTANCE_ID: ${OVERCR_INSTANCE_ID:-not set}"

echo ""
echo "=== Verification Complete ==="
echo "All components in place for HQ operational continuity"
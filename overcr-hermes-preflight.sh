#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OVERCR_ROOT="${OVERCR_ROOT:-$ROOT}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PROFILE="${OVERCR_HERMES_PROFILE:-overcr-hq}"

failures=0
warnings=0

ok() {
  printf '   [OK] %s\n' "$1"
}

warn() {
  warnings=$((warnings + 1))
  printf '   [WARN] %s\n' "$1"
}

fail() {
  failures=$((failures + 1))
  printf '   [FAIL] %s\n' "$1"
}

is_truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

echo "=== OverCR Hermes Preflight ==="
echo "Root: $OVERCR_ROOT"
echo "Hermes home: $HERMES_HOME"
echo "Profile: $PROFILE"
echo ""

echo "1. Workspace Files"
for path in \
  "AGENTS.md" \
  "soul.md" \
  "overcr_state.json" \
  "HQ_ROUTE_MARKER" \
  "prompts/hq_compact_boot.md" \
  "configs/hermes-profiles.md"
do
  if [ -e "$OVERCR_ROOT/$path" ]; then
    ok "$path exists"
  else
    fail "$path missing"
  fi
done

echo ""
echo "2. Workspace Directories"
for path in "configs" "memory/routes/hq" "tasks" "workspace"; do
  if [ -d "$OVERCR_ROOT/$path" ]; then
    ok "$path exists"
  else
    warn "$path missing"
  fi
done

echo ""
echo "3. Hermes Availability"
if command -v hermes >/dev/null 2>&1; then
  ok "hermes command found: $(command -v hermes)"
else
  warn "hermes command not found on PATH"
fi

if [ -d "$HERMES_HOME" ]; then
  ok "HERMES_HOME exists"
else
  warn "HERMES_HOME does not exist yet"
fi

echo ""
echo "4. Approval Posture"
if is_truthy "${HERMES_YOLO_MODE:-}"; then
  fail "HERMES_YOLO_MODE is enabled; OverCR expects operator approval gates"
else
  ok "HERMES_YOLO_MODE is not enabled"
fi

config_file="$HERMES_HOME/config.yaml"
if [ -f "$config_file" ]; then
  approval_mode="$(
    awk '
      /^[[:space:]]*approvals:[[:space:]]*$/ { in_approvals=1; next }
      /^[^[:space:]][^:]*:[[:space:]]*/ { in_approvals=0 }
      in_approvals && /^[[:space:]]*mode:[[:space:]]*/ {
        sub(/^[[:space:]]*mode:[[:space:]]*/, "")
        gsub(/["'\'']/, "")
        print
        exit
      }
    ' "$config_file"
  )"
  if [ "${approval_mode:-}" = "off" ]; then
    fail "Hermes approvals.mode appears to be off in $config_file"
  elif [ -n "${approval_mode:-}" ]; then
    ok "Hermes approvals.mode is $approval_mode"
  else
    warn "Hermes approvals.mode not found in $config_file; using Hermes default"
  fi
else
  warn "Hermes config not found at $config_file"
fi

echo ""
echo "5. Profile Guidance"
case "$PROFILE" in
  overcr-hq)
    ok "overcr-hq profile selected"
    warn "Keep outbound toolsets disabled unless the operator explicitly needs them"
    ;;
  cryer-readonly)
    ok "cryer-readonly profile selected"
    warn "Use web/search/report-writing only; do not use messaging, form submission, login-required browsing, cron, or computer use"
    ;;
  operator-approved-actions)
    ok "operator-approved-actions profile selected"
    warn "Keep approvals scoped to the operator-approved task and record completed actions"
    ;;
  *)
    warn "Unknown OVERCR_HERMES_PROFILE '$PROFILE'; see configs/hermes-profiles.md"
    ;;
esac

echo ""
if [ "$failures" -gt 0 ]; then
  echo "=== Preflight Failed ==="
  echo "$failures failure(s), $warnings warning(s)"
  exit 1
fi

echo "=== Preflight Complete ==="
echo "$warnings warning(s)"
echo "OverCR workspace is ready for a Hermes session, subject to the warnings above."


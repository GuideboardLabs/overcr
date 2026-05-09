# OverCR HQ Boot Manifest
# Canonical runtime: ${OVERCR_ROOT}
# Instance and timestamp set at boot time

boot_timestamp: null
instance_id: ${OVERCR_INSTANCE_ID:-overcr-hq-local}
status: cold-start
mode: fresh-install

artifacts:
  soul_reference:
    source: ${OVERCR_ROOT}/soul.md
    dest: ${OVERCR_ROOT}/soul_reference.md
    integrity: unverified

workspace_integration:
  configs: ready
  memory: ready
  logs: ready
  tasks: ready
  prompts: ready
  tui: ready
  workspace: ready

route_status:
  overcr-hq: active
  priority: 1
  gateway: cli
  autonomous: false
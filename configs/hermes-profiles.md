# Hermes Profile Notes

These are reference profiles for running OverCR in Hermes. They are intentionally conservative and operator-facing: Hermes remains the runtime, while OverCR states the route expectations clearly.

The exact command or configuration surface may vary by Hermes version. Use the profile names and tool boundaries below when creating a Hermes profile, launcher, or local config.

## `overcr-hq`

Purpose: normal OverCR command-center mode.

Expected behavior:

- Load repository context from `AGENTS.md`.
- Read `soul.md`, `overcr_state.json`, `HQ_ROUTE_MARKER`, and `prompts/hq_compact_boot.md` at boot.
- Treat workspace files as authoritative over chat memory.
- Keep Hermes approval mode enabled.
- Do not enable yolo mode.
- Ask for operator approval before outbound or irreversible actions.

Suggested tool posture:

- Enable: file read/write, search, web research, local terminal with Hermes approval guardrails.
- Use with care: browser automation, cron/scheduled actions, computer use.
- Disable by default unless needed: messaging, smart-home/service-control tools, broad outbound integrations.

## `cryer-readonly`

Purpose: read-only public recon and evidence gathering.

Expected behavior:

- Inspect public information.
- Produce structured notes, reports, or task records inside the workspace.
- Avoid footprint-creating actions.

Suggested tool posture:

- Enable: web search/extraction, local file writing for reports.
- Disable: messaging, form submission, purchasing, booking, calls, login-required browsing, destructive terminal commands, cron jobs, computer use, and service-control tools.

Operator rule:

If a task requires logging in, messaging, submitting a form, contacting a person or business, or using private data, stop and ask for approval.

## `operator-approved-actions`

Purpose: broader action mode after the operator has explicitly approved a task.

Expected behavior:

- Keep the approval decision scoped to the named task.
- Record what was approved and what was done.
- Ask again when the action changes materially.

Suggested tool posture:

- Enable only the extra tools required for the approved action.
- Return to `overcr-hq` or `cryer-readonly` after the action is complete.


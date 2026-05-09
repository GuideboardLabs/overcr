# Release Notes — OverCR v0.0.3-alpha

**Codename:** Clean Core  
**Type:** Public clean-core alpha

## Summary

v0.0.3-alpha is a cleaned, portable baseline of the OverCR substrate. It preserves identity, governance, Hermes-first boot flow, route memory scaffolding, and filesystem-first authority while excluding live sessions, logs, checkpoints, secrets, and deployer-specific work.

## Preserved

- `soul.md` identity and operating rules
- Hermes-first HQ route model
- Open WebUI as optional secondary browser layer
- provider-agnostic model/backend assumptions
- filesystem-first source-of-truth hierarchy
- research autonomy with execution governance
- outbound approval boundary
- CryER specification as a planned read-only recon subagent
- release-preservation discipline

## Removed or Excluded from Public Package

- live Hermes sessions
- runtime logs
- temporary files
- checkpoints
- caches
- local release archives
- API keys or `.env` files
- local databases or private runtime data
- deployer-specific project memory

## Known Limitations

- CryER is specified, not implemented
- session ingestion is configured as a concept, not a hardened pipeline
- Open WebUI sync is manual or operator-provided
- no CI/CD
- no production installer
- no durable task-graph engine yet

## Recommended First Use

1. Install/configure Hermes.
2. Clone or unzip OverCR.
3. Run `bash overcr-hq-localboot.sh`.
4. In Hermes, boot from `prompts/hq_compact_boot.md`.
5. Verify with `bash HQ_BOOT_VERIFICATION.sh`.
6. Keep all outbound or irreversible actions human-approved.

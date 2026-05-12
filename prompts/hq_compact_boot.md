Boot OverCR HQ.

Read soul.md first.

Reconstruct operational context from filesystem state, not chat history.

Inspect:
- overcr_state.json if present
- memory/routes/hq/
- memory/warm/
- tasks/
- knowledge/
- checkpoints/
- release manifests

Return concise HQ status:
- identity/status
- loaded memory/state
- active risks
- available runtime tools
- next recommended action

Do not dump full files.
Do not expand architecture.
Use filesystem truth as authoritative.
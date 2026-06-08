"""
OverCR Vault — GBrain Integration

Filesystem-first vault reader for OverCR. Walks an Obsidian vault,
parses gbrain/cammander/overcr facts fences, resolves [[wikilinks]],
and exposes structured knowledge to the runtime as optional context.

Zero external dependencies. Zero vector DB. Zero embeddings.

Usage:
    from knowledge.vault import VaultIndex

    idx = VaultIndex("/path/to/vault")
    idx.rebuild()
    facts = idx.search(domain="cag", tags=["memory"])

Or with auto-load on first search:
    idx = VaultIndex("/path/to/vault")
    facts = idx.search(query="KV cache")  # auto-rebuilds
"""

from knowledge.vault.vault_adapter import VaultIndex

__all__ = [
    "VaultIndex",
]

__version__ = "0.1.0"
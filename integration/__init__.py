"""
OverCR v2.9.0 — Integration Hardening & Release Candidate Preparation

A suite of validators, checkers, and verifiers that ensure the v2
stack is internally coherent, replayable, portable, auditable, and
recoverable.

This release is about stabilization, not new capabilities. Every
validator reports — never mutates. Every checker is deterministic.

Exports:
  - SchemaRegistry: centralized schema discovery
  - SystemValidator: directory, schema, and workflow integrity
  - ReplayValidator: replay determinism and audit reconstruction
  - StateConsistency: cross-system reference integrity
  - ReleaseIntegrity: release cleanliness checks
  - MigrationChecker: v1→v2 compatibility validation
  - CompatibilityMatrix: machine-readable compat report
  - RecoveryVerifier: cold-start reconstruction simulation
"""

from integration.schema_registry import SchemaRegistry, SchemaEntry
from integration.system_validator import SystemValidator, SystemValidationReport
from integration.replay_validator import ReplayValidator, ReplayValidationReport
from integration.state_consistency import StateConsistency, ConsistencyReport
from integration.release_integrity import ReleaseIntegrity, IntegrityReport
from integration.migration_checker import MigrationChecker, MigrationReport
from integration.compatibility_matrix import CompatibilityMatrix, CompatibilityReport
from integration.recovery_verifier import RecoveryVerifier, RecoveryVerification

__all__ = [
    "SchemaRegistry", "SchemaEntry",
    "SystemValidator", "SystemValidationReport",
    "ReplayValidator", "ReplayValidationReport",
    "StateConsistency", "ConsistencyReport",
    "ReleaseIntegrity", "IntegrityReport",
    "MigrationChecker", "MigrationReport",
    "CompatibilityMatrix", "CompatibilityReport",
    "RecoveryVerifier", "RecoveryVerification",
]

__version__ = "2.9.0"

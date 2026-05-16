"""
OverCR v2.10.0 — Stable Release Candidate Consolidation

A suite of release preparation tools for stable-release candidacy:
semantic compatibility, install validation, release building,
manifest generation, version tracking, reproducibility checks,
and operator readiness validation.

Every tool reports — never mutates. Every check is deterministic.
"""

from release.semantic_compatibility import SemanticCompatibility, SemanticCompatReport
from release.install_validator import InstallValidator, InstallValidationReport
from release.release_builder import ReleaseBuilder, ReleaseBuild
from release.release_manifest import ReleaseManifest, ReleaseManifestEntry
from release.version_matrix import VersionMatrix, VersionMatrixEntry
from release.reproducibility_checker import ReproducibilityChecker, ReproducibilityReport
from release.operator_readiness import OperatorReadiness, ReadinessReport

__all__ = [
    "SemanticCompatibility", "SemanticCompatReport",
    "InstallValidator", "InstallValidationReport",
    "ReleaseBuilder", "ReleaseBuild",
    "ReleaseManifest", "ReleaseManifestEntry",
    "VersionMatrix", "VersionMatrixEntry",
    "ReproducibilityChecker", "ReproducibilityReport",
    "OperatorReadiness", "ReadinessReport",
]

__version__ = "2.10.0"

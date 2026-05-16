"""
OverCR v2.10.1 — Final Stable Validation

Validates the v2.10.0 stable release candidate under realistic operating
conditions. Every tool reports — never mutates. Every check is deterministic.

Modules:
  SoakTester       — repeated controlled operations over time
  SecurityFuzzer   — fuzz validators/guards with malicious inputs
  PerformanceBaseline — deterministic latency measurements
  OperatorAcceptance  — human-operator flow verification
  PlatformReport   — OS, Python, dependencies, known limitations
"""

from validation.soak_tester import SoakTester, SoakTesterConfig, SoakResult
from validation.security_fuzzer import SecurityFuzzer, FuzzCase, FuzzerReport
from validation.performance_baseline import PerformanceBaseline, PerfReport
from validation.operator_acceptance import OperatorAcceptance, AcceptanceReport
from validation.platform_report import PlatformReport

__all__ = [
    "SoakTester",
    "SoakTesterConfig",
    "SoakResult",
    "SecurityFuzzer",
    "FuzzCase",
    "FuzzerReport",
    "PerformanceBaseline",
    "PerfReport",
    "OperatorAcceptance",
    "AcceptanceReport",
    "PlatformReport",
]

__version__ = "2.10.1"

"""Layer 1: free, instant, deterministic scoring.

Cost boundary: nothing in this package may import a metered LLM/embedding client.
Enforced by the import-linter contract in pyproject.toml and tests/test_cost_boundary.py.
"""

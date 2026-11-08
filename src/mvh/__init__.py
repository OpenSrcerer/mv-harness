# ruff: noqa: E501  (long catalogue tables / docstrings)
"""mv-harness: one song in, a folder of timestamped metadata out (see PLAN.md and docs/CONTRACT.md).

Core rule (PLAN §3.3): ``mvh/__init__``, ``mvh/worker.py`` and ``mvh/contract/`` import only the stdlib and numpy,
so the sep worker env can import them.
"""
__version__ = "0.1.0"
CONTRACT_VERSION = "1.0.0-rc.1"   # keep equal to mvh.contract.catalog.CONTRACT_VERSION (tested)

__all__ = ["__version__", "CONTRACT_VERSION"]

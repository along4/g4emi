"""Shared matplotlib rendering helpers for analysis outputs.

This module should own:
- common figure creation
- histogram rendering helpers
- shared styling/color helpers
- save/show handling for figures

This module should not own:
- HDF5 reads
- domain-specific data extraction
- SimConfig loading
"""

from __future__ import annotations

__all__: list[str] = []

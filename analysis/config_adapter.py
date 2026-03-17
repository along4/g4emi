"""Adapters from repo configuration objects into analysis parameters.

This module should own:
- SimConfig-derived plot extents
- SimConfig-derived timing-component extraction
- translation from hydrated config objects into plain analysis inputs

This module should not own:
- core analysis logic
- generic HDF5 access
- matplotlib rendering
"""

from __future__ import annotations

__all__: list[str] = []

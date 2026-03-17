"""HDF5 file and dataset access helpers for analysis code.

This module should own:
- opening HDF5 files for read-only analysis
- loading structured datasets and root attributes
- dataset existence checks
- shared field-validation helpers

This module should not own:
- plotting
- domain analysis logic
- SimConfig loading
"""

from __future__ import annotations

__all__: list[str] = []

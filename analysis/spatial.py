"""Spatial quick-look analyzers for primary/photon/intensifier views.

This module should own:
- neutron hit image generation
- photon origin image generation
- photon exit image generation
- optical interface hit image generation
- intensifier hit image generation
- shared XY-range policy for spatial plots

This module should not own:
- generic plotting primitives
- timing fits
- event recoil visualization
"""

from __future__ import annotations

__all__: list[str] = []

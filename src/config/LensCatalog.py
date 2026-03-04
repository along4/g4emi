"""Pydantic models for lens catalog data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Base model with strict validation defaults."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
    )


class LensCatalogEntryDefinition(StrictModel):
    """One lens entry definition loaded from `lenses/catalog.yaml`."""

    name: str = Field(min_length=1)
    description: str = ""
    zmx_file: str = Field(alias="zmxFile", min_length=1)
    smx_file: str | None = Field(default=None, alias="smxFile", min_length=1)


class LensCatalogIndex(StrictModel):
    """Top-level lens catalog file model (`lenses/catalog.yaml`)."""

    version: int = Field(ge=1)
    default: str = Field(min_length=1)
    lenses: dict[str, LensCatalogEntryDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_default_key(self) -> "LensCatalogIndex":
        if self.default not in self.lenses:
            raise ValueError(
                f"catalog default '{self.default}' not found in lenses mapping."
            )
        return self


class LoadedLens(StrictModel):
    """Resolved lens entry with absolute asset paths."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    zmx_path: Path = Field(alias="zmxPath")
    smx_path: Path | None = Field(default=None, alias="smxPath")


@dataclass(frozen=True)
class LensCatalogContext:
    """Loaded lens catalog index and filesystem context."""

    index: LensCatalogIndex
    catalog_path: str

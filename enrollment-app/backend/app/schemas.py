"""Pydantic request schemas (contracts/rest-api.md).

Responses are built by the service layer as plain dicts so the contract shapes stay
explicit; these schemas own request validation. ``extra="forbid"`` means immutable
fields (frigate_identity_name, id, ...) can never be smuggled in via PATCH/POST.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import Relationship


class PersonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=100)
    relationship: Relationship

    @field_validator("display_name")
    @classmethod
    def _trim_and_require(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("display_name must not be blank")
        return v


class PersonUpdate(BaseModel):
    """PATCH — any subset of the three mutable fields. Nothing else is accepted."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    relationship: Relationship | None = None
    enabled: bool | None = None

    @field_validator("display_name")
    @classmethod
    def _trim_and_require(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("display_name must not be blank")
        return v
"""The Fact/Evidence model: every value the product shows carries its provenance.

Invariants enforced here (HLD §2.2):
- ACTUAL values cite at least one piece of evidence.
- CALCULATED values carry the formula that produced them.
- ASSUMED and RECOMMENDED values explain themselves in `note`.
- UNAVAILABLE values have no value and say why, so missing data is never shown as 0.
"""

from datetime import datetime
from typing import Generic, Self, TypeVar

from pydantic import BaseModel, ConfigDict, JsonValue, model_validator

from app.domain.enums import EvidenceKind, Provenance, SourceMode

T = TypeVar("T")


class Fact(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True)

    value: T | None = None
    unit: str | None = None
    provenance: Provenance
    evidence_ids: tuple[str, ...] = ()
    formula: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> Self:
        p = self.provenance
        if p is Provenance.UNAVAILABLE:
            if self.value is not None:
                raise ValueError("UNAVAILABLE facts must not carry a value")
            if not self.note:
                raise ValueError("UNAVAILABLE facts must explain why in `note`")
            return self
        if self.value is None:
            raise ValueError(f"{p} facts must carry a value; use UNAVAILABLE instead")
        if p is Provenance.ACTUAL and not self.evidence_ids:
            raise ValueError("ACTUAL facts must cite at least one evidence id")
        if p is Provenance.CALCULATED and not self.formula:
            raise ValueError("CALCULATED facts must include the formula")
        if p in (Provenance.ASSUMED, Provenance.RECOMMENDED) and not self.note:
            raise ValueError(f"{p} facts must explain themselves in `note`")
        return self

    @property
    def is_available(self) -> bool:
        return self.provenance is not Provenance.UNAVAILABLE


def actual(value: T, *evidence_ids: str, unit: str | None = None) -> Fact[T]:
    return Fact[T](value=value, unit=unit, provenance=Provenance.ACTUAL, evidence_ids=evidence_ids)


def calculated(value: T, formula: str, *evidence_ids: str, unit: str | None = None) -> Fact[T]:
    return Fact[T](
        value=value,
        unit=unit,
        provenance=Provenance.CALCULATED,
        formula=formula,
        evidence_ids=evidence_ids,
    )


def assumed(value: T, note: str, *evidence_ids: str, unit: str | None = None) -> Fact[T]:
    return Fact[T](
        value=value, unit=unit, provenance=Provenance.ASSUMED, note=note, evidence_ids=evidence_ids
    )


def recommended(value: T, note: str, *evidence_ids: str, unit: str | None = None) -> Fact[T]:
    return Fact[T](
        value=value,
        unit=unit,
        provenance=Provenance.RECOMMENDED,
        note=note,
        evidence_ids=evidence_ids,
    )


def unavailable(reason: str, *evidence_ids: str, unit: str | None = None) -> Fact[T]:
    return Fact[T](
        unit=unit, provenance=Provenance.UNAVAILABLE, note=reason, evidence_ids=evidence_ids
    )


class Evidence(BaseModel):
    """A source record a Fact can cite: a BOM cell, distributor offer, rule evaluation, etc."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: EvidenceKind
    source_name: str
    source_ref: str | None = None
    fetched_at: datetime | None = None
    mode: SourceMode | None = None
    payload_excerpt: dict[str, JsonValue] = {}

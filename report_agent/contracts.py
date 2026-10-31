"""Pydantic result schemas published by the official MCP SDK."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ToolResult(BaseModel, Generic[T]):
    ok: bool
    data: T | None = None
    error: str | None = None
    kind: str | None = None


class ImportResult(BaseModel):
    file: str
    sheet: str
    header_row: int
    mapping: dict[str, str]
    raw_rows: int
    rows: int
    removed_duplicates: int
    date_start: str
    date_end: str
    references: list[dict]


class Source(BaseModel):
    id: str
    text: str


class MinutesResult(BaseModel):
    week: int | None
    sources: list[Source]


class Metric(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    label: str
    dimension: str
    cents: int
    previous_cents: int
    change: float | None
    margin: float | None
    target_rate: float | None
    delivery_share: float | None
    anomaly: bool


class MetricsResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    total: Metric
    groups: list[Metric]
    anomalies: list[Metric]
    tokens: dict[str, str]
    top_products: list[dict]
    quality: dict
    trend: list[dict]
    period: str
    week: int
    import_summary: dict
    category_margins: list[dict] = Field(default_factory=list)


class ArtifactResult(BaseModel):
    file: str
    artifact_id: str
    sha256: str
    chart_files: list[str]


class Check(BaseModel):
    name: str
    passed: bool
    details: str


class QualityResult(BaseModel):
    passed: bool
    checks: list[Check]
    artifact_id: str

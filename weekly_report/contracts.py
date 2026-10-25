"""Typed MCP output envelopes; the official SDK publishes these as output JSON Schemas."""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ToolResult(BaseModel, Generic[T]):
    ok: bool
    data: T | None = None
    error: str | None = None
    kind: str | None = None


class SaleRow(BaseModel):
    date: str
    store: str
    region: str
    category: str
    cents: int
    source_row: int


class SalesData(BaseModel):
    records: list[SaleRow]
    warnings: list[str]
    row_count: int


class Source(BaseModel):
    id: str
    text: str


class MinutesData(BaseModel):
    sources: list[Source]


class MetricRow(BaseModel):
    key: str
    label: str
    dimension: str
    current_cents: int
    previous_cents: int | None
    change_percent: float | None
    change_text: str
    current_rows: int
    previous_rows: int
    anomaly: bool


class MetricsData(BaseModel):
    total: MetricRow
    groups: list[MetricRow]
    tokens: dict[str, str]
    warnings: list[str]
    period: str
    previous_period: str
    current_rows: int
    previous_rows: int
    threshold: float


class FileData(BaseModel):
    file: str


class QualityCheck(BaseModel):
    name: str
    passed: bool
    details: str


class QualityData(BaseModel):
    passed: bool
    checks: list[QualityCheck] = Field(min_length=1)
    file: str

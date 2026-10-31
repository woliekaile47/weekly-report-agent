from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TaskSpec(BaseModel):
    title: str = Field(default="门店经营周报", min_length=1, max_length=100)
    year: int = Field(default=2026, ge=2000, le=2100)
    week: int = Field(default=44, ge=1, le=53)
    focus: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def valid_week(self):
        date.fromisocalendar(self.year, self.week, 1)
        return self


class Evidence(BaseModel):
    source_id: str
    quote: str = Field(min_length=1)


class Anomaly(BaseModel):
    metric_id: str
    reason: str
    uncertain: bool
    evidence: list[Evidence] = Field(default_factory=list)


class Draft(BaseModel):
    summary: str
    anomalies: list[Anomaly]
    conflicts: list[str] = Field(default_factory=list)
    data_notes: list[str] = Field(default_factory=list)
    actions: list[str]
    review_response: str = ""


class Review(BaseModel):
    decision: Literal["approve", "revise"]
    reviewer: str = Field(min_length=1, max_length=80)
    feedback: str = Field(default="", max_length=4000)
    version: int = Field(ge=1)

    @model_validator(mode="after")
    def required_feedback(self):
        if not self.reviewer.strip() or (self.decision == "revise" and not self.feedback.strip()):
            raise ValueError("请填写审核人；退回时必须填写修改意见")
        return self


class WorkflowError(Exception):
    def __init__(self, message, kind="execution"):
        super().__init__(message)
        self.kind = kind

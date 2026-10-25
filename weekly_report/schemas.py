from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TaskSpec(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    start_date: date
    end_date: date
    require_comparison: bool = True
    focus: str = Field(default="分析各区域、门店和品类经营表现，说明异常及改进建议。", max_length=2000)

    @model_validator(mode="after")
    def valid_period(self):
        if not 0 <= (self.end_date - self.start_date).days <= 30:
            raise ValueError("统计周期须为 1 至 31 天，结束日期不得早于开始日期")
        return self


class Evidence(BaseModel):
    source_id: str
    quote: str = Field(min_length=1, max_length=1500)


class Finding(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    analysis: str = Field(min_length=1, max_length=4000)
    uncertain: bool
    evidence: list[Evidence] = Field(default_factory=list, max_length=10)


class Draft(BaseModel):
    summary: str = Field(min_length=1, max_length=5000)
    findings: list[Finding] = Field(min_length=1, max_length=15)
    actions: list[str] = Field(min_length=1, max_length=15)
    review_response: str = Field(default="", max_length=4000)


class Review(BaseModel):
    decision: Literal["approve", "reject"]
    version: int = Field(ge=1)
    reviewer: str = Field(min_length=1, max_length=80)
    feedback: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def feedback_required(self):
        if self.decision == "reject" and not self.feedback.strip():
            raise ValueError("退回修改必须填写意见")
        if not self.reviewer.strip():
            raise ValueError("请填写审核人")
        return self


class EmployeeError(Exception):
    def __init__(self, message: str, kind: str = "execution"):
        super().__init__(message)
        self.kind = kind

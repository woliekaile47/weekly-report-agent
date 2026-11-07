from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TaskSpec(BaseModel):
    title: str = Field(default="门店经营周报", min_length=1, max_length=100)
    year: int = Field(default=2026, ge=2000, le=2100)
    week: int = Field(default=44, ge=1, le=53)
    focus: str = Field(default="", max_length=2000)
    news_queries: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("news_queries")
    @classmethod
    def bounded_queries(cls, values):
        if any(not q.strip() or len(q) > 160 for q in values):
            raise ValueError("每条公开新闻关键词须为1至160字，最多3条")
        return values

    @model_validator(mode="after")
    def valid_week(self):
        date.fromisocalendar(self.year, self.week, 1)
        return self


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    quote: str = Field(min_length=1)

    @field_validator("source_id", "quote")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("证据编号和摘录不能为空")
        return value


class Anomaly(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric_id: str
    reason: str
    uncertain: bool
    evidence: list[Evidence] = Field(default_factory=list)

    @field_validator("metric_id", "reason")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("异常编号和原因不能为空")
        return value


Section = Literal["summary", "anomalies", "conflicts", "data_notes", "actions"]


class RevisionResponse(BaseModel):
    item_id: str
    response: str = Field(min_length=1, max_length=1200)
    sections: list[Section] = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)


class NewsAssessment(BaseModel):
    source_id: str
    verdict: Literal["support", "conflict", "unverified"]
    explanation: str = Field(min_length=1, max_length=800)
    citations: list[Evidence] = Field(default_factory=list, max_length=5)


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    news_assessments: list[NewsAssessment] = Field(default_factory=list, max_length=30)
    summary: str
    anomalies: list[Anomaly]
    conflicts: list[str] = Field(default_factory=list)
    data_notes: list[str] = Field(default_factory=list)
    actions: list[str]
    review_response: str = ""
    revision_responses: list[RevisionResponse] = Field(default_factory=list)

    @field_validator("summary")
    @classmethod
    def summary_required(cls, value):
        if not value.strip():
            raise ValueError("本周摘要不能为空")
        return value

    @field_validator("actions", "conflicts", "data_notes")
    @classmethod
    def list_entries_required(cls, values):
        if any(not item.strip() for item in values):
            raise ValueError("章节条目不能为空")
        return values

    @model_validator(mode="after")
    def actions_required(self):
        if not self.actions:
            raise ValueError("至少填写一条行动项")
        return self


class ReviewItem(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    category: Literal["auto", "data", "evidence", "content", "layout"] = "auto"
    sections: list[Section] = Field(default_factory=list)

    @model_validator(mode="after")
    def nonblank(self):
        if not self.text.strip():
            raise ValueError("修改意见不能为空")
        return self


class Review(BaseModel):
    decision: Literal["approve", "revise"]
    reviewer: str = Field(min_length=1, max_length=80)
    feedback: str = Field(default="", max_length=4000)
    version: int = Field(ge=1)
    items: list[ReviewItem] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def required_feedback(self):
        if not self.reviewer.strip() or (
            self.decision == "revise" and not (self.feedback.strip() or self.items)
        ):
            raise ValueError("请填写审核人；退回时必须填写修改意见")
        if self.decision == "approve" and self.items:
            raise ValueError("通过时不能同时提交未处理的修改项")
        return self


class WorkflowError(Exception):
    def __init__(self, message, kind="execution"):
        super().__init__(message)
        self.kind = kind

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.enums import AssessmentStage


class GeminiQuestionGenerationRequest(BaseModel):
    jd: str = Field(min_length=20)
    resume: str = Field(min_length=20)
    stage: AssessmentStage
    role_seniority: str = "mid"
    previous_answers: list[str] = Field(default_factory=list)
    count: int = Field(default=3, ge=1, le=10)


class GeminiQuestionGenerationResponse(BaseModel):
    questions: list[dict]
    model: str
    fallback_used: bool


class GeminiAnswerEvaluationRequest(BaseModel):
    question: str = Field(min_length=3)
    answer: str = Field(min_length=1)
    rubric: dict = Field(default_factory=dict)


class GeminiAnswerEvaluationResponse(BaseModel):
    score: float
    confidence: float
    classification: str
    reasons: list[str] = Field(default_factory=list)
    model: str
    fallback_used: bool


class AIChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class AIChatRequest(BaseModel):
    messages: list[AIChatMessage] = Field(min_length=1, max_length=40)
    context: dict = Field(default_factory=dict)


class AIChatResponse(BaseModel):
    reply: str
    model: str
    fallback_used: bool

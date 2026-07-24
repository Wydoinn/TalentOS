from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import get_auth_context, require_roles
from app.models.enums import UserRole
from app.schemas.ai import (
    AIChatRequest,
    AIChatResponse,
    GeminiAnswerEvaluationRequest,
    GeminiAnswerEvaluationResponse,
    GeminiQuestionGenerationRequest,
    GeminiQuestionGenerationResponse,
)
from app.services.gemini_service import GeminiService


router = APIRouter(prefix="/ai", tags=["ai"])
manager_only = require_roles(UserRole.PROJECT_MANAGER)


@router.post("/questions/generate", response_model=GeminiQuestionGenerationResponse)
async def generate_questions(
    payload: GeminiQuestionGenerationRequest,
    _=Depends(manager_only),
) -> GeminiQuestionGenerationResponse:
    service = GeminiService()
    result = await service.generate_questions(
        jd=payload.jd,
        resume=payload.resume,
        stage=payload.stage,
        role_seniority=payload.role_seniority,
        previous_answers=payload.previous_answers,
        count=payload.count,
    )
    return GeminiQuestionGenerationResponse(
        questions=result.questions,
        model=result.model,
        fallback_used=result.fallback_used,
    )


@router.post("/answers/evaluate", response_model=GeminiAnswerEvaluationResponse)
async def evaluate_answer(
    payload: GeminiAnswerEvaluationRequest,
    _=Depends(manager_only),
) -> GeminiAnswerEvaluationResponse:
    service = GeminiService()
    result = await service.evaluate_answer(
        question=payload.question,
        answer=payload.answer,
        rubric=payload.rubric,
    )
    return GeminiAnswerEvaluationResponse(
        score=result.score,
        confidence=result.confidence,
        classification=result.classification,
        reasons=result.reasons,
        model=result.model,
        fallback_used=result.fallback_used,
    )


@router.post("/chat", response_model=AIChatResponse)
async def ai_chat(
    payload: AIChatRequest,
    auth=Depends(get_auth_context),
) -> AIChatResponse:
    """Conversational AI assistant for hiring managers and candidates.
    Accessible by both PM and CANDIDATE roles.
    """
    service = GeminiService()
    result = await service.chat(
        messages=[{"role": m.role, "content": m.content} for m in payload.messages],
        context=payload.context,
    )
    return AIChatResponse(
        reply=result.reply,
        model=result.model,
        fallback_used=result.fallback_used,
    )

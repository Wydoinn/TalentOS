from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_feedback_service
from app.schemas.feedback import (
    CandidateFeedbackRequest,
    CandidateFeedbackResponse,
    FeedbackSummaryResponse,
)
from app.services.feedback_service import RecruiterFeedbackService

router = APIRouter(prefix="/resumes/feedback", tags=["Recruiter Feedback"])


@router.post("", response_model=CandidateFeedbackResponse)
async def record_feedback(
    payload: CandidateFeedbackRequest,
    feedback_service: RecruiterFeedbackService = Depends(get_feedback_service),
) -> CandidateFeedbackResponse:
    return await feedback_service.record_feedback(payload)


@router.get("/summary", response_model=FeedbackSummaryResponse)
async def feedback_summary(
    feedback_service: RecruiterFeedbackService = Depends(get_feedback_service),
) -> FeedbackSummaryResponse:
    return await feedback_service.get_feedback_summary()

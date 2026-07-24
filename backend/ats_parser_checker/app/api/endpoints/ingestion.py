from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_resume_analysis_service, get_resume_sync_manager
from app.schemas.ingestion import ResumeSyncStatusResponse, ResumeSyncSummary
from app.schemas.resume_analysis import (
    ResumeCheckRequest,
    ResumeCheckResponse,
    ResumeReportResponse,
)
from app.services.resume_analysis_service import ResumeAnalysisService
from app.services.resume_sync_service import ResumeDirectorySyncManager

router = APIRouter(prefix="/resumes", tags=["Resume Ingestion"])


@router.get("/status", response_model=ResumeSyncStatusResponse)
async def resume_sync_status(
    sync_manager: ResumeDirectorySyncManager = Depends(get_resume_sync_manager),
) -> ResumeSyncStatusResponse:
    return sync_manager.build_status()


@router.post("/sync", response_model=ResumeSyncSummary)
async def sync_resumes(
    sync_manager: ResumeDirectorySyncManager = Depends(get_resume_sync_manager),
) -> ResumeSyncSummary:
    return await sync_manager.sync(force=True)


@router.post("/check", response_model=ResumeCheckResponse)
async def check_resume(
    payload: ResumeCheckRequest,
    analysis_service: ResumeAnalysisService = Depends(get_resume_analysis_service),
) -> ResumeCheckResponse:
    return await analysis_service.check_resumes(payload)


@router.get("/check/{report_run_id}", response_model=ResumeCheckResponse)
async def get_check_run(
    report_run_id: str,
    analysis_service: ResumeAnalysisService = Depends(get_resume_analysis_service),
) -> ResumeCheckResponse:
    return await analysis_service.get_check_run(report_run_id)


@router.get("/report/{report_run_id}/{candidate_id}", response_model=ResumeReportResponse)
async def get_resume_report(
    report_run_id: str,
    candidate_id: str,
    analysis_service: ResumeAnalysisService = Depends(get_resume_analysis_service),
) -> ResumeReportResponse:
    return await analysis_service.get_report(report_run_id, candidate_id)

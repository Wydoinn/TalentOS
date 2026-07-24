from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db_session
from app.core.exceptions import ApiError
from app.core.security import AuthContext, get_auth_context, require_roles
from app.models.entities import CandidateMatch, Job, RankingResult, ResumeAnalysis, RoleRequirement
from app.models.enums import MatchStatus, UserRole
from app.schemas.jobs import (
    AutoInviteResponse,
    CandidateProfileAIResponse,
    CandidateMatchResponse,
    CandidateStatusUpdateRequest,
    JobCreateRequest,
    JobCandidatesResponse,
    JobResponse,
    JobUpdateRequest,
    QuestionBlueprintItem,
    RankingRequest,
    RankingResponse,
    RequirementInput,
    ResumeCheckProxyRequest,
    default_question_blueprint,
)
from app.services.ats_client import ATSClient
from app.services.audit_service import AuditService
from app.services.gemini_service import GeminiService
from app.services.ranking_service import RankingService


router = APIRouter(prefix="/jobs", tags=["jobs"])
manager_only = require_roles(UserRole.PROJECT_MANAGER)


def _job_to_response(job: Job) -> JobResponse:
    requirements = [
        RequirementInput(
            requirement_type=requirement.requirement_type,
            label=requirement.label,
            weight=requirement.weight,
        )
        for requirement in job.requirements
    ]
    return JobResponse(
        id=job.id,
        manager_user_id=job.manager_user_id,
        title=job.title,
        department=job.department,
        location=job.location,
        employment_type=job.employment_type,
        seniority=job.seniority,
        description=job.description,
        jd_text=job.jd_text,
        assessment_start_at=job.assessment_start_at,
        assessment_end_at=job.assessment_end_at,
        assessment_timezone=job.assessment_timezone,
        assessment_slot_minutes=job.assessment_slot_minutes,
        question_blueprint=_normalize_question_blueprint(job.question_blueprint),
        status=job.status,
        requirements=requirements,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _ranking_source_map(ranking_payload: dict | None) -> dict[str, str]:
    if not isinstance(ranking_payload, dict):
        return {}

    raw_results = ranking_payload.get("results")
    if not isinstance(raw_results, list):
        return {}

    source_map: dict[str, str] = {}
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        candidate_id = _read_text(item.get("candidate_id"))
        source = _read_text(item.get("source"))
        if candidate_id and source:
            source_map[candidate_id] = source
    return source_map


def _candidate_match_response(
    match: CandidateMatch,
    source_map: dict[str, str] | None = None,
) -> CandidateMatchResponse:
    return CandidateMatchResponse(
        match_id=match.id,
        candidate_external_id=match.candidate_external_id,
        candidate_name=match.candidate_name,
        candidate_email=match.candidate_email,
        source=(source_map or {}).get(match.candidate_external_id),
        rank=match.rank,
        final_score=match.final_score,
        ats_score=match.ats_score,
        status=match.status,
        explanation=match.explanation,
    )


def _candidate_payload_response(
    item: dict[str, object],
    *,
    rank: int,
) -> CandidateMatchResponse | None:
    candidate_external_id = _read_text(item.get("candidate_id"))
    candidate_name = _read_text(item.get("candidate_name"))
    if not candidate_external_id or not candidate_name:
        return None

    candidate_email = _read_text(item.get("email")) or _read_text(item.get("candidate_email"))
    explanation = _read_text(item.get("explanation")) or _read_text(item.get("summary")) or "Matched from ATS ranking results."
    source = _read_text(item.get("source"))

    try:
        final_score = float(item.get("final_score") or 0.0)
    except Exception:
        final_score = 0.0

    try:
        ats_score = float(item.get("ats_score") or 0.0)
    except Exception:
        ats_score = 0.0

    return CandidateMatchResponse(
        match_id=candidate_external_id,
        candidate_external_id=candidate_external_id,
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        source=source,
        rank=rank,
        final_score=final_score,
        ats_score=ats_score,
        status=MatchStatus.MATCHED,
        explanation=explanation,
    )


def _job_candidate_responses(ranking: RankingResult) -> list[CandidateMatchResponse]:
    source_map = _ranking_source_map(ranking.ranking_payload)
    matches = sorted(ranking.matches, key=lambda item: item.rank)
    if matches:
        return [_candidate_match_response(match, source_map) for match in matches]

    payload = ranking.ranking_payload if isinstance(ranking.ranking_payload, dict) else {}
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        return []

    candidates: list[CandidateMatchResponse] = []
    for index, item in enumerate(raw_results, start=1):
        if not isinstance(item, dict):
            continue
        candidate = _candidate_payload_response(item, rank=index)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


@router.post("", response_model=JobResponse)
async def create_job(
    payload: JobCreateRequest,
    request: Request,
    context: AuthContext = Depends(manager_only),
    session: AsyncSession = Depends(get_db_session),
) -> JobResponse:
    job = Job(
        manager_user_id=context.user_id,
        title=payload.title,
        department=payload.department,
        location=payload.location,
        employment_type=payload.employment_type,
        seniority=payload.seniority,
        description=payload.description,
        jd_text=payload.jd_text,
        assessment_start_at=payload.assessment_start_at,
        assessment_end_at=payload.assessment_end_at,
        assessment_timezone=payload.assessment_timezone,
        assessment_slot_minutes=payload.assessment_slot_minutes,
        question_blueprint=[item.model_dump(mode="json") for item in payload.question_blueprint],
        status=payload.status,
    )
    session.add(job)
    await session.flush()

    for requirement in payload.requirements:
        session.add(
            RoleRequirement(
                job_id=job.id,
                requirement_type=requirement.requirement_type,
                label=requirement.label,
                weight=requirement.weight,
            )
        )

    audit_service = AuditService(session)
    await audit_service.record(
        context=context,
        action="jobs.create",
        resource_type="job",
        resource_id=job.id,
        request=request,
        metadata={"title": payload.title},
    )

    await session.commit()
    await session.refresh(job)
    job_with_requirements = await session.scalar(
        select(Job)
        .where(Job.id == job.id)
        .options(selectinload(Job.requirements))
    )
    if job_with_requirements is None:
        raise ApiError(status_code=500, code="job_persistence_failed", message="Could not load created job.")
    return _job_to_response(job_with_requirements)


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[JobResponse]:
    query = select(Job).options(selectinload(Job.requirements)).order_by(Job.created_at.desc())

    if context.role == UserRole.PROJECT_MANAGER:
        query = query.where(Job.manager_user_id == context.user_id)
    elif context.role == UserRole.CANDIDATE:
        query = query.where(Job.status == "ACTIVE")

    jobs = await session.scalars(query)
    return [_job_to_response(job) for job in jobs]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> JobResponse:
    job = await session.scalar(
        select(Job).where(Job.id == job_id).options(selectinload(Job.requirements))
    )
    if job is None:
        raise ApiError(status_code=404, code="job_not_found", message="Job not found.")

    if context.role == UserRole.PROJECT_MANAGER and job.manager_user_id != context.user_id:
        raise ApiError(status_code=403, code="forbidden_job_access", message="Job does not belong to this manager.")
    if context.role == UserRole.CANDIDATE and job.status != "ACTIVE":
        raise ApiError(status_code=403, code="forbidden_job_access", message="Job is not available.")

    return _job_to_response(job)


@router.put("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: str,
    payload: JobUpdateRequest,
    request: Request,
    context: AuthContext = Depends(manager_only),
    session: AsyncSession = Depends(get_db_session),
) -> JobResponse:
    job = await session.scalar(
        select(Job).where(Job.id == job_id).options(selectinload(Job.requirements))
    )
    if job is None:
        raise ApiError(status_code=404, code="job_not_found", message="Job not found.")
    if context.role == UserRole.PROJECT_MANAGER and job.manager_user_id != context.user_id:
        raise ApiError(status_code=403, code="forbidden_job_access", message="Job does not belong to this manager.")

    updates = payload.model_dump(exclude_none=True)
    requirements = updates.pop("requirements", None)
    if "question_blueprint" in updates:
        updates["question_blueprint"] = [
            QuestionBlueprintItem.model_validate(item).model_dump(mode="json")
            for item in updates["question_blueprint"]
        ]
    for key, value in updates.items():
        setattr(job, key, value)

    if requirements is not None:
        for existing in list(job.requirements):
            await session.delete(existing)
        await session.flush()
        for requirement in requirements:
            requirement_payload = (
                requirement.model_dump()
                if hasattr(requirement, "model_dump")
                else requirement
            )
            session.add(
                RoleRequirement(
                    job_id=job.id,
                    requirement_type=requirement_payload["requirement_type"],
                    label=requirement_payload["label"],
                    weight=requirement_payload["weight"],
                )
            )

    audit_service = AuditService(session)
    await audit_service.record(
        context=context,
        action="jobs.update",
        resource_type="job",
        resource_id=job.id,
        request=request,
        metadata={"fields": sorted(list(updates.keys()))},
    )

    await session.commit()
    refreshed = await session.scalar(
        select(Job).where(Job.id == job.id).options(selectinload(Job.requirements))
    )
    if refreshed is None:
        raise ApiError(status_code=500, code="job_persistence_failed", message="Could not load updated job.")
    return _job_to_response(refreshed)


@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    request: Request,
    context: AuthContext = Depends(manager_only),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    job = await session.get(Job, job_id)
    if job is None:
        raise ApiError(status_code=404, code="job_not_found", message="Job not found.")
    if context.role == UserRole.PROJECT_MANAGER and job.manager_user_id != context.user_id:
        raise ApiError(status_code=403, code="forbidden_job_access", message="Job does not belong to this manager.")

    await session.delete(job)

    audit_service = AuditService(session)
    await audit_service.record(
        context=context,
        action="jobs.delete",
        resource_type="job",
        resource_id=job_id,
        request=request,
    )

    await session.commit()
    return {"message": "Job deleted successfully."}


@router.post("/{job_id}/rank-candidates", response_model=RankingResponse)
async def rank_candidates(
    job_id: str,
    payload: RankingRequest,
    request: Request,
    context: AuthContext = Depends(manager_only),
    session: AsyncSession = Depends(get_db_session),
) -> RankingResponse:
    job = await session.get(Job, job_id)
    if job is None:
        raise ApiError(status_code=404, code="job_not_found", message="Job not found.")
    if context.role == UserRole.PROJECT_MANAGER and job.manager_user_id != context.user_id:
        raise ApiError(status_code=403, code="forbidden_job_access", message="Job does not belong to this manager.")

    ranking_service = RankingService(session)
    outcome = await ranking_service.run_ranking(
        job=job,
        payload=payload,
        context=context,
        request=request,
    )

    return RankingResponse(
        ranking_result_id=outcome.ranking_result.id,
        report_run_id=outcome.ranking_result.report_run_id,
        total_candidates=outcome.ranking_result.total_candidates,
        invited_top_n=outcome.ranking_result.invited_top_n,
        matches=[
            _candidate_match_response(
                match,
                _ranking_source_map(outcome.ranking_result.ranking_payload),
            )
            for match in outcome.matches
        ],
    )


@router.get("/{job_id}/rankings/latest", response_model=RankingResponse)
async def get_latest_ranking(
    job_id: str,
    context: AuthContext = Depends(manager_only),
    session: AsyncSession = Depends(get_db_session),
) -> RankingResponse:
    job = await session.get(Job, job_id)
    if job is None:
        raise ApiError(status_code=404, code="job_not_found", message="Job not found.")
    if context.role == UserRole.PROJECT_MANAGER and job.manager_user_id != context.user_id:
        raise ApiError(status_code=403, code="forbidden_job_access", message="Job does not belong to this manager.")

    ranking_service = RankingService(session)
    ranking = await ranking_service.get_latest_ranking(job_id=job_id)
    if ranking is None:
        raise ApiError(status_code=404, code="ranking_not_found", message="No ranking exists for this job.")

    return RankingResponse(
        ranking_result_id=ranking.id,
        report_run_id=ranking.report_run_id,
        total_candidates=ranking.total_candidates,
        invited_top_n=ranking.invited_top_n,
        matches=[
            _candidate_match_response(
                match,
                _ranking_source_map(ranking.ranking_payload),
            )
            for match in sorted(ranking.matches, key=lambda item: item.rank)
        ],
    )


@router.get("/{job_id}/candidates", response_model=JobCandidatesResponse)
async def list_job_candidates(
    job_id: str,
    context: AuthContext = Depends(manager_only),
    session: AsyncSession = Depends(get_db_session),
) -> JobCandidatesResponse:
    job = await session.get(Job, job_id)
    if job is None:
        raise ApiError(status_code=404, code="job_not_found", message="Job not found.")
    if context.role == UserRole.PROJECT_MANAGER and job.manager_user_id != context.user_id:
        raise ApiError(status_code=403, code="forbidden_job_access", message="Job does not belong to this manager.")

    ranking_service = RankingService(session)
    ranking = await ranking_service.get_latest_ranking(job_id=job_id)
    if ranking is None:
        return JobCandidatesResponse(
            job_id=job_id,
            ranking_result_id=None,
            report_run_id=None,
            candidates=[],
        )

    candidates = _job_candidate_responses(ranking)

    return JobCandidatesResponse(
        job_id=job_id,
        ranking_result_id=ranking.id,
        report_run_id=ranking.report_run_id,
        candidates=candidates,
    )


@router.get("/{job_id}/candidates/{match_id}/profile", response_model=CandidateProfileAIResponse)
async def get_candidate_profile_ai(
    job_id: str,
    match_id: str,
    candidate_external_id: str | None = None,
    context: AuthContext = Depends(manager_only),
    session: AsyncSession = Depends(get_db_session),
) -> CandidateProfileAIResponse:
    job = await session.get(Job, job_id)
    if job is None:
        raise ApiError(status_code=404, code="job_not_found", message="Job not found.")
    if context.role == UserRole.PROJECT_MANAGER and job.manager_user_id != context.user_id:
        raise ApiError(status_code=403, code="forbidden_job_access", message="Job does not belong to this manager.")

    match = await session.scalar(
        select(CandidateMatch)
        .join(RankingResult, CandidateMatch.ranking_result_id == RankingResult.id)
        .where(
            CandidateMatch.id == match_id,
            RankingResult.job_id == job_id,
        )
    )

    if match is None and candidate_external_id:
        match = await session.scalar(
            select(CandidateMatch)
            .join(RankingResult, CandidateMatch.ranking_result_id == RankingResult.id)
            .where(
                RankingResult.job_id == job_id,
                CandidateMatch.candidate_external_id == candidate_external_id,
            )
            .order_by(RankingResult.created_at.desc(), CandidateMatch.rank.asc())
        )

    if match is None:
        raise ApiError(status_code=404, code="candidate_match_not_found", message="Candidate match not found for this job.")

    ranking = await session.get(RankingResult, match.ranking_result_id)
    if ranking is None:
        raise ApiError(
            status_code=404,
            code="ranking_not_found",
            message="Ranking result not found for this candidate match.",
        )

    analysis_query = select(ResumeAnalysis).where(
        ResumeAnalysis.job_id == job_id,
        ResumeAnalysis.candidate_external_id == match.candidate_external_id,
    )
    if ranking.report_run_id:
        analysis_query = analysis_query.where(ResumeAnalysis.report_run_id == ranking.report_run_id)

    analysis = await session.scalar(analysis_query.order_by(ResumeAnalysis.created_at.desc()))
    if analysis is None and ranking.report_run_id:
        analysis = await session.scalar(
            select(ResumeAnalysis)
            .where(
                ResumeAnalysis.job_id == job_id,
                ResumeAnalysis.candidate_external_id == match.candidate_external_id,
            )
            .order_by(ResumeAnalysis.created_at.desc())
        )

    raw_payload = analysis.raw_payload if analysis and isinstance(analysis.raw_payload, dict) else {}
    llm_summary = _read_text(raw_payload.get("llm_summary"))
    summary = _read_text(raw_payload.get("summary"))
    reasons = _read_text_list(raw_payload.get("reasons"))
    suggestions = _read_text_list(raw_payload.get("suggestions"))
    issues = _read_text_list(raw_payload.get("issues"))
    matched_keywords = _read_text_list(raw_payload.get("matched_keywords"))
    missing_keywords = _read_text_list(raw_payload.get("missing_keywords"))
    relative_path = _read_text(raw_payload.get("relative_path"))
    sections = _read_mapping(raw_payload.get("sections"))
    formatting_signals = _read_mapping(raw_payload.get("formatting_signals"))
    parsed_resume = _read_mapping(raw_payload.get("parsed_resume"))
    experience_timeline = (
        _read_dict_list(raw_payload.get("experience"))
        or _read_dict_list(raw_payload.get("experiences"))
        or _read_dict_list(parsed_resume.get("experience"))
        or _read_dict_list(parsed_resume.get("experiences"))
    )
    projects = _read_dict_list(raw_payload.get("projects")) or _read_dict_list(parsed_resume.get("projects"))
    education = _read_dict_list(raw_payload.get("education")) or _read_dict_list(parsed_resume.get("education"))
    contact = _read_mapping(raw_payload.get("contact"))
    if not contact:
        contact = _compact_mapping(
            {
                "email": match.candidate_email or (analysis.candidate_email if analysis else None),
                "phone": _read_text(raw_payload.get("phone")),
                "location": _read_text(raw_payload.get("location")),
                "linkedin": _read_text(raw_payload.get("linkedin")),
            }
        )

    fallback_reasons = list(analysis.reasons) if analysis else []
    explanation_reasons = [item.strip() for item in (match.explanation or "").split("|") if item.strip()]
    signal_scores = _compact_mapping(
        {
            "final_score": analysis.final_score if analysis else match.final_score,
            "ats_score": analysis.ats_score if analysis else match.ats_score,
            "keyword_score": _read_float(raw_payload.get("keyword_score")),
            "semantic_similarity": _read_float(raw_payload.get("semantic_similarity")),
            "formatting_score": _read_float(raw_payload.get("formatting_score")),
            "quality_score": _read_float(raw_payload.get("quality_score")),
            "experience_relevance_score": _read_float(raw_payload.get("experience_relevance_score")),
            "section_completeness_score": _read_float(raw_payload.get("section_completeness_score")),
            "retrieval_score": _read_float(raw_payload.get("retrieval_score")),
            "graph_score": _read_float(raw_payload.get("graph_score")),
            "reranker_score": _read_float(raw_payload.get("reranker_score")),
            "parsing_quality_score": _read_float(raw_payload.get("parsing_quality_score")),
        }
    )
    gemini_service = GeminiService()
    gemini_profile = await gemini_service.compose_candidate_profile_summary(
        candidate_name=match.candidate_name,
        job_title=job.title,
        job_description=job.jd_text,
        current_title=_read_text(raw_payload.get("current_title")),
        matched_keywords=matched_keywords,
        missing_keywords=missing_keywords,
        reasons=reasons or fallback_reasons or explanation_reasons,
        summary=summary,
        llm_summary=llm_summary,
        signals=signal_scores,
    )

    return CandidateProfileAIResponse(
        candidate_external_id=match.candidate_external_id,
        candidate_name=match.candidate_name,
        candidate_email=match.candidate_email,
        summary=summary or llm_summary or (match.explanation or None),
        gemini_summary=gemini_profile.summary,
        llm_summary=llm_summary,
        reasons=reasons or fallback_reasons or explanation_reasons,
        suggestions=suggestions,
        issues=issues,
        matched_keywords=matched_keywords,
        missing_keywords=missing_keywords,
        source=_read_text(raw_payload.get("source")),
        current_title=_read_text(raw_payload.get("current_title")),
        relative_path=relative_path,
        match_explanation=match.explanation or None,
        parsed_resume=parsed_resume,
        contact=contact,
        experience_timeline=experience_timeline,
        projects=projects,
        education=education,
        signals=signal_scores,
        sections=sections,
        formatting_signals=formatting_signals,
        generated_at=_read_datetime(raw_payload.get("generated_at")),
    )


@router.patch("/{job_id}/candidates/{match_id}/status", response_model=CandidateMatchResponse)
async def update_candidate_status(
    job_id: str,
    match_id: str,
    payload: CandidateStatusUpdateRequest,
    request: Request,
    context: AuthContext = Depends(manager_only),
    session: AsyncSession = Depends(get_db_session),
) -> CandidateMatchResponse:
    job = await session.get(Job, job_id)
    if job is None:
        raise ApiError(status_code=404, code="job_not_found", message="Job not found.")
    if context.role == UserRole.PROJECT_MANAGER and job.manager_user_id != context.user_id:
        raise ApiError(status_code=403, code="forbidden_job_access", message="Job does not belong to this manager.")

    match = await session.scalar(
        select(CandidateMatch)
        .join(RankingResult, CandidateMatch.ranking_result_id == RankingResult.id)
        .where(
            CandidateMatch.id == match_id,
            RankingResult.job_id == job_id,
        )
    )
    if match is None:
        raise ApiError(status_code=404, code="candidate_match_not_found", message="Candidate match not found for this job.")

    match.status = payload.status

    audit_service = AuditService(session)
    await audit_service.record(
        context=context,
        action="jobs.update_candidate_status",
        resource_type="candidate_match",
        resource_id=match.id,
        request=request,
        metadata={"job_id": job_id, "status": payload.status.value},
    )

    await session.commit()
    await session.refresh(match)

    ranking = await session.get(RankingResult, match.ranking_result_id)
    return _candidate_match_response(
        match,
        _ranking_source_map(ranking.ranking_payload if ranking is not None else {}),
    )


@router.post("/resumes/check")
async def proxy_resume_check(
    payload: ResumeCheckProxyRequest,
    context: AuthContext = Depends(manager_only),
) -> dict:
    _ = context
    client = ATSClient()
    return await client.run_resume_check(payload.model_dump())


@router.post("/{job_id}/invites/latest", response_model=AutoInviteResponse)
async def latest_invite_summary(
    job_id: str,
    context: AuthContext = Depends(manager_only),
    session: AsyncSession = Depends(get_db_session),
) -> AutoInviteResponse:
    job = await session.get(Job, job_id)
    if job is None:
        raise ApiError(status_code=404, code="job_not_found", message="Job not found.")
    if context.role == UserRole.PROJECT_MANAGER and job.manager_user_id != context.user_id:
        raise ApiError(status_code=403, code="forbidden_job_access", message="Job does not belong to this manager.")

    ranking_service = RankingService(session)
    ranking = await ranking_service.get_latest_ranking(job_id=job_id)
    if ranking is None:
        raise ApiError(status_code=404, code="ranking_not_found", message="No ranking exists for this job.")

    return AutoInviteResponse(
        ranking_result_id=ranking.id,
        invited_count=ranking.invited_top_n,
        notification_ids=[],
    )


def _read_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _read_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = _read_text(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _read_text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _read_mapping(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _read_dict_list(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []

    normalized: list[dict] = []
    for item in value:
        if isinstance(item, dict):
            normalized.append({str(key): value for key, value in item.items()})
        elif item is not None:
            text = str(item).strip()
            if text:
                normalized.append({"value": text})
    return normalized


def _compact_mapping(value: dict[str, object]) -> dict:
    return {
        key: item
        for key, item in value.items()
        if item not in (None, "", [], {}, ())
    }


def _normalize_question_blueprint(value: object) -> list[QuestionBlueprintItem]:
    if not isinstance(value, list):
        return default_question_blueprint()

    normalized: list[QuestionBlueprintItem] = []
    for entry in value:
        try:
            if isinstance(entry, QuestionBlueprintItem):
                normalized.append(entry)
            elif isinstance(entry, dict):
                normalized.append(QuestionBlueprintItem.model_validate(entry))
        except Exception:
            continue
    return normalized or default_question_blueprint()

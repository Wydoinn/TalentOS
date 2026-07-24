from __future__ import annotations

from fastapi import APIRouter, Body, Depends, File, Query, UploadFile, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.exceptions import ApiError
from app.core.security import AuthContext, decode_auth_token, get_auth_context
from app.models.entities import AssessmentSession
from app.models.enums import UserRole
from app.realtime.ws_manager import ws_manager
from app.schemas.assessment import (
    AnswerSubmitRequest,
    AnswerEvaluationResponse,
    AssessmentFinishRequest,
    AssessmentReportSummaryItem,
    AssessmentReportSummaryResponse,
    AssessmentJoinResponse,
    AssessmentReportResponse,
    AssessmentSessionCreateRequest,
    AssessmentSessionResponse,
    AssessmentHeartbeatRequest,
    AssessmentSpeechTranscriptionResponse,
    AssessmentVisionCheckResponse,
    ProctoringEventIngestRequest,
    QuestionGenerateForSessionRequest,
    QuestionItem,
    SessionQuestionResponse,
)
from app.services.assessment_service import AssessmentService


router = APIRouter(prefix="/assessment", tags=["assessment"])


def _session_response(session) -> AssessmentSessionResponse:
    metadata = session.session_metadata if isinstance(session.session_metadata, dict) else {}
    return AssessmentSessionResponse(
        id=session.id,
        room_id=session.room_id,
        job_id=session.job_id,
        candidate_profile_id=session.candidate_profile_id,
        status=session.status,
        anti_spoof_session_id=session.anti_spoof_session_id,
        heartbeat_at=session.heartbeat_at,
        started_at=session.started_at,
        ended_at=session.ended_at,
        integrity_score=float(session.integrity_score or 0.0),
        termination_reason=(
            str(metadata.get("termination_reason"))
            if metadata.get("termination_reason")
            else None
        ),
        question_blueprint=list(metadata.get("question_blueprint") or []),
    )


@router.post("/sessions", response_model=AssessmentSessionResponse)
async def create_assessment_session(
    payload: AssessmentSessionCreateRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> AssessmentSessionResponse:
    if context.role == UserRole.CANDIDATE and context.email and context.email.lower() != payload.candidate_email.lower():
        raise ApiError(
            status_code=403,
            code="candidate_email_mismatch",
            message="Candidate can only create sessions for their own email.",
        )

    service = AssessmentService(session)
    record = await service.create_session(payload=payload, context=context, request=None)
    return _session_response(record)


@router.post("/sessions/{session_id}/join", response_model=AssessmentJoinResponse)
async def join_assessment_session(
    session_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> AssessmentJoinResponse:
    service = AssessmentService(session)
    record = await service.join_session(session_id=session_id, context=context, request=None)
    return AssessmentJoinResponse(
        session=_session_response(record),
        websocket_url=f"/assessment/ws/{record.room_id}",
    )


@router.post("/sessions/{session_id}/heartbeat", response_model=AssessmentSessionResponse)
async def heartbeat(
    session_id: str,
    payload: AssessmentHeartbeatRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> AssessmentSessionResponse:
    service = AssessmentService(session)
    record = await service.heartbeat(
        session_id=session_id,
        status=payload.status,
        context=context,
    )
    return _session_response(record)


@router.get("/sessions/{session_id}/anti-spoof")
async def anti_spoof_status(
    session_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    service = AssessmentService(session)
    return await service.get_anti_spoof_status(
        session_id=session_id,
        context=context,
    )


@router.post("/sessions/{session_id}/anti-spoof/challenge")
async def anti_spoof_issue_challenge(
    session_id: str,
    payload: dict | None = Body(default=None),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    challenge_type: str | None = None
    if isinstance(payload, dict):
        raw = payload.get("challenge_type")
        if isinstance(raw, str) and raw.strip():
            challenge_type = raw.strip()

    service = AssessmentService(session)
    return await service.issue_anti_spoof_challenge(
        session_id=session_id,
        context=context,
        challenge_type=challenge_type,
    )


@router.post("/sessions/{session_id}/anti-spoof/analyze")
async def anti_spoof_analyze(
    session_id: str,
    video: UploadFile = File(...),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    video_bytes = await video.read()
    try:
        service = AssessmentService(session)
        return await service.analyze_anti_spoof(
            session_id=session_id,
            context=context,
            video_bytes=video_bytes,
            filename=video.filename or "anti-spoof.webm",
            content_type=video.content_type or "video/webm",
        )
    finally:
        await video.close()


@router.post("/sessions/{session_id}/anti-spoof/finalize")
async def anti_spoof_finalize(
    session_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    service = AssessmentService(session)
    return await service.finalize_anti_spoof(
        session_id=session_id,
        context=context,
    )


@router.post("/sessions/{session_id}/questions", response_model=SessionQuestionResponse)
async def generate_questions(
    session_id: str,
    payload: QuestionGenerateForSessionRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> SessionQuestionResponse:
    service = AssessmentService(session)
    questions = await service.generate_questions(
        session_id=session_id,
        payload=payload,
        context=context,
    )
    return SessionQuestionResponse(
        questions=[
            QuestionItem(
                id=question.id,
                stage=question.stage,
                prompt=question.prompt,
                rubric=question.rubric,
                source=question.source.value if getattr(question, "source", None) else None,
                sequence_no=question.sequence_no,
            )
            for question in questions
        ]
    )


@router.post("/sessions/{session_id}/answers", response_model=AnswerEvaluationResponse)
async def submit_answer(
    session_id: str,
    payload: AnswerSubmitRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> AnswerEvaluationResponse:
    service = AssessmentService(session)
    answer = await service.submit_answer(session_id=session_id, payload=payload, context=context)
    eval_data = answer.evaluation or {}
    return AnswerEvaluationResponse(
        answer_id=answer.id,
        score=float(answer.score or 0.0),
        confidence=float(answer.confidence or 0.0),
        is_off_topic=bool(answer.is_off_topic),
        classification=str(eval_data.get("classification") or "needs_review"),
        reasons=[str(item) for item in eval_data.get("reasons", [])] if isinstance(eval_data.get("reasons"), list) else [],
        model=str(eval_data.get("model") or "fallback"),
        fallback_used=bool(eval_data.get("fallback_used", False)),
    )


@router.post("/sessions/{session_id}/transcribe", response_model=AssessmentSpeechTranscriptionResponse)
async def transcribe_answer_audio(
    session_id: str,
    audio: UploadFile = File(...),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> AssessmentSpeechTranscriptionResponse:
    audio_bytes = await audio.read()
    try:
        service = AssessmentService(session)
        payload = await service.transcribe_answer_audio(
            session_id=session_id,
            context=context,
            audio_bytes=audio_bytes,
        )
        return AssessmentSpeechTranscriptionResponse(**payload)
    finally:
        await audio.close()


@router.post("/sessions/{session_id}/vision-check", response_model=AssessmentVisionCheckResponse)
async def analyze_vision_frame(
    session_id: str,
    image: UploadFile = File(...),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> AssessmentVisionCheckResponse:
    image_bytes = await image.read()
    try:
        service = AssessmentService(session)
        payload = await service.analyze_vision_frame(
            session_id=session_id,
            context=context,
            image_bytes=image_bytes,
        )
        return AssessmentVisionCheckResponse(**payload)
    finally:
        await image.close()


@router.post("/sessions/{session_id}/proctor-events")
async def ingest_proctor_event(
    session_id: str,
    payload: ProctoringEventIngestRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    service = AssessmentService(session)
    event = await service.ingest_proctor_event(session_id=session_id, payload=payload, context=context)
    assessment_session = await session.get(AssessmentSession, session_id)
    room_id = assessment_session.room_id if assessment_session else f"room-{session_id}"
    metadata = (
        assessment_session.session_metadata
        if assessment_session and isinstance(assessment_session.session_metadata, dict)
        else {}
    )
    last_policy = metadata.get("last_proctor_policy") if isinstance(metadata.get("last_proctor_policy"), dict) else {}
    await ws_manager.broadcast(
        room_id=room_id,
        payload={
            "event": "proctoring_event",
            "session_id": session_id,
            "room_id": room_id,
            "event_type": event.event_type,
            "severity": event.severity.value,
            "timestamp": event.event_timestamp.isoformat(),
            "payload": event.payload,
            "session_status": assessment_session.status.value if assessment_session else None,
            "integrity_score": float(assessment_session.integrity_score or 0.0) if assessment_session else None,
            "termination_reason": metadata.get("termination_reason"),
            "event_count": last_policy.get("event_count"),
            "should_acknowledge": last_policy.get("should_acknowledge"),
            "warning_message": last_policy.get("warning_message"),
        },
    )
    return {
        "event_id": event.id,
        "status": "ingested",
        "session_status": assessment_session.status.value if assessment_session else None,
        "termination_reason": metadata.get("termination_reason"),
        "event_count": last_policy.get("event_count"),
        "should_acknowledge": bool(last_policy.get("should_acknowledge", False)),
        "warning_message": last_policy.get("warning_message"),
    }


@router.post("/sessions/{session_id}/finish", response_model=AssessmentReportResponse)
async def finish_assessment(
    session_id: str,
    payload: AssessmentFinishRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> AssessmentReportResponse:
    service = AssessmentService(session)
    report = await service.finish_session(
        session_id=session_id,
        payload=payload,
        context=context,
        request=None,
    )
    return AssessmentReportResponse(
        assessment_session_id=report.assessment_session_id,
        technical_score=report.technical_score,
        communication_score=report.communication_score,
        integrity_score=report.integrity_score,
        coding_score=report.coding_score,
        overall_score=report.overall_score,
        decision=report.decision,
        section_scores=dict(report.section_scores or {}),
        reasons=list(report.reasons or []),
        flagged_events_timeline=list(report.flagged_events_timeline or []),
        question_results=list(report.question_results or []),
        proctor_summary=report.proctor_summary,
        termination_reason=report.termination_reason,
        summary=report.summary,
        generated_by_model=report.generated_by_model,
    )


@router.get("/sessions/{session_id}/report", response_model=AssessmentReportResponse)
async def get_assessment_report(
    session_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> AssessmentReportResponse:
    service = AssessmentService(session)
    report = await service.get_report(session_id=session_id, context=context)
    return AssessmentReportResponse(
        assessment_session_id=report.assessment_session_id,
        technical_score=report.technical_score,
        communication_score=report.communication_score,
        integrity_score=report.integrity_score,
        coding_score=report.coding_score,
        overall_score=report.overall_score,
        decision=report.decision,
        section_scores=dict(report.section_scores or {}),
        reasons=list(report.reasons or []),
        flagged_events_timeline=list(report.flagged_events_timeline or []),
        question_results=list(report.question_results or []),
        proctor_summary=report.proctor_summary,
        termination_reason=report.termination_reason,
        summary=report.summary,
        generated_by_model=report.generated_by_model,
    )


@router.get("/reports", response_model=AssessmentReportSummaryResponse)
async def list_assessment_reports(
    job_id: str | None = Query(default=None),
    candidate_email: str | None = Query(default=None),
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> AssessmentReportSummaryResponse:
    service = AssessmentService(session)
    items = await service.list_manager_report_summaries(
        context=context,
        job_id=job_id,
        candidate_email=candidate_email,
    )
    return AssessmentReportSummaryResponse(
        items=[
            AssessmentReportSummaryItem(**item)
            for item in items
        ]
    )


@router.websocket("/ws/{room_id}")
async def room_signaling(websocket: WebSocket, room_id: str, token: str = Query(default="")):
    try:
        payload = decode_auth_token(token)
    except Exception:
        await websocket.close(code=4401)
        return

    user_id = str(payload.get("sub") or "unknown")

    await ws_manager.connect(websocket, room_id)
    await ws_manager.broadcast(
        room_id=room_id,
        payload={"event": "user_joined", "room_id": room_id, "user_id": user_id},
    )

    try:
        while True:
            data = await websocket.receive_json()
            await ws_manager.broadcast(
                room_id=room_id,
                payload={
                    "event": "signal",
                    "room_id": room_id,
                    "user_id": user_id,
                    "data": data,
                },
            )
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, room_id)
        await ws_manager.broadcast(
            room_id=room_id,
            payload={"event": "user_left", "room_id": room_id, "user_id": user_id},
        )

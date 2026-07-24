from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.auth import create_session_token, require_session_token
from app.api.schemas import (
    AnalysisResult,
    ChallengeRequest,
    ChallengeResponse,
    ChallengeType,
    CreateSessionRequest,
    CreateSessionResponse,
    DetailResponse,
    FinalizeResponse,
    LockResponse,
    NextAction,
    OverallStatus,
    ReasonCode,
    SessionDetailResponse,
    SessionStatus,
)
from app.config import get_settings
from app.pipeline.challenge_engine import Challenge, ChallengeEngine
from app.pipeline.orchestrator import AntiSpoofingPipeline
from app.session.store import (
    SessionData,
    get_session_store,
    make_challenge_id,
    make_expiry,
    make_session_id,
)
from app.utils.logging import get_logger

router = APIRouter(prefix="/sessions", tags=["sessions"])
settings = get_settings()
logger = get_logger(__name__)

_pipeline = AntiSpoofingPipeline()
_challenge_engine = ChallengeEngine()
_ALLOWED_VIDEO_CONTENT_TYPES = {
    "application/octet-stream",
    "video/avi",
    "video/mp4",
    "video/mpeg",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
    "video/x-msvideo",
}
_WRITE_CONFLICT_DETAILS = {
    SessionStatus.TERMINATED: "Session has been terminated",
    SessionStatus.FINALIZED: "Session is finalized; lock it or create a new session",
    SessionStatus.REVIEW_READY: "Session already has a completed analysis; finalize or lock it",
    SessionStatus.ANALYZING: "Session is currently analyzing another upload",
}


async def _load_session(session_id: str) -> SessionData:
    session = await get_session_store().get(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found or expired",
        )
    return session


async def _verify_token_and_load(
    session_id: str,
    token_payload: dict[str, object] = Depends(require_session_token),
) -> SessionData:
    if token_payload.get("sub") != session_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token does not match requested session",
        )
    return await _load_session(session_id)


def _challenge_response(session_id: str, challenge: Challenge) -> ChallengeResponse:
    return ChallengeResponse(
        session_id=session_id,
        challenge_id=challenge.challenge_id,
        challenge_type=ChallengeType(challenge.challenge_type),
        prompt=challenge.prompt,
        instructions=_challenge_engine.build_instructions(challenge),
        expires_at=challenge.expires_at,
    )


def _detail_http_response(
    description: str,
    *,
    detail: str | None = None,
    examples: dict[str, dict[str, dict[str, str]]] | None = None,
) -> dict:
    content: dict[str, dict] = {"application/json": {}}
    if examples:
        content["application/json"]["examples"] = examples
    elif detail is not None:
        content["application/json"]["example"] = {"detail": detail}

    return {
        "model": DetailResponse,
        "description": description,
        "content": content,
    }


_AUTHENTICATED_SESSION_RESPONSES = {
    401: _detail_http_response(
        "Missing, expired, or invalid bearer token.",
        examples={
            "missing_header": {
                "summary": "Authorization header missing",
                "value": {"detail": "Authorization header required"},
            },
            "expired_token": {
                "summary": "Expired token",
                "value": {"detail": "Token has expired - create a new session"},
            },
            "invalid_token": {
                "summary": "Invalid token",
                "value": {"detail": "Invalid token: signature verification failed"},
            },
        },
    ),
    403: _detail_http_response(
        "Token does not belong to the requested session.",
        detail="Token does not match requested session",
    ),
    404: _detail_http_response(
        "Session was not found or has expired.",
        detail="Session 'session_id' not found or expired",
    ),
}


def _conflict(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=detail,
    )


async def _read_upload_bytes(video: UploadFile) -> bytes:
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    total_bytes = 0
    chunks: list[bytes] = []

    try:
        while True:
            chunk = await video.read(1024 * 1024)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File too large (max {settings.MAX_FILE_SIZE_MB} MB)",
                )
            chunks.append(chunk)
    finally:
        await video.close()

    return b"".join(chunks)


def _validate_video_content_type(video: UploadFile) -> None:
    raw_content_type = (video.content_type or "").lower()
    content_type = raw_content_type.split(";", 1)[0].strip()
    if content_type and content_type not in _ALLOWED_VIDEO_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported media type: {video.content_type}",
        )


def _apply_retry_exhaustion(result: AnalysisResult) -> AnalysisResult:
    updated_reasons = list(dict.fromkeys([*result.reasons, ReasonCode.RETRY_ESCALATED]))
    updated_issues = list(dict.fromkeys([*result.top_issues, ReasonCode.RETRY_ESCALATED.value]))
    summary = result.human_readable_summary.rstrip(".")
    return result.model_copy(
        update={
            "reasons": updated_reasons,
            "top_issues": updated_issues[:5],
            "human_readable_summary": f"{summary}. Retry limit reached; finalize or lock the session.",
            "retry_allowed": False,
            "decision_ready": True,
            "next_action": NextAction.FINALIZE_SESSION,
        }
    )


def _ensure_session_writable(session: SessionData) -> None:
    if session.is_locked():
        raise _conflict("Session is locked and cannot be reused")

    detail = _WRITE_CONFLICT_DETAILS.get(session.status)
    if detail:
        raise _conflict(detail)


def _deserialize_latest_result(session: SessionData) -> AnalysisResult | None:
    if not session.latest_result:
        return None
    try:
        return AnalysisResult(**session.latest_result)
    except Exception as exc:
        logger.debug("Could not deserialize latest result for %s: %s", session.session_id, exc)
        return None


def _next_action_for_status(session_status: SessionStatus) -> NextAction:
    return (
        NextAction.ISSUE_CHALLENGE
        if session_status == SessionStatus.RETRY_REQUIRED
        else NextAction.FINALIZE_SESSION
    )


async def _load_challenge_for_analysis(
    session: SessionData,
    session_id: str,
) -> Challenge:
    if not session.challenge:
        raise _conflict("A challenge must be issued before submitting a video")

    try:
        challenge = Challenge.from_dict(session.challenge)
    except Exception as exc:
        logger.warning("Could not deserialize challenge for %s: %s", session_id, exc)
        raise _conflict("Challenge data is invalid; issue a new challenge") from exc

    if challenge.is_expired():
        session.challenge = None
        session.challenge_verified = False
        session.status = SessionStatus.RETRY_REQUIRED
        await get_session_store().save(session)
        raise _conflict("Challenge expired; issue a new challenge")

    return challenge


def _apply_analysis_result(session: SessionData, result: AnalysisResult) -> AnalysisResult:
    session.retry_count += 1
    session.trust_score = result.trust_score
    session.challenge = None

    retry_exhausted = (
        result.overall_status == OverallStatus.FLAG
        and session.retry_count >= settings.MAX_RETRIES_BEFORE_FAIL
    )
    if result.overall_status == OverallStatus.FLAG and not retry_exhausted:
        session.status = SessionStatus.RETRY_REQUIRED
    else:
        session.status = SessionStatus.REVIEW_READY

    if retry_exhausted:
        session.issue_history.append(ReasonCode.RETRY_ESCALATED.value)
        result = _apply_retry_exhaustion(result)

    return result.model_copy(
        update={
            "retry_allowed": session.status == SessionStatus.RETRY_REQUIRED,
            "session_status": session.status,
            "decision_ready": session.status == SessionStatus.REVIEW_READY,
            "next_action": _next_action_for_status(session.status),
        }
    )


@router.post(
    "",
    response_model=CreateSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new verification session",
)
async def create_session(body: CreateSessionRequest):
    session_id = make_session_id()
    created_at = datetime.now(timezone.utc)
    expires_at = make_expiry()
    token = create_session_token(session_id, body.candidate_id)

    session = SessionData(
        session_id=session_id,
        candidate_id=body.candidate_id,
        job_id=body.job_id,
        metadata=body.metadata,
        status=SessionStatus.CREATED,
        created_at=created_at,
        expires_at=expires_at,
        trust_score=settings.INITIAL_TRUST_SCORE,
    )
    await get_session_store().save(session)
    logger.info("Session created: %s for candidate %r", session_id, body.candidate_id)

    return CreateSessionResponse(
        session_id=session_id,
        candidate_id=body.candidate_id,
        status=SessionStatus.CREATED,
        created_at=created_at,
        expires_at=expires_at,
        access_token=token,
    )


@router.post(
    "/{session_id}/challenge",
    response_model=ChallengeResponse,
    summary="Issue a dynamic liveness challenge",
    responses={
        **_AUTHENTICATED_SESSION_RESPONSES,
        409: _detail_http_response(
            "Session cannot accept a new challenge in its current state.",
            examples={
                "terminated": {
                    "summary": "Terminated session",
                    "value": {"detail": "Session has been terminated"},
                },
                "finalized": {
                    "summary": "Already finalized",
                    "value": {"detail": "Session is finalized; lock it or create a new session"},
                },
                "locked": {
                    "summary": "Locked session",
                    "value": {"detail": "Session is locked and cannot be reused"},
                },
                "review_ready": {
                    "summary": "Decision pending",
                    "value": {"detail": "Session already has a completed analysis; finalize or lock it"},
                },
                "analyzing": {
                    "summary": "Concurrent analysis in progress",
                    "value": {"detail": "Session is currently analyzing another upload"},
                },
            },
        ),
    },
)
async def issue_challenge(
    session_id: str,
    body: ChallengeRequest,
    session: SessionData = Depends(_verify_token_and_load),
):
    _ensure_session_writable(session)

    challenge = _challenge_engine.generate(
        make_challenge_id(),
        body.challenge_type.value if body.challenge_type is not None else None,
        previous_type=session.last_challenge_type,
    )
    session.challenge = challenge.to_dict()
    session.challenge_verified = False
    session.last_challenge_type = challenge.challenge_type
    session.status = SessionStatus.CHALLENGED
    await get_session_store().save(session)

    logger.info(
        "Challenge issued for %s: type=%s prompt=%s",
        session_id,
        challenge.challenge_type,
        challenge.prompt,
    )
    return _challenge_response(session_id, challenge)


@router.post(
    "/{session_id}/analyze",
    response_model=AnalysisResult,
    summary="Submit a video clip for anti-spoofing analysis",
    responses={
        **_AUTHENTICATED_SESSION_RESPONSES,
        409: _detail_http_response(
            "Session or challenge state prevents video analysis.",
            examples={
                "terminated": {
                    "summary": "Terminated session",
                    "value": {"detail": "Session has been terminated"},
                },
                "finalized": {
                    "summary": "Already finalized",
                    "value": {"detail": "Session is finalized; lock it or create a new session"},
                },
                "locked": {
                    "summary": "Locked session",
                    "value": {"detail": "Session is locked and cannot be reused"},
                },
                "review_ready": {
                    "summary": "Decision pending",
                    "value": {"detail": "Session already has a completed analysis; finalize or lock it"},
                },
                "missing_challenge": {
                    "summary": "Challenge missing",
                    "value": {"detail": "A challenge must be issued before submitting a video"},
                },
                "invalid_challenge": {
                    "summary": "Challenge corrupted",
                    "value": {"detail": "Challenge data is invalid; issue a new challenge"},
                },
                "expired_challenge": {
                    "summary": "Challenge expired",
                    "value": {"detail": "Challenge expired; issue a new challenge"},
                },
            },
        ),
        413: _detail_http_response(
            "Uploaded video exceeds the configured file-size limit.",
            detail="File too large (max 50 MB)",
        ),
        415: _detail_http_response(
            "Uploaded media type is not supported.",
            detail="Unsupported media type: application/pdf",
        ),
    },
)
async def analyze_session(
    session_id: str,
    video: UploadFile = File(..., description="4-15 second MP4/WebM video"),
    session: SessionData = Depends(_verify_token_and_load),
):
    _ensure_session_writable(session)

    _validate_video_content_type(video)
    video_bytes = await _read_upload_bytes(video)
    challenge = await _load_challenge_for_analysis(session, session_id)

    session.status = SessionStatus.ANALYZING
    await get_session_store().save(session)

    result = await _pipeline.analyze(
        video_bytes,
        video.filename or "upload.mp4",
        session,
        challenge,
    )
    result = _apply_analysis_result(session, result)

    session.latest_result = result.model_dump(mode="json")
    await get_session_store().save(session)

    logger.info(
        "Analysis complete for %s: status=%s score=%.1f retry_count=%s",
        session_id,
        result.overall_status.value,
        result.overall_score,
        session.retry_count,
    )
    return result


@router.get(
    "/{session_id}",
    response_model=SessionDetailResponse,
    summary="Get session status and latest result",
    responses=_AUTHENTICATED_SESSION_RESPONSES,
)
async def get_session_detail(
    session_id: str,
    session: SessionData = Depends(_verify_token_and_load),
):
    challenge_response: ChallengeResponse | None = None
    if session.challenge:
        try:
            challenge_response = _challenge_response(
                session_id,
                Challenge.from_dict(session.challenge),
            )
        except Exception as exc:
            logger.debug("Skipping invalid challenge payload for %s: %s", session_id, exc)

    latest_result = _deserialize_latest_result(session)

    return SessionDetailResponse(
        session_id=session_id,
        candidate_id=session.candidate_id,
        job_id=session.job_id,
        status=session.status,
        retry_count=session.retry_count,
        trust_score=session.trust_score,
        anomaly_count=session.anomaly_count,
        created_at=session.created_at,
        expires_at=session.expires_at,
        final_decision=session.final_decision,
        finalized_at=session.finalized_at,
        locked_at=session.locked_at,
        challenge=challenge_response,
        latest_result=latest_result,
    )


@router.post(
    "/{session_id}/finalize",
    response_model=FinalizeResponse,
    summary="Finalize session and freeze the current decision",
    responses={
        **_AUTHENTICATED_SESSION_RESPONSES,
        409: _detail_http_response(
            "Session cannot be finalized in its current state.",
            examples={
                "terminated": {
                    "summary": "Terminated session",
                    "value": {"detail": "Session was terminated and cannot be finalized"},
                },
                "locked": {
                    "summary": "Locked session",
                    "value": {"detail": "Session is already locked"},
                },
                "not_ready": {
                    "summary": "No completed decision",
                    "value": {"detail": "Session is not ready to be finalized"},
                },
            },
        ),
    },
)
async def finalize_session(
    session_id: str,
    session: SessionData = Depends(_verify_token_and_load),
):
    if session.status == SessionStatus.TERMINATED:
        raise _conflict("Session was terminated and cannot be finalized")
    if session.is_locked():
        raise _conflict("Session is already locked")

    latest_result = _deserialize_latest_result(session)
    if latest_result is None or session.status not in {SessionStatus.REVIEW_READY, SessionStatus.FINALIZED}:
        raise _conflict("Session is not ready to be finalized")

    finalized_at = session.finalized_at or datetime.now(timezone.utc)
    final_decision = latest_result.overall_status
    session.final_decision = final_decision
    session.finalized_at = finalized_at
    session.status = SessionStatus.FINALIZED
    await get_session_store().save(session)

    logger.info("Session %s finalized with %s", session_id, final_decision.value)
    return FinalizeResponse(
        session_id=session_id,
        final_decision=final_decision,
        result=latest_result,
        finalized_at=finalized_at,
    )


@router.post(
    "/{session_id}/lock",
    response_model=LockResponse,
    summary="Lock a finalized session to prevent reuse",
    responses={
        **_AUTHENTICATED_SESSION_RESPONSES,
        409: _detail_http_response(
            "Session cannot be locked in its current state.",
            examples={
                "terminated": {
                    "summary": "Terminated session",
                    "value": {"detail": "Session was terminated and cannot be locked"},
                },
                "not_finalized": {
                    "summary": "Not finalized yet",
                    "value": {"detail": "Finalize the session before locking it"},
                },
            },
        ),
    },
)
async def lock_session(
    session_id: str,
    session: SessionData = Depends(_verify_token_and_load),
):
    if session.status == SessionStatus.TERMINATED:
        raise _conflict("Session was terminated and cannot be locked")
    if session.is_locked():
        return LockResponse(
            session_id=session_id,
            final_decision=session.final_decision,
            locked_at=session.locked_at or datetime.now(timezone.utc),
        )
    if session.status != SessionStatus.FINALIZED or session.finalized_at is None:
        raise _conflict("Finalize the session before locking it")

    session.status = SessionStatus.LOCKED
    session.locked_at = datetime.now(timezone.utc)
    session.challenge = None
    await get_session_store().save(session)

    logger.info("Session %s locked", session_id)
    return LockResponse(
        session_id=session_id,
        final_decision=session.final_decision,
        locked_at=session.locked_at,
    )

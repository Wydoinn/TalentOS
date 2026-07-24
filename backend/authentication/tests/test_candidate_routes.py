from __future__ import annotations

from sqlalchemy import select

from app.core.security import decode_access_token
from app.db.models import FaceVerificationLog, User
from tests.support import TEST_INVITATION_TOKEN


def _complete_candidate_signup(api, otp_delivery) -> dict[str, object]:
    email = "candidate@example.com"
    send_response = api.send_signup_otp(
        email=email,
        role="CANDIDATE",
        invitation_token=TEST_INVITATION_TOKEN,
    )
    verify_response = api.verify_signup_otp(
        email=email,
        role="CANDIDATE",
        invitation_token=TEST_INVITATION_TOKEN,
    )

    assert send_response.status_code == 200
    assert verify_response.status_code == 200
    assert otp_delivery[-1]["email"] == email
    return verify_response.json()


def _register_candidate_face(api, signup_payload: dict[str, object]) -> dict[str, object]:
    response = api.register_face(token=signup_payload["token"]["access_token"])

    assert response.status_code == 200
    return response.json()


def _prepare_candidate_login(api, otp_delivery) -> dict[str, object]:
    signup_payload = _complete_candidate_signup(api, otp_delivery)
    _register_candidate_face(api, signup_payload)

    send_login_response = api.send_login_otp(
        email="candidate@example.com",
        role="CANDIDATE",
        invitation_token=TEST_INVITATION_TOKEN,
    )
    verify_login_response = api.verify_login_otp(
        email="candidate@example.com",
        role="CANDIDATE",
        invitation_token=TEST_INVITATION_TOKEN,
    )

    assert send_login_response.status_code == 200
    assert verify_login_response.status_code == 200
    return verify_login_response.json()


def test_candidate_signup_requires_face_registration_to_finish(
    api,
    db_session,
    otp_delivery,
    face_environment,
) -> None:
    signup_payload = _complete_candidate_signup(api, otp_delivery)

    assert signup_payload["flow"] == "signup"
    assert signup_payload["role"] == "CANDIDATE"
    assert signup_payload["auth_stage"] == "face_registration_required"
    assert signup_payload["is_authenticated"] is False
    assert signup_payload["face_registered"] is False
    assert signup_payload["can_register_face"] is True
    assert signup_payload["requires_face_verification"] is False
    assert signup_payload["next_step"] == "register_face"

    pending_token_payload = decode_access_token(signup_payload["token"]["access_token"])
    assert pending_token_payload["stage"] == "face_registration_required"

    register_payload = _register_candidate_face(api, signup_payload)

    assert register_payload["face_registered"] is True
    assert register_payload["auth_stage"] == "authenticated"
    assert register_payload["is_authenticated"] is True
    assert register_payload["next_step"] == "authenticated"
    assert register_payload["token"] is not None

    final_token_payload = decode_access_token(register_payload["token"]["access_token"])
    assert final_token_payload["stage"] == "authenticated"

    db_session.expire_all()
    candidate = db_session.scalar(select(User).where(User.email == "candidate@example.com"))
    assert candidate is not None
    assert candidate.face_registered is True
    assert face_environment.stored_embeddings[str(candidate.id)].shape == (512,)


def test_candidate_login_requires_face_verification_after_face_registration(
    api,
    otp_delivery,
    face_environment,
) -> None:
    login_payload = _prepare_candidate_login(api, otp_delivery)

    assert login_payload["flow"] == "login"
    assert login_payload["role"] == "CANDIDATE"
    assert login_payload["auth_stage"] == "face_verification_required"
    assert login_payload["is_authenticated"] is False
    assert login_payload["face_registered"] is True
    assert login_payload["can_register_face"] is False
    assert login_payload["requires_face_verification"] is True
    assert login_payload["next_step"] == "verify_face"
    assert login_payload["face_similarity_threshold"] == 0.6

    pending_token_payload = decode_access_token(login_payload["token"]["access_token"])
    assert pending_token_payload["stage"] == "face_verification_required"

    verify_response = api.verify_face(token=login_payload["token"]["access_token"])

    assert verify_response.status_code == 200
    verify_payload = verify_response.json()
    assert verify_payload["success"] is True
    assert verify_payload["status"] == "VERIFIED"
    assert verify_payload["auth_stage"] == "authenticated"
    assert verify_payload["is_authenticated"] is True
    assert verify_payload["next_step"] == "authenticated"
    assert verify_payload["remaining_attempts"] == 5
    assert verify_payload["token"] is not None

    token_payload = decode_access_token(verify_payload["token"]["access_token"])
    assert token_payload["stage"] == "authenticated"
    assert token_payload["role"] == "CANDIDATE"


def test_candidate_login_without_face_registration_returns_registration_step(
    api,
    otp_delivery,
) -> None:
    signup_payload = _complete_candidate_signup(api, otp_delivery)

    assert signup_payload["auth_stage"] == "face_registration_required"

    send_login_response = api.send_login_otp(
        email="candidate@example.com",
        role="CANDIDATE",
        invitation_token=TEST_INVITATION_TOKEN,
    )
    verify_login_response = api.verify_login_otp(
        email="candidate@example.com",
        role="CANDIDATE",
        invitation_token=TEST_INVITATION_TOKEN,
    )

    assert send_login_response.status_code == 200
    assert verify_login_response.status_code == 200

    login_payload = verify_login_response.json()
    assert login_payload["auth_stage"] == "face_registration_required"
    assert login_payload["is_authenticated"] is False
    assert login_payload["can_register_face"] is True
    assert login_payload["requires_face_verification"] is False
    assert login_payload["next_step"] == "register_face"


def test_candidate_verify_face_returns_failure_and_logs_attempt(
    api,
    db_session,
    otp_delivery,
    face_environment,
) -> None:
    login_payload = _prepare_candidate_login(api, otp_delivery)

    verify_response = api.verify_face(
        token=login_payload["token"]["access_token"],
        image_bytes=b"verification-mismatch",
        device_info="Chrome on Windows",
        user_agent="pytest-agent",
    )

    assert verify_response.status_code == 200
    payload = verify_response.json()
    assert payload["success"] is False
    assert payload["status"] == "FAILED"
    assert payload["auth_stage"] == "face_verification_required"
    assert payload["is_authenticated"] is False
    assert payload["next_step"] == "verify_face"
    assert payload["remaining_attempts"] == 4
    assert payload["token"] is None

    verification_log = db_session.scalar(select(FaceVerificationLog))
    assert verification_log is not None
    assert verification_log.status.value == "FAILED"
    assert verification_log.similarity_score == 0.0
    assert verification_log.device_info == "Chrome on Windows | user-agent=pytest-agent"


def test_candidate_routes_require_authorization(api) -> None:
    register_response = api.register_face(token=None)
    verify_response = api.verify_face(token=None)

    assert register_response.status_code == 401
    assert verify_response.status_code == 401
    assert register_response.json()["error"]["code"] == "missing_token"
    assert verify_response.json()["error"]["code"] == "missing_token"


def test_register_face_rejects_non_image_uploads(
    api,
    otp_delivery,
) -> None:
    signup_payload = _complete_candidate_signup(api, otp_delivery)

    response = api.register_face(
        token=signup_payload["token"]["access_token"],
        image_bytes=b"plain-text",
        filename="not-an-image.txt",
        content_type="text/plain",
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


def test_candidate_signup_requires_invitation_token(api, otp_delivery) -> None:
    response = api.send_signup_otp(email="candidate@example.com", role="CANDIDATE")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "candidate_invitation_required"


def test_candidate_login_requires_invitation_token(api, otp_delivery) -> None:
    _complete_candidate_signup(api, otp_delivery)
    response = api.send_login_otp(email="candidate@example.com", role="CANDIDATE")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "candidate_invitation_required"


def test_candidate_login_bootstraps_new_account_with_invitation(
    api,
    db_session,
    otp_delivery,
) -> None:
    email = "new.invited.candidate@example.com"

    send_response = api.send_login_otp(
        email=email,
        role="CANDIDATE",
        invitation_token=TEST_INVITATION_TOKEN,
    )
    verify_response = api.verify_login_otp(
        email=email,
        role="CANDIDATE",
        invitation_token=TEST_INVITATION_TOKEN,
    )

    assert send_response.status_code == 200
    assert verify_response.status_code == 200
    assert send_response.json()["flow"] == "signup"
    assert otp_delivery[-1]["email"] == email

    payload = verify_response.json()
    assert payload["flow"] == "signup"
    assert payload["auth_stage"] == "face_registration_required"
    assert payload["is_authenticated"] is False
    assert payload["next_step"] == "register_face"

    db_session.expire_all()
    candidate = db_session.scalar(select(User).where(User.email == email))
    assert candidate is not None
    assert candidate.is_email_verified is True

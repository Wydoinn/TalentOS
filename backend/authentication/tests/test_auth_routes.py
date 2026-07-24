from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.security import decode_access_token
from app.db.models import OtpVerification
from tests.support import TEST_INVITATION_TOKEN, TEST_OTP


@pytest.mark.parametrize("role", ["PROJECT_MANAGER"])
def test_project_manager_authenticates_after_signup_and_login(
    api,
    db_session,
    otp_delivery,
    role: str,
) -> None:
    email = f"{role.lower()}@example.com"

    signup_send_response = api.send_signup_otp(email=email, role=role)
    signup_verify_response = api.verify_signup_otp(email=email, role=role)

    assert signup_send_response.status_code == 200
    assert signup_verify_response.status_code == 200
    assert otp_delivery == [{"email": email, "otp_code": TEST_OTP}]

    otp_record = db_session.scalar(select(OtpVerification))
    assert otp_record is not None
    assert otp_record.otp_code != TEST_OTP
    assert otp_record.is_used is True

    signup_payload = signup_verify_response.json()
    assert signup_payload["flow"] == "signup"
    assert signup_payload["role"] == role
    assert signup_payload["auth_stage"] == "authenticated"
    assert signup_payload["is_authenticated"] is True
    assert signup_payload["requires_face_verification"] is False
    assert signup_payload["can_register_face"] is False
    assert signup_payload["next_step"] == "authenticated"
    assert signup_payload["face_registered"] is False
    assert signup_payload["face_similarity_threshold"] is None

    signup_token_payload = decode_access_token(signup_payload["token"]["access_token"])
    assert signup_token_payload["stage"] == "authenticated"
    assert signup_token_payload["role"] == role

    login_send_response = api.send_login_otp(email=email, role=role)
    login_verify_response = api.verify_login_otp(email=email, role=role)

    assert login_send_response.status_code == 200
    assert login_verify_response.status_code == 200
    assert otp_delivery[-1] == {"email": email, "otp_code": TEST_OTP}

    login_payload = login_verify_response.json()
    assert login_payload["flow"] == "login"
    assert login_payload["auth_stage"] == "authenticated"
    assert login_payload["is_authenticated"] is True
    assert login_payload["requires_face_verification"] is False
    assert login_payload["can_register_face"] is False
    assert login_payload["next_step"] == "authenticated"

    login_token_payload = decode_access_token(login_payload["token"]["access_token"])
    assert login_token_payload["stage"] == "authenticated"
    assert login_token_payload["role"] == role


def test_verify_signup_otp_rejects_invalid_code_without_consuming_the_record(
    api,
    db_session,
    otp_delivery,
) -> None:
    email = "manager@example.com"

    send_response = api.send_signup_otp(email=email, role="PROJECT_MANAGER")
    verify_response = api.verify_signup_otp(
        email=email,
        role="PROJECT_MANAGER",
        otp_code="999999",
    )

    assert send_response.status_code == 200
    assert verify_response.status_code == 400
    assert verify_response.json()["error"]["code"] == "invalid_otp"
    assert otp_delivery == [{"email": email, "otp_code": TEST_OTP}]

    otp_record = db_session.scalar(select(OtpVerification))
    assert otp_record is not None
    assert otp_record.is_used is False


def test_login_send_otp_rejects_unknown_account(api, otp_delivery) -> None:
    response = api.send_login_otp(email="missing@example.com", role="PROJECT_MANAGER")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "user_not_found"
    assert otp_delivery == []


def test_signup_send_otp_rejects_existing_account(api, otp_delivery) -> None:
    email = "manager@example.com"

    first_send_response = api.send_signup_otp(email=email, role="PROJECT_MANAGER")
    first_verify_response = api.verify_signup_otp(email=email, role="PROJECT_MANAGER")
    duplicate_send_response = api.send_signup_otp(email=email, role="PROJECT_MANAGER")

    assert first_send_response.status_code == 200
    assert first_verify_response.status_code == 200
    assert duplicate_send_response.status_code == 409
    assert duplicate_send_response.json()["error"]["code"] == "account_already_exists"


def test_auth_routes_reject_role_mismatch_for_existing_email(api, otp_delivery) -> None:
    email = "shared@example.com"

    signup_send_response = api.send_signup_otp(email=email, role="PROJECT_MANAGER")
    signup_verify_response = api.verify_signup_otp(email=email, role="PROJECT_MANAGER")
    signup_mismatch_response = api.send_signup_otp(
        email=email,
        role="CANDIDATE",
        invitation_token=TEST_INVITATION_TOKEN,
    )
    login_mismatch_response = api.send_login_otp(
        email=email,
        role="CANDIDATE",
        invitation_token=TEST_INVITATION_TOKEN,
    )

    assert signup_send_response.status_code == 200
    assert signup_verify_response.status_code == 200
    assert signup_mismatch_response.status_code == 409
    assert login_mismatch_response.status_code == 409
    assert signup_mismatch_response.json()["error"]["code"] == "role_mismatch"
    assert login_mismatch_response.json()["error"]["code"] == "role_mismatch"


def test_candidate_access_validation_route_returns_server_validated_link_state(api, otp_delivery) -> None:
    _ = otp_delivery
    response = api.validate_candidate_access(
        email="candidate@example.com",
        invitation_token=TEST_INVITATION_TOKEN,
        flow="l0_session",
        schedule_id="schedule-001",
        slot_id="slot-001",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["candidate_email"] == "candidate@example.com"
    assert payload["schedule_status"] == "BOOKED"
    assert payload["schedule_id"] == "schedule-001"
    assert payload["slot_id"] == "slot-001"

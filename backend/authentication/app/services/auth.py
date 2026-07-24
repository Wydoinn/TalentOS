from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api_errors import ApiException
from app.core.config import Settings, get_settings
from app.core.enums import AuthFlow, AuthNextStep, AuthStage, UserRole
from app.core.security import (
    TokenBundle,
    create_access_token,
    generate_otp_code,
    hash_otp_code,
    normalize_email,
    verify_otp_code,
)
from app.db.models import OtpVerification, User
from app.services.email import EmailService
from app.services.invitation_access import InvitationAccessService
from app.utils.time import ensure_utc, utcnow


@dataclass(frozen=True, slots=True)
class OTPDispatchResult:
    flow: AuthFlow
    expires_in_seconds: int


@dataclass(frozen=True, slots=True)
class AuthSessionResult:
    user: User
    flow: AuthFlow
    token: TokenBundle
    auth_stage: AuthStage
    is_authenticated: bool
    face_registered: bool
    can_register_face: bool
    requires_face_verification: bool
    next_step: AuthNextStep
    face_similarity_threshold: float | None


class AuthService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        email_service: EmailService | None = None,
        invitation_access_service: InvitationAccessService | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.email_service = email_service or EmailService(self.settings)
        self.invitation_access_service = invitation_access_service or InvitationAccessService(self.settings)

    def send_signup_otp(
        self,
        *,
        email: str,
        role: UserRole,
        invitation_token: str | None = None,
    ) -> OTPDispatchResult:
        normalized_email = normalize_email(email)
        self._assert_candidate_invitation_access(
            email=normalized_email,
            role=role,
            invitation_token=invitation_token,
        )
        self._ensure_signup_allowed(email=normalized_email, role=role)
        return self._issue_otp(email=normalized_email, role=role, flow=AuthFlow.SIGNUP)

    def verify_signup_otp(
        self,
        *,
        email: str,
        role: UserRole,
        otp_code: str,
        invitation_token: str | None = None,
    ) -> AuthSessionResult:
        normalized_email = normalize_email(email)
        self._assert_candidate_invitation_access(
            email=normalized_email,
            role=role,
            invitation_token=invitation_token,
        )
        self._ensure_signup_allowed(email=normalized_email, role=role)
        self._consume_otp(email=normalized_email, role=role, otp_code=otp_code)

        user = User(
            email=normalized_email,
            role=role,
            is_email_verified=True,
        )
        self.db.add(user)
        self._commit_new_user()
        self.db.refresh(user)

        return self._build_auth_session(user=user, flow=AuthFlow.SIGNUP)

    def send_login_otp(
        self,
        *,
        email: str,
        role: UserRole,
        invitation_token: str | None = None,
    ) -> OTPDispatchResult:
        normalized_email = normalize_email(email)
        self._assert_candidate_invitation_access(
            email=normalized_email,
            role=role,
            invitation_token=invitation_token,
        )

        # Invited candidates may use the login entrypoint before their account exists.
        # In that case we bootstrap through signup OTP semantics.
        if role == UserRole.CANDIDATE and self._get_user_by_email(normalized_email) is None:
            return self._issue_otp(email=normalized_email, role=role, flow=AuthFlow.SIGNUP)

        self._require_existing_user(email=normalized_email, role=role)
        return self._issue_otp(email=normalized_email, role=role, flow=AuthFlow.LOGIN)

    def verify_login_otp(
        self,
        *,
        email: str,
        role: UserRole,
        otp_code: str,
        invitation_token: str | None = None,
    ) -> AuthSessionResult:
        normalized_email = normalize_email(email)
        self._assert_candidate_invitation_access(
            email=normalized_email,
            role=role,
            invitation_token=invitation_token,
        )

        if role == UserRole.CANDIDATE and self._get_user_by_email(normalized_email) is None:
            self._consume_otp(email=normalized_email, role=role, otp_code=otp_code)

            user = User(
                email=normalized_email,
                role=role,
                is_email_verified=True,
            )
            self.db.add(user)
            self._commit_new_user()
            self.db.refresh(user)

            return self._build_auth_session(user=user, flow=AuthFlow.SIGNUP)

        user = self._require_existing_user(email=normalized_email, role=role)
        self._consume_otp(email=normalized_email, role=role, otp_code=otp_code)
        user.is_email_verified = True
        user.updated_at = utcnow()
        self.db.add(user)
        self._commit_or_raise(
            message="Unable to complete the login verification right now.",
        )
        self.db.refresh(user)

        return self._build_auth_session(user=user, flow=AuthFlow.LOGIN)

    def _issue_otp(
        self,
        *,
        email: str,
        role: UserRole,
        flow: AuthFlow,
    ) -> OTPDispatchResult:
        otp_code = generate_otp_code(self.settings.otp_length)
        otp_hash = hash_otp_code(email=email, role=role, otp_code=otp_code)
        expires_at = utcnow() + timedelta(minutes=self.settings.otp_expiry_minutes)

        self.db.execute(
            update(OtpVerification)
            .where(
                OtpVerification.email == email,
                OtpVerification.role == role,
                OtpVerification.is_used.is_(False),
            )
            .values(is_used=True)
        )
        otp_record = OtpVerification(
            email=email,
            role=role,
            otp_code=otp_hash,
            expires_at=expires_at,
        )
        self.db.add(otp_record)
        self._commit_or_raise(
            message="Unable to save the OTP request right now.",
            code="otp_persistence_failed",
        )

        try:
            self.email_service.send_otp_email(email=email, otp_code=otp_code)
        except ApiException:
            self.db.execute(
                update(OtpVerification)
                .where(OtpVerification.id == otp_record.id)
                .values(is_used=True)
            )
            self._commit_or_raise(
                message="Unable to update the OTP request state right now.",
                code="otp_persistence_failed",
            )
            raise

        return OTPDispatchResult(
            flow=flow,
            expires_in_seconds=int(
                timedelta(minutes=self.settings.otp_expiry_minutes).total_seconds()
            ),
        )

    def _consume_otp(
        self,
        *,
        email: str,
        role: UserRole,
        otp_code: str,
    ) -> None:
        otp_record = self.db.scalars(
            select(OtpVerification)
            .where(
                OtpVerification.email == email,
                OtpVerification.role == role,
                OtpVerification.is_used.is_(False),
            )
            .order_by(OtpVerification.created_at.desc())
        ).first()

        if otp_record is None:
            raise ApiException(
                status_code=400,
                code="invalid_otp",
                message="The OTP is invalid or has already been used.",
            )

        if ensure_utc(otp_record.expires_at) < utcnow():
            raise ApiException(
                status_code=400,
                code="otp_expired",
                message="The OTP has expired. Request a fresh code.",
            )

        if not verify_otp_code(
            email=email,
            role=role,
            otp_code=otp_code,
            otp_hash=otp_record.otp_code,
        ):
            raise ApiException(
                status_code=400,
                code="invalid_otp",
                message="The OTP is invalid or has already been used.",
            )

        mark_used_result = self.db.execute(
            update(OtpVerification)
            .where(
                OtpVerification.id == otp_record.id,
                OtpVerification.is_used.is_(False),
            )
            .values(is_used=True)
        )
        if mark_used_result.rowcount == 0:
            self.db.rollback()
            raise ApiException(
                status_code=400,
                code="invalid_otp",
                message="The OTP is invalid or has already been used.",
            )

        self._commit_or_raise(
            message="Unable to finalize OTP verification right now.",
            code="otp_persistence_failed",
        )

    def _ensure_signup_allowed(self, *, email: str, role: UserRole) -> None:
        existing_user = self._get_user_by_email(email)
        if existing_user is None:
            return
        if existing_user.role != role:
            raise ApiException(
                status_code=409,
                code="role_mismatch",
                message="This email is already registered with a different role.",
            )
        raise ApiException(
            status_code=409,
            code="account_already_exists",
            message="An account already exists for this email and role. Log in instead.",
        )

    def _require_existing_user(self, *, email: str, role: UserRole) -> User:
        user = self._get_user_by_email(email)
        if user is None:
            message = "No account exists for this email and role. Sign up first."
            if role == UserRole.CANDIDATE:
                message = (
                    "No candidate account is linked to this email yet. "
                    "Candidate access is invitation-only. Please contact your recruiter."
                )
            raise ApiException(
                status_code=404,
                code="user_not_found",
                message=message,
            )
        if user.role != role:
            raise ApiException(
                status_code=409,
                code="role_mismatch",
                message="This email is already registered with a different role.",
            )
        return user

    def _assert_candidate_invitation_access(
        self,
        *,
        email: str,
        role: UserRole,
        invitation_token: str | None,
    ) -> None:
        if role != UserRole.CANDIDATE:
            return

        token = (invitation_token or "").strip()
        if not token:
            raise ApiException(
                status_code=403,
                code="candidate_invitation_required",
                message=(
                    "Candidate access is invitation-only. "
                    "Use the secure link sent by your recruiter."
                ),
            )

        result = self.invitation_access_service.validate_candidate_invitation(
            invitation_token=token,
            candidate_email=email,
        )
        if result.valid:
            return

        raise ApiException(
            status_code=403,
            code="candidate_invitation_invalid",
            message="This invitation link is invalid, expired, or does not match your email.",
        )

    def _build_auth_session(self, *, user: User, flow: AuthFlow) -> AuthSessionResult:
        face_registered = bool(user.face_registered)
        can_register_face = False
        requires_face_verification = False
        auth_stage = AuthStage.AUTHENTICATED
        next_step = AuthNextStep.AUTHENTICATED

        if user.role == UserRole.CANDIDATE:
            if not face_registered:
                can_register_face = True
                auth_stage = AuthStage.FACE_REGISTRATION_REQUIRED
                next_step = AuthNextStep.REGISTER_FACE
            elif flow == AuthFlow.LOGIN:
                requires_face_verification = True
                auth_stage = AuthStage.FACE_VERIFICATION_REQUIRED
                next_step = AuthNextStep.VERIFY_FACE

        token = create_access_token(
            user_id=str(user.id),
            role=user.role,
            stage=auth_stage,
            extra_claims={"email": user.email},
        )

        return AuthSessionResult(
            user=user,
            flow=flow,
            token=token,
            auth_stage=auth_stage,
            is_authenticated=auth_stage == AuthStage.AUTHENTICATED,
            face_registered=face_registered,
            can_register_face=can_register_face,
            requires_face_verification=requires_face_verification,
            next_step=next_step,
            face_similarity_threshold=(
                self.settings.face_similarity_threshold
                if requires_face_verification
                else None
            ),
        )

    def _get_user_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email))

    def _commit_new_user(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ApiException(
                status_code=409,
                code="account_already_exists",
                message="An account already exists for this email and role. Log in instead.",
            ) from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise ApiException(
                status_code=500,
                code="database_error",
                message="Unable to create the user account right now.",
            ) from exc

    def _commit_or_raise(
        self,
        *,
        message: str,
        code: str = "database_error",
    ) -> None:
        try:
            self.db.commit()
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise ApiException(
                status_code=500,
                code=code,
                message=message,
            ) from exc

from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    PROJECT_MANAGER = "PROJECT_MANAGER"
    CANDIDATE = "CANDIDATE"


class FaceVerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


class AuthStage(str, Enum):
    FACE_REGISTRATION_REQUIRED = "face_registration_required"
    FACE_VERIFICATION_REQUIRED = "face_verification_required"
    AUTHENTICATED = "authenticated"


class AuthFlow(str, Enum):
    SIGNUP = "signup"
    LOGIN = "login"


class AuthNextStep(str, Enum):
    AUTHENTICATED = "authenticated"
    REGISTER_FACE = "register_face"
    VERIFY_FACE = "verify_face"

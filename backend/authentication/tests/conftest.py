import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_RUNTIME_DIR = Path(tempfile.mkdtemp(prefix="authentication-tests-"))
TEST_DB_PATH = TEST_RUNTIME_DIR / "test_auth.db"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["APP_ENV"] = "test"
os.environ["APP_NAME"] = "Authentication API"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["AUTH_DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-with-safe-length-123456"
os.environ["AUTH_JWT_SECRET_KEY"] = "test-jwt-secret-key-with-safe-length-123456"
os.environ["OTP_SECRET"] = "test-otp-secret-key-with-safe-length-123456"
os.environ["AUTH_OTP_SECRET"] = "test-otp-secret-key-with-safe-length-123456"
os.environ["SMTP_HOST"] = ""
os.environ["SMTP_FROM_EMAIL"] = ""
os.environ["AUTH_SMTP_HOST"] = ""
os.environ["AUTH_SMTP_FROM_EMAIL"] = ""
os.environ["PINECONE_API_KEY"] = ""
os.environ["PINECONE_INDEX_NAME"] = ""
os.environ["AUTH_PINECONE_API_KEY"] = ""
os.environ["AUTH_PINECONE_INDEX_NAME"] = ""

import app.db.models  # noqa: F401
from app.db.base import Base
from app.core.rate_limit import rate_limiter
from app.db.session import SessionLocal, engine, get_db
from app.main import create_app
from tests.support import AuthenticationApiClient, FakeFaceEnvironment, install_face_services, mock_otp_delivery


def reset_database() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(delete(table))


@pytest.fixture(scope="session", autouse=True)
def setup_database() -> None:
    reset_database()
    yield
    engine.dispose()
    shutil.rmtree(TEST_RUNTIME_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_database() -> None:
    reset_database()
    with rate_limiter._lock:
        rate_limiter._windows.clear()
    yield
    reset_database()
    with rate_limiter._lock:
        rate_limiter._windows.clear()


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def app():
    application = create_app()

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    application.dependency_overrides[get_db] = override_get_db
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def api(client) -> AuthenticationApiClient:
    return AuthenticationApiClient(client)


@pytest.fixture
def otp_delivery(monkeypatch):
    return mock_otp_delivery(monkeypatch)


@pytest.fixture
def face_environment(monkeypatch) -> FakeFaceEnvironment:
    environment = FakeFaceEnvironment()
    install_face_services(monkeypatch, environment)
    return environment

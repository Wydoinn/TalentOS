from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base


settings = get_settings()


def _ensure_sqlite_directory(database_url: URL) -> None:
    database_path = database_url.database
    if not database_path or database_path == ":memory:":
        return
    Path(database_path).expanduser().resolve(strict=False).parent.mkdir(
        parents=True,
        exist_ok=True,
    )


def _build_admin_database_url(database_url: URL) -> URL | None:
    database_name = database_url.database
    if not database_name:
        return None
    return database_url.set(database="postgres")


def _quote_identifier(identifier: str) -> str:
    escaped = identifier.replace('"', '""')
    return '"' + escaped + '"'


def _ensure_database_exists() -> None:
    database_url = make_url(settings.database_url)
    backend_name = database_url.get_backend_name()

    if backend_name == "sqlite":
        _ensure_sqlite_directory(database_url)
        return

    if backend_name != "postgresql" or not database_url.database:
        return

    admin_database_url = _build_admin_database_url(database_url)
    if admin_database_url is None:
        return

    admin_engine = create_engine(
        admin_database_url,
        future=True,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )

    try:
        with admin_engine.connect() as connection:
            database_exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
                {"database_name": database_url.database},
            ).scalar()
            if database_exists:
                return
            connection.execute(
                text(f"CREATE DATABASE {_quote_identifier(database_url.database)}")
            )
    finally:
        admin_engine.dispose()


def _build_engine() -> Engine:
    engine_kwargs: dict[str, object] = {
        "echo": settings.database_echo,
        "future": True,
        "pool_pre_ping": True,
    }

    if settings.database_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        engine_kwargs["pool_size"] = settings.database_pool_size
        engine_kwargs["max_overflow"] = settings.database_max_overflow

    return create_engine(settings.database_url, **engine_kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def init_db() -> None:
    import app.db.models  # noqa: F401

    _ensure_database_exists()
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def check_database_health() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

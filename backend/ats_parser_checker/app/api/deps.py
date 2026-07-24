from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.embedding_model import LocalEmbeddingModel
from app.agents.reranker_model import LocalRerankerModel
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.graph.neo4j_client import Neo4jGraphStore
from app.repositories.candidate_repository import CandidateRepository
from app.repositories.feedback_event_repository import FeedbackEventRepository
from app.repositories.report_run_repository import ATSReportRunRepository
from app.repositories.resume_report_repository import ResumeReportRepository
from app.services.feedback_service import RecruiterFeedbackService
from app.services.resume_analysis_service import ResumeAnalysisService
from app.services.resume_sync_service import ResumeDirectorySyncManager
from app.vectorstore.pinecone_client import PineconeVectorStore


def get_runtime_settings() -> Settings:
    return get_settings()


def get_embedding_model(request: Request) -> LocalEmbeddingModel:
    return request.app.state.embedding_model


def get_resume_sync_manager(request: Request) -> ResumeDirectorySyncManager:
    return request.app.state.resume_sync_manager


def get_reranker_model(request: Request) -> LocalRerankerModel | None:
    return getattr(request.app.state, "reranker_model", None)


def get_vector_store(request: Request) -> PineconeVectorStore:
    return request.app.state.vector_store


def get_graph_store(request: Request) -> Neo4jGraphStore:
    return request.app.state.graph_store


def get_candidate_repository(
    session: AsyncSession = Depends(get_db_session),
) -> CandidateRepository:
    return CandidateRepository(session)


def get_resume_report_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ResumeReportRepository:
    return ResumeReportRepository(session)


def get_report_run_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ATSReportRunRepository:
    return ATSReportRunRepository(session)


def get_feedback_repository(
    session: AsyncSession = Depends(get_db_session),
) -> FeedbackEventRepository:
    return FeedbackEventRepository(session)


def get_feedback_service(
    settings: Settings = Depends(get_runtime_settings),
    feedback_repository: FeedbackEventRepository = Depends(get_feedback_repository),
    report_run_repository: ATSReportRunRepository = Depends(get_report_run_repository),
    report_repository: ResumeReportRepository = Depends(get_resume_report_repository),
) -> RecruiterFeedbackService:
    return RecruiterFeedbackService(
        settings=settings,
        feedback_repository=feedback_repository,
        report_run_repository=report_run_repository,
        report_repository=report_repository,
    )


def get_resume_analysis_service(
    settings: Settings = Depends(get_runtime_settings),
    candidate_repository: CandidateRepository = Depends(get_candidate_repository),
    report_run_repository: ATSReportRunRepository = Depends(get_report_run_repository),
    report_repository: ResumeReportRepository = Depends(get_resume_report_repository),
    feedback_service: RecruiterFeedbackService = Depends(get_feedback_service),
    embedding_model: LocalEmbeddingModel = Depends(get_embedding_model),
    reranker_model: LocalRerankerModel | None = Depends(get_reranker_model),
    vector_store: PineconeVectorStore = Depends(get_vector_store),
    graph_store: Neo4jGraphStore = Depends(get_graph_store),
) -> ResumeAnalysisService:
    return ResumeAnalysisService(
        settings=settings,
        candidate_repository=candidate_repository,
        report_run_repository=report_run_repository,
        report_repository=report_repository,
        feedback_service=feedback_service,
        embedding_model=embedding_model,
        reranker_model=reranker_model,
        vector_store=vector_store,
        graph_store=graph_store,
    )

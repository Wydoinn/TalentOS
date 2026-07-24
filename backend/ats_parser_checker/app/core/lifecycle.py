import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agents.embedding_model import get_embedding_model
from app.agents.reranker_model import get_reranker_model
from app.core.config import get_settings
from app.core.database import dispose_database, init_database
from app.graph.neo4j_client import Neo4jGraphStore
from app.services.resume_sync_service import ResumeDirectorySyncManager
from app.vectorstore.pinecone_client import PineconeVectorStore

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.resume_source_dir.mkdir(parents=True, exist_ok=True)

    await init_database()

    vector_store = PineconeVectorStore(settings)
    try:
        await vector_store.ensure_index()
    except Exception as exc:
        logger.warning("Pinecone startup initialization failed: %s", exc)

    graph_store = Neo4jGraphStore(settings)
    try:
        await graph_store.connect()
    except Exception as exc:
        logger.warning("Neo4j startup initialization failed: %s", exc)

    embedding_model = get_embedding_model(settings.embedding_model_dir)
    reranker_model = None
    if settings.reranker_model_dir.exists():
        reranker_model = get_reranker_model(
            settings.reranker_model_dir,
            batch_size=settings.reranker_batch_size,
        )
    else:
        logger.warning("Reranker model directory not found: %s", settings.reranker_model_dir)

    if settings.model_warmup_on_startup:
        await asyncio.to_thread(embedding_model.warmup)
        if reranker_model is not None:
            await asyncio.to_thread(reranker_model.warmup)

    app.state.vector_store = vector_store
    app.state.graph_store = graph_store
    app.state.embedding_model = embedding_model
    app.state.reranker_model = reranker_model
    app.state.resume_sync_manager = ResumeDirectorySyncManager(
        settings=settings,
        embedding_model=embedding_model,
        vector_store=vector_store,
        graph_store=graph_store,
    )

    resume_watch_task = asyncio.create_task(app.state.resume_sync_manager.watch())
    app.state.resume_watch_task = resume_watch_task

    logger.info("Application startup complete")
    try:
        yield
    finally:
        resume_watch_task.cancel()
        try:
            await resume_watch_task
        except asyncio.CancelledError:
            pass
        await graph_store.close()
        await dispose_database()
        logger.info("Application shutdown complete")

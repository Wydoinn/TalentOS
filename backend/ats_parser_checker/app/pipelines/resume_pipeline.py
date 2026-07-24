from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.agents.embedding_model import LocalEmbeddingModel
from app.graph.neo4j_client import Neo4jGraphStore
from app.vectorstore.pinecone_client import PineconeVectorStore

logger = logging.getLogger(__name__)


class ResumeIngestionPipeline:
    def __init__(
        self,
        *,
        embedding_model: LocalEmbeddingModel,
        vector_store: PineconeVectorStore,
        graph_store: Neo4jGraphStore,
    ) -> None:
        self.embedding_model = embedding_model
        self.vector_store = vector_store
        self.graph_store = graph_store

    async def run(
        self,
        *,
        candidate_id: str,
        search_document: str,
        metadata: dict[str, Any],
        graph_payload: dict[str, Any],
    ) -> None:
        logger.info("Generating embedding for candidate '%s'", candidate_id)
        embedding = await asyncio.wait_for(
            asyncio.to_thread(self.embedding_model.embed_passages, [search_document]),
            timeout=30,
        )
        vector = embedding[0]
        logger.info("Embedding generated for candidate '%s'", candidate_id)

        logger.info("Upserting candidate '%s' into Pinecone", candidate_id)
        await asyncio.wait_for(
            self.vector_store.upsert_candidate(
                candidate_id=candidate_id,
                embedding=vector,
                metadata=metadata,
            ),
            timeout=max(
                30,
                self.vector_store.settings.pinecone_connect_timeout_seconds
                + self.vector_store.settings.pinecone_read_timeout_seconds
                + 10,
            ),
        )
        logger.info("Pinecone upsert completed for candidate '%s'", candidate_id)
        logger.info("Upserting candidate '%s' into Neo4j", candidate_id)
        await asyncio.wait_for(
            self.graph_store.upsert_candidate_profile(
                candidate_id=candidate_id,
                full_name=graph_payload["full_name"],
                source=graph_payload["source"],
                current_title=graph_payload["current_title"],
                total_experience_years=graph_payload["total_experience_years"],
                skills=graph_payload["skills"],
                projects=graph_payload["projects"],
                experiences=graph_payload["experiences"],
                experience_level=graph_payload["experience_level"],
                experience_min_years=graph_payload["experience_min_years"],
                experience_max_years=graph_payload["experience_max_years"],
            ),
            timeout=max(
                45,
                self.graph_store.settings.neo4j_connect_timeout_seconds
                + (self.graph_store.settings.neo4j_query_timeout_seconds * 2)
                + 15,
            ),
        )
        logger.info("Neo4j upsert completed for candidate '%s'", candidate_id)

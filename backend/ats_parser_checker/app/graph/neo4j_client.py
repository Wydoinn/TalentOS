from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from neo4j import AsyncGraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable, SessionExpired

from app.core.ats_rules import get_ats_rules
from app.core.config import Settings
from app.utils.candidate_profile import deduplicate_skills

logger = logging.getLogger(__name__)

_RULES = get_ats_rules()
_RETRIEVAL_RULES = _RULES["retrieval"]
_GRAPH_SCORE_WEIGHTS = _RETRIEVAL_RULES["graph_score_weights"]
_PROJECT_MULTI_SKILL_MATCH_THRESHOLD = _RETRIEVAL_RULES["project_multi_skill_match_threshold"]

SCHEMA_QUERIES = (
    "CREATE CONSTRAINT candidate_id_unique IF NOT EXISTS FOR (candidate:Candidate) REQUIRE candidate.id IS UNIQUE",
    "CREATE CONSTRAINT skill_name_unique IF NOT EXISTS FOR (skill:Skill) REQUIRE skill.name IS UNIQUE",
    "CREATE CONSTRAINT project_key_unique IF NOT EXISTS FOR (project:Project) REQUIRE project.key IS UNIQUE",
    "CREATE CONSTRAINT experience_key_unique IF NOT EXISTS FOR (experience:Experience) REQUIRE experience.key IS UNIQUE",
    "CREATE CONSTRAINT experience_level_name_unique IF NOT EXISTS FOR (level:ExperienceLevel) REQUIRE level.name IS UNIQUE",
    "CREATE INDEX candidate_experience_years IF NOT EXISTS FOR (candidate:Candidate) ON (candidate.total_experience_years)",
    "CREATE INDEX candidate_current_title IF NOT EXISTS FOR (candidate:Candidate) ON (candidate.current_title)",
)


@dataclass(slots=True)
class GraphCandidateScore:
    candidate_id: str
    score: float
    matched_skills: list[str]
    project_validated_skills: list[str] | None = None
    cooccurring_skills: list[str] | None = None
    experience_score: float = 0.0


class Neo4jGraphStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._driver = None
        self._last_error: str | None = None
        self._schema_ready = False

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.neo4j_uri
            and self.settings.neo4j_username
            and self.settings.neo4j_password
        )

    async def connect(self) -> None:
        if not self.enabled:
            return
        if self._driver is None:
            try:
                self._driver = AsyncGraphDatabase.driver(
                    self.settings.neo4j_uri,
                    auth=(self.settings.neo4j_username, self.settings.neo4j_password),
                    connection_timeout=self.settings.neo4j_connect_timeout_seconds,
                )
                await asyncio.wait_for(
                    self._driver.verify_connectivity(),
                    timeout=self.settings.neo4j_connect_timeout_seconds,
                )
                await self._ensure_schema()
                await self._cleanup_legacy_graph()
                self._last_error = None
            except Exception as exc:
                self._last_error = self._error_detail(exc)
                await self._close_driver()
                raise

    async def close(self) -> None:
        await self._close_driver()

    async def upsert_candidate_profile(
        self,
        *,
        candidate_id: str,
        full_name: str,
        source: str,
        current_title: str,
        total_experience_years: float,
        skills: list[str],
        projects: list[dict[str, Any]],
        experiences: list[dict[str, Any]],
        experience_level: str,
        experience_min_years: float,
        experience_max_years: float | None,
    ) -> None:
        if not self.enabled:
            return
        if self._driver is None:
            await self.connect()
        if self._driver is None:
            return
        sanitized_skills = deduplicate_skills(skills)
        sanitized_projects = [
            {
                "key": str(project.get("key") or "").strip(),
                "name": str(project.get("name") or "").strip(),
                "summary": str(project.get("summary") or "").strip(),
                "skills": deduplicate_skills(list(project.get("skills") or [])),
            }
            for project in projects
            if str(project.get("key") or "").strip() and str(project.get("name") or "").strip()
        ]
        sanitized_experiences = [
            {
                "key": str(experience.get("key") or "").strip(),
                "role": str(experience.get("role") or "").strip(),
                "company": str(experience.get("company") or "").strip(),
                "description": str(experience.get("description") or "").strip(),
                "start_date": str(experience.get("start_date") or "").strip(),
                "end_date": str(experience.get("end_date") or "").strip(),
                "skills": deduplicate_skills(list(experience.get("skills") or [])),
            }
            for experience in experiences
            if str(experience.get("key") or "").strip() and str(experience.get("role") or "").strip()
        ]

        async def _operation() -> None:
            async with self._driver.session() as session:
                await self._run_query(
                    session,
                    """
                    MERGE (candidate:Candidate {id: $candidate_id})
                    SET
                        candidate.name = $full_name,
                        candidate.source = $source,
                        candidate.current_title = $current_title,
                        candidate.total_experience_years = $total_experience_years,
                        candidate.updated_at = datetime()
                    """,
                    candidate_id=candidate_id,
                    full_name=full_name,
                    source=source,
                    current_title=current_title,
                    total_experience_years=total_experience_years,
                )
                await self._run_query(
                    session,
                    """
                    MATCH (candidate:Candidate {id: $candidate_id})
                    OPTIONAL MATCH (candidate)-[:HAS_PROJECT]->(project:Project)
                    DETACH DELETE project
                    """,
                    candidate_id=candidate_id,
                )
                await self._run_query(
                    session,
                    """
                    MATCH (candidate:Candidate {id: $candidate_id})
                    OPTIONAL MATCH (candidate)-[:HAS_EXPERIENCE]->(experience:Experience)
                    DETACH DELETE experience
                    """,
                    candidate_id=candidate_id,
                )
                await self._run_query(
                    session,
                    """
                    MATCH (candidate:Candidate {id: $candidate_id})
                    OPTIONAL MATCH (candidate)-[relationship:HAS_SKILL|HAS_EXPERIENCE_LEVEL]->()
                    DELETE relationship
                    """,
                    candidate_id=candidate_id,
                )
                if sanitized_skills:
                    await self._run_query(
                        session,
                        """
                        MATCH (candidate:Candidate {id: $candidate_id})
                        UNWIND $skills AS skill_name
                        MERGE (skill:Skill {name: skill_name})
                        MERGE (candidate)-[:HAS_SKILL]->(skill)
                        """,
                        candidate_id=candidate_id,
                        skills=sanitized_skills,
                    )
                await self._run_query(
                    session,
                    """
                    MATCH (candidate:Candidate {id: $candidate_id})
                    MERGE (level:ExperienceLevel {name: $experience_level})
                    SET
                        level.min_years = $experience_min_years,
                        level.max_years = $experience_max_years
                    MERGE (candidate)-[:HAS_EXPERIENCE_LEVEL]->(level)
                    """,
                    candidate_id=candidate_id,
                    experience_level=experience_level,
                    experience_min_years=experience_min_years,
                    experience_max_years=experience_max_years,
                )
                if sanitized_experiences:
                    await self._run_query(
                        session,
                        """
                        MATCH (candidate:Candidate {id: $candidate_id})
                        UNWIND $experiences AS experience_payload
                        MERGE (experience:Experience {key: experience_payload.key})
                        SET
                            experience.role = experience_payload.role,
                            experience.company = experience_payload.company,
                            experience.description = experience_payload.description,
                            experience.start_date = experience_payload.start_date,
                            experience.end_date = experience_payload.end_date
                        MERGE (candidate)-[:HAS_EXPERIENCE]->(experience)
                        FOREACH (skill_name IN experience_payload.skills |
                            MERGE (skill:Skill {name: skill_name})
                            MERGE (experience)-[:USES_SKILL]->(skill)
                        )
                        """,
                        candidate_id=candidate_id,
                        experiences=sanitized_experiences,
                    )
                if sanitized_projects:
                    await self._run_query(
                        session,
                        """
                        MATCH (candidate:Candidate {id: $candidate_id})
                        UNWIND $projects AS project_payload
                        MERGE (project:Project {key: project_payload.key})
                        SET
                            project.name = project_payload.name,
                            project.summary = project_payload.summary
                        MERGE (candidate)-[:HAS_PROJECT]->(project)
                        FOREACH (skill_name IN project_payload.skills |
                            MERGE (skill:Skill {name: skill_name})
                            MERGE (project)-[:USES_SKILL]->(skill)
                        )
                        """,
                        candidate_id=candidate_id,
                        projects=sanitized_projects,
                    )
        await self._execute_with_retry(_operation)

    async def healthcheck(self, *, fast: bool = False) -> dict[str, str]:
        if not self.enabled:
            return {"status": "disabled", "detail": "Neo4j credentials not configured"}
        if self._driver is None and self._last_error:
            return {"status": "error", "detail": self._last_error}
        if self._driver is None:
            return {"status": "error", "detail": "Neo4j driver is not connected"}
        timeout_seconds = (
            self.settings.healthcheck_timeout_seconds
            if fast
            else self.settings.neo4j_query_timeout_seconds
        )
        try:
            async def _operation() -> None:
                async with self._driver.session() as session:
                    result = await asyncio.wait_for(
                        session.run("RETURN 1 AS health"),
                        timeout=timeout_seconds,
                    )
                    await asyncio.wait_for(
                        result.single(),
                        timeout=timeout_seconds,
                    )

            if fast:
                await _operation()
            else:
                await self._execute_with_retry(_operation)
            self._last_error = None
        except Exception as exc:
            self._last_error = self._error_detail(exc)
            return {"status": "error", "detail": self._last_error}
        return {"status": "ok", "detail": "neo4j"}

    async def clear_candidate_graph(self) -> None:
        if not self.enabled:
            return
        if self._driver is None:
            await self.connect()
        if self._driver is None:
            return

        async def _operation() -> None:
            async with self._driver.session() as session:
                for query in (
                    "MATCH (candidate:Candidate) DETACH DELETE candidate",
                    "MATCH (project:Project) DETACH DELETE project",
                    "MATCH (experience:Experience) DETACH DELETE experience",
                    """
                    MATCH (skill:Skill)
                    WHERE NOT EXISTS { MATCH (:Candidate)-[:HAS_SKILL]->(skill) }
                      AND NOT EXISTS { MATCH (:Project)-[:USES_SKILL]->(skill) }
                      AND NOT EXISTS { MATCH (:Experience)-[:USES_SKILL]->(skill) }
                    DELETE skill
                    """,
                    """
                    MATCH (level:ExperienceLevel)
                    WHERE NOT EXISTS { MATCH (:Candidate)-[:HAS_EXPERIENCE_LEVEL]->(level) }
                    DELETE level
                    """,
                ):
                    await self._run_query(session, query)

        await self._execute_with_retry(_operation)

    async def score_candidates(
        self,
        *,
        candidate_ids: list[str],
        required_skills: list[str],
        required_years: float | None = None,
    ) -> dict[str, GraphCandidateScore]:
        if not self.enabled or not candidate_ids:
            return {}

        normalized_candidate_ids = [candidate_id for candidate_id in candidate_ids if candidate_id]
        normalized_required_skills = deduplicate_skills(required_skills)
        if not normalized_candidate_ids:
            return {}

        if self._driver is None:
            await self.connect()
        if self._driver is None:
            return {}

        async def _operation() -> dict[str, GraphCandidateScore]:
            async with self._driver.session() as session:
                result = await asyncio.wait_for(
                    session.run(
                        """
                        UNWIND $candidate_ids AS candidate_id
                        MATCH (candidate:Candidate {id: candidate_id})
                        OPTIONAL MATCH (candidate)-[:HAS_SKILL]->(skill:Skill)
                        WITH
                            candidate,
                            collect(DISTINCT toLower(skill.name)) AS candidate_skills
                        OPTIONAL MATCH (candidate)-[:HAS_EXPERIENCE]->(experience:Experience)
                        OPTIONAL MATCH (experience)-[:USES_SKILL]->(experience_skill:Skill)
                        WITH
                            candidate,
                            candidate_skills,
                            experience,
                            collect(DISTINCT toLower(experience_skill.name)) AS experience_skill_names
                        WITH
                            candidate,
                            candidate_skills,
                            collect(
                                CASE
                                    WHEN experience IS NULL THEN NULL
                                    ELSE {
                                        key: experience.key,
                                        skills: experience_skill_names,
                                        matched_count: size([skill IN $required_skills WHERE skill IN experience_skill_names])
                                    }
                                END
                            ) AS experience_rows
                        WITH
                            candidate,
                            candidate_skills,
                            [experience_row IN experience_rows WHERE experience_row IS NOT NULL] AS candidate_experiences
                        OPTIONAL MATCH (candidate)-[:HAS_PROJECT]->(project:Project)
                        OPTIONAL MATCH (project)-[:USES_SKILL]->(project_skill:Skill)
                        WITH
                            candidate,
                            candidate_skills,
                            candidate_experiences,
                            project,
                            collect(DISTINCT toLower(project_skill.name)) AS project_skill_names
                        WITH
                            candidate,
                            candidate_skills,
                            candidate_experiences,
                            collect(
                                CASE
                                    WHEN project IS NULL THEN NULL
                                    ELSE {
                                        name: project.name,
                                        skills: project_skill_names,
                                        matched_count: size([skill IN $required_skills WHERE skill IN project_skill_names])
                                    }
                                END
                            ) AS project_rows
                        WITH
                            candidate,
                            candidate_skills,
                            candidate_experiences,
                            [project_row IN project_rows WHERE project_row IS NOT NULL] AS candidate_projects
                        WITH
                            candidate,
                            candidate_skills,
                            candidate_projects,
                            candidate_experiences,
                            reduce(
                                validated = [],
                                project_row IN candidate_projects |
                                validated + [skill IN $required_skills WHERE skill IN project_row.skills]
                            ) AS project_validated_skills,
                            reduce(
                                validated = [],
                                experience_row IN candidate_experiences |
                                validated + [skill IN $required_skills WHERE skill IN experience_row.skills]
                            ) AS experience_validated_skills,
                            [project_row IN candidate_projects WHERE project_row.matched_count >= $project_multi_skill_match_threshold] AS multi_skill_projects
                        RETURN
                            candidate.id AS candidate_id,
                            candidate.total_experience_years AS total_experience_years,
                            [skill IN $required_skills WHERE skill IN candidate_skills] AS matched_skills,
                            project_validated_skills AS project_validated_skills,
                            experience_validated_skills AS experience_validated_skills,
                            reduce(
                                cooccurring = [],
                                project_row IN multi_skill_projects |
                                cooccurring + [skill IN $required_skills WHERE skill IN project_row.skills]
                            ) AS cooccurring_skills,
                            size(multi_skill_projects) AS cooccurrence_project_count,
                            size(candidate_projects) AS project_count
                        """,
                        candidate_ids=normalized_candidate_ids,
                        required_skills=normalized_required_skills,
                        project_multi_skill_match_threshold=_PROJECT_MULTI_SKILL_MATCH_THRESHOLD,
                    ),
                    timeout=self.settings.neo4j_query_timeout_seconds,
                )
                records = await asyncio.wait_for(
                    result.data(),
                    timeout=self.settings.neo4j_query_timeout_seconds,
                )

            total_required = len(normalized_required_skills)
            scores: dict[str, GraphCandidateScore] = {}
            for record in records:
                candidate_id = str(record.get("candidate_id") or "")
                if not candidate_id:
                    continue
                matched_skills = deduplicate_skills(
                    [str(skill) for skill in (record.get("matched_skills") or [])]
                )
                project_validated_skills = deduplicate_skills(
                    [str(skill) for skill in (record.get("project_validated_skills") or [])]
                )
                experience_validated_skills = deduplicate_skills(
                    [str(skill) for skill in (record.get("experience_validated_skills") or [])]
                )
                cooccurring_skills = deduplicate_skills(
                    [str(skill) for skill in (record.get("cooccurring_skills") or [])]
                )
                total_experience_years = float(record.get("total_experience_years") or 0.0)
                project_count = int(record.get("project_count") or 0)
                cooccurrence_project_count = int(record.get("cooccurrence_project_count") or 0)

                skill_overlap = (
                    round(len(matched_skills) / total_required, 4) if total_required else 0.0
                )
                project_validation = (
                    round(len(project_validated_skills) / total_required, 4)
                    if total_required
                    else 0.0
                )
                experience_validation = (
                    round(len(experience_validated_skills) / total_required, 4)
                    if total_required
                    else 0.0
                )
                cooccurrence_strength = (
                    round(cooccurrence_project_count / max(project_count, 1), 4)
                    if project_count
                    else 0.0
                )
                if required_years and required_years > 0:
                    experience_score = round(
                        max(0.0, min(total_experience_years / required_years, 1.0)),
                        4,
                    )
                else:
                    experience_score = 1.0 if total_experience_years > 0 else 0.0

                score = round(
                    (skill_overlap * _GRAPH_SCORE_WEIGHTS["skill_overlap"])
                    + (project_validation * _GRAPH_SCORE_WEIGHTS["project_validation"])
                    + (experience_validation * _GRAPH_SCORE_WEIGHTS["experience_validation"])
                    + (cooccurrence_strength * _GRAPH_SCORE_WEIGHTS["cooccurrence_strength"])
                    + (experience_score * _GRAPH_SCORE_WEIGHTS["experience"]),
                    4,
                )
                scores[candidate_id] = GraphCandidateScore(
                    candidate_id=candidate_id,
                    score=score,
                    matched_skills=matched_skills,
                    project_validated_skills=project_validated_skills,
                    cooccurring_skills=cooccurring_skills,
                    experience_score=experience_score,
                )
            return scores

        try:
            return await self._execute_with_retry(_operation)
        except Exception as exc:
            self._last_error = self._error_detail(exc)
            logger.warning("Neo4j candidate scoring failed: %s", self._last_error)
            return {}

    @staticmethod
    def _error_detail(exc: Exception) -> str:
        return str(exc) or exc.__class__.__name__

    async def _run_query(self, session, query: str, **parameters: Any) -> None:
        result = await asyncio.wait_for(
            session.run(query, **parameters),
            timeout=self.settings.neo4j_query_timeout_seconds,
        )
        await asyncio.wait_for(
            result.consume(),
            timeout=self.settings.neo4j_query_timeout_seconds,
        )

    async def _ensure_schema(self) -> None:
        if self._driver is None or self._schema_ready:
            return
        async with self._driver.session() as session:
            for query in self._schema_queries():
                await self._run_query(session, query)
        self._schema_ready = True

    async def _cleanup_legacy_graph(self) -> None:
        if self._driver is None:
            return
        async with self._driver.session() as session:
            for query in (
                "MATCH ()-[relationship:WORKED_AT]->(:Company) DELETE relationship",
                "MATCH ()-[relationship:AT_COMPANY]->(:Company) DELETE relationship",
                "MATCH (company:Company) DETACH DELETE company",
                "MATCH (:Candidate)-[relationship:HAS_EXPERIENCE]->(:ExperienceLevel) DELETE relationship",
            ):
                await self._run_query(session, query)

    @staticmethod
    def _schema_queries() -> tuple[str, ...]:
        return SCHEMA_QUERIES

    async def _close_driver(self) -> None:
        driver = self._driver
        self._driver = None
        self._schema_ready = False
        if driver is None:
            return

        try:
            await asyncio.wait_for(
                driver.close(),
                timeout=self._close_timeout_seconds(),
            )
        except asyncio.TimeoutError:
            logger.info("Neo4j driver close timed out; continuing shutdown")
        except Exception as exc:
            logger.warning(
                "Neo4j driver close did not finish cleanly: %s",
                self._error_detail(exc),
            )

    def _close_timeout_seconds(self) -> int:
        return self.settings.neo4j_query_timeout_seconds

    async def _execute_with_retry(self, operation):
        try:
            result = await operation()
            self._last_error = None
            return result
        except Exception as exc:
            if not self._is_retryable(exc):
                self._last_error = self._error_detail(exc)
                raise

        await self.close()
        await self.connect()
        result = await operation()
        self._last_error = None
        return result

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, (asyncio.TimeoutError, OSError, ServiceUnavailable, SessionExpired)):
            return True
        if isinstance(exc, Neo4jError):
            try:
                return exc.is_retryable()
            except Exception:
                return False
        return False

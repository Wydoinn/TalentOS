from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agents.embedding_model import LocalEmbeddingModel
from app.agents.reranker_model import LocalRerankerModel
from app.core.ats_rules import get_ats_rules
from app.core.config import Settings
from app.core.exceptions import NotFoundException
from app.graph.neo4j_client import Neo4jGraphStore
from app.models.candidate import Candidate
from app.models.enums import CandidateSource
from app.models.report_run import ATSReportRun
from app.models.resume_report import ResumeReport
from app.repositories.candidate_repository import CandidateRepository
from app.repositories.report_run_repository import ATSReportRunRepository
from app.repositories.resume_report_repository import ResumeReportRepository
from app.schemas.ingestion import StructuredResume
from app.schemas.resume_analysis import (
    ATSSectionStatus,
    ResumeATSReport,
    ResumeCheckRequest,
    ResumeCheckResponse,
    ResumeReportResponse,
)
from app.services.feedback_service import RecruiterFeedbackService
from app.utils.ats import (
    experience_relevance_score,
    heuristic_quality_score,
    inspect_resume_format,
    keyword_scores,
    requested_experience_years,
    section_completeness_score,
    section_status,
)
from app.utils.candidate_profile import (
    RoleProfile,
    infer_role_profile,
    resume_skill_inventory,
    role_alignment_label,
    role_alignment_score,
    role_keywords,
)
from app.utils.ids import generate_report_run_id
from app.utils.retrieval import (
    bm25_score_documents,
    build_lexical_document,
    experience_band,
    jaccard_similarity,
    normalize_score_map,
    phrase_overlap_score,
    tokenize_for_retrieval,
)
from app.utils.scoring import clamp01
from app.utils.text import extract_required_skills
from app.vectorstore.pinecone_client import PineconeVectorStore

logger = logging.getLogger(__name__)

_RULES = get_ats_rules()
_ANALYSIS_RULES = _RULES["analysis"]
_ANALYSIS_LIMITS = _ANALYSIS_RULES["limits"]
_ANALYSIS_REASON_THRESHOLDS = _ANALYSIS_RULES["reason_thresholds"]
_ATS_COMPONENT_WEIGHTS = _ANALYSIS_RULES["ats_component_weights"]
_RETRIEVAL_RULES = _RULES["retrieval"]
_LEXICAL_BLEND = _RETRIEVAL_RULES["lexical_blend"]
_EXACT_MATCH_WEIGHTS = _RETRIEVAL_RULES["exact_match_weights"]
_ROLE_ALIGNMENT_PENALTY_RULES = _RETRIEVAL_RULES["role_alignment_penalty"]
_ROLE_MISMATCH_TOKENS = tuple(_RETRIEVAL_RULES["role_mismatch_tokens"])
_SUMMARY_OVERLAP_STOPWORDS = set(_RETRIEVAL_RULES["summary_overlap_stopwords"])


@dataclass(slots=True)
class RetrievalConfig:
    retrieval_top_k: int
    candidate_pool_size: int
    final_top_k: int


@dataclass(slots=True)
class JobRequirements:
    required_skills: list[str]
    required_years: float | None
    role_keywords: list[str]
    is_senior_role: bool
    role_profile: RoleProfile


@dataclass(slots=True)
class CandidateSearchHit:
    candidate_id: str
    retrieval_score: float | None = None
    vector_score: float | None = None
    lexical_score: float | None = None
    graph_score: float | None = None
    reranker_score: float | None = None
    role_alignment_score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    experience_penalty: float = 0.0
    graph_matched_skills: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CandidateEvaluation:
    candidate: Candidate
    structured_resume: StructuredResume
    hit: CandidateSearchHit
    report: ResumeATSReport


class ResumeAnalysisService:
    def __init__(
        self,
        *,
        settings: Settings,
        candidate_repository: CandidateRepository,
        report_run_repository: ATSReportRunRepository,
        report_repository: ResumeReportRepository,
        feedback_service: RecruiterFeedbackService,
        embedding_model: LocalEmbeddingModel,
        reranker_model: LocalRerankerModel | None,
        vector_store: PineconeVectorStore,
        graph_store: Neo4jGraphStore,
    ) -> None:
        self.settings = settings
        self.candidate_repository = candidate_repository
        self.report_run_repository = report_run_repository
        self.report_repository = report_repository
        self.feedback_service = feedback_service
        self.embedding_model = embedding_model
        self.reranker_model = reranker_model
        self.vector_store = vector_store
        self.graph_store = graph_store

    async def check_resumes(self, payload: ResumeCheckRequest) -> ResumeCheckResponse:
        source_filter = self._source_filter(payload.source)
        config = self._resolve_retrieval_config(payload)
        job_query_text = self._job_query_text(
            job_title=payload.job_title,
            job_description=payload.job_description,
        )
        requirements = self._resolve_job_requirements(
            job_title=payload.job_title,
            job_query_text=job_query_text,
        )
        weight_snapshot = await self.feedback_service.get_weight_snapshot()
        selected_candidates = await self._select_candidates(
            job_query_text=job_query_text,
            source_filter=source_filter,
            config=config,
            requirements=requirements,
        )

        evaluations: list[CandidateEvaluation] = []
        for candidate, hit in selected_candidates:
            structured_resume = StructuredResume.model_validate(candidate.structured_resume)
            report = await self._build_report(
                candidate,
                structured_resume,
                job_query_text,
                hit=hit,
                requirements=requirements,
                ranking_weights=weight_snapshot.weights,
            )
            evaluations.append(
                CandidateEvaluation(
                    candidate=candidate,
                    structured_resume=structured_resume,
                    hit=hit,
                    report=report,
                )
            )

        evaluations.sort(
            key=lambda item: (
                item.report.final_score,
                item.report.ats_score,
                item.report.keyword_score,
                item.report.reranker_score or 0.0,
            ),
            reverse=True,
        )
        eligible_evaluations = [
            item
            for item in evaluations
            if self._matches_threshold(item.report.ats_score, payload.minimum_ats_score)
        ]
        final_evaluations = self._apply_diversity_selection(
            evaluations=eligible_evaluations,
            final_top_k=config.final_top_k,
        )

        for rank, item in enumerate(final_evaluations, start=1):
            item.report.rank = rank

        generated_at = datetime.now(timezone.utc)
        report_run = ATSReportRun(
            id=generate_report_run_id(),
            job_id=payload.job_id,
            job_title=self._resolved_job_title(payload),
            job_description=payload.job_description,
            source=payload.source,
            minimum_ats_score=payload.minimum_ats_score,
            ranking_weights=weight_snapshot.weights,
            feedback_events_analyzed=weight_snapshot.feedback_events_analyzed,
            total_candidates=len(evaluations),
            matched_candidates=len(eligible_evaluations),
        )
        await self.report_run_repository.save(report_run)

        for item in final_evaluations:
            item.report.generated_at = generated_at
            await self.report_repository.save(
                self._build_stored_report(
                    report_run=report_run,
                    candidate=item.candidate,
                    report=item.report,
                )
            )

        await self.report_run_repository.commit()
        response_results = [item.report for item in final_evaluations]
        return self._build_check_response(
            report_run=report_run,
            results=response_results,
            generated_at=generated_at,
        )

    async def get_check_run(self, report_run_id: str) -> ResumeCheckResponse:
        report_run = await self.report_run_repository.get_by_id(report_run_id)
        if report_run is None:
            raise NotFoundException(f"ATS report run '{report_run_id}' was not found")

        stored_reports = await self.report_repository.list_by_run_id(report_run_id)
        ordered_reports = [self._hydrate_report(record) for record in stored_reports]
        response_results = [
            report
            for report in ordered_reports
            if self._matches_threshold(report.ats_score, report_run.minimum_ats_score)
        ]
        generated_at = report_run.updated_at or report_run.created_at or datetime.now(timezone.utc)
        return self._build_check_response(
            report_run=report_run,
            results=response_results,
            generated_at=generated_at,
        )

    async def get_report(self, report_run_id: str, candidate_id: str) -> ResumeReportResponse:
        report_run = await self.report_run_repository.get_by_id(report_run_id)
        if report_run is None:
            raise NotFoundException(f"ATS report run '{report_run_id}' was not found")

        report = await self.report_repository.get_by_run_and_candidate(report_run_id, candidate_id)
        if report is None:
            raise NotFoundException(
                f"No ATS report is available for candidate '{candidate_id}' in run '{report_run_id}'"
            )

        return ResumeReportResponse(
            report_run_id=report_run.id,
            job_id=report_run.job_id,
            job_title=report_run.job_title,
            job_description=report_run.job_description,
            **self._hydrate_report(report).model_dump(),
        )

    async def _select_candidates(
        self,
        *,
        job_query_text: str,
        source_filter: CandidateSource | None,
        config: RetrievalConfig,
        requirements: JobRequirements,
    ) -> list[tuple[Candidate, CandidateSearchHit]]:
        vector_hits = await self._vector_retrieval_hits(
            job_query_text=job_query_text,
            source_filter=source_filter,
            top_k=config.retrieval_top_k,
            requirements=requirements,
        )
        filtered_vector_hits = self._filter_hits_by_metadata(
            search_hits=list((vector_hits or {}).values()),
            requirements=requirements,
            fallback_pool_size=config.candidate_pool_size,
        )
        lexical_hits = await self._lexical_retrieval_hits(
            job_query_text=job_query_text,
            source_filter=source_filter,
            top_k=config.retrieval_top_k,
            required_skills=requirements.required_skills,
            candidate_ids=[hit.candidate_id for hit in filtered_vector_hits] or None,
        )
        retrieval_hits = self._merge_retrieval_hits(
            vector_hits={hit.candidate_id: hit for hit in filtered_vector_hits},
            lexical_hits=lexical_hits or {},
            retrieval_top_k=config.retrieval_top_k,
        )
        if not retrieval_hits:
            return await self._fallback_candidates(source_filter)

        graph_shortlist = await self._apply_graph_scoring(
            search_hits=retrieval_hits,
            required_skills=requirements.required_skills,
            required_years=requirements.required_years,
            candidate_pool_size=config.candidate_pool_size,
        )
        if not graph_shortlist:
            return []

        candidates = await self.candidate_repository.list_by_ids(
            [hit.candidate_id for hit in graph_shortlist]
        )
        if not candidates:
            return []

        shortlist_map = {hit.candidate_id: hit for hit in graph_shortlist}
        candidate_hits = [
            (candidate, shortlist_map[candidate.id])
            for candidate in candidates
            if candidate.id in shortlist_map
        ]
        if not candidate_hits:
            return []

        return await self._apply_reranker(
            candidate_hits=candidate_hits,
            job_query_text=job_query_text,
        )

    async def _vector_retrieval_hits(
        self,
        *,
        job_query_text: str,
        source_filter: CandidateSource | None,
        top_k: int,
        requirements: JobRequirements,
    ) -> dict[str, CandidateSearchHit] | None:
        try:
            query_embedding = await asyncio.wait_for(
                asyncio.to_thread(self.embedding_model.embed_queries, [job_query_text]),
                timeout=30,
            )
            metadata_filter = self._build_pinecone_metadata_filter(requirements)
            query_timeout = max(
                30,
                self.vector_store.settings.pinecone_connect_timeout_seconds
                + self.vector_store.settings.pinecone_read_timeout_seconds
                + 10,
            )
            raw_matches = await asyncio.wait_for(
                self.vector_store.query_candidates(
                    query_embedding=query_embedding[0],
                    top_k=top_k,
                    source=source_filter.value if source_filter else None,
                    metadata_filter=metadata_filter,
                ),
                timeout=query_timeout,
            )
            if metadata_filter and len(raw_matches) < min(top_k, 5):
                raw_matches = await asyncio.wait_for(
                    self.vector_store.query_candidates(
                        query_embedding=query_embedding[0],
                        top_k=top_k,
                        source=source_filter.value if source_filter else None,
                    ),
                    timeout=query_timeout,
                )
        except Exception as exc:
            logger.warning("Vector retrieval unavailable: %s", exc)
            return None

        hits: dict[str, CandidateSearchHit] = {}
        for match in raw_matches:
            score = round(clamp01(match.score), 4)
            existing = hits.get(match.candidate_id)
            if existing is None or score > (existing.vector_score or 0.0):
                hits[match.candidate_id] = CandidateSearchHit(
                    candidate_id=match.candidate_id,
                    vector_score=score,
                    metadata=dict(match.metadata or {}),
                )
        return hits

    async def _lexical_retrieval_hits(
        self,
        *,
        job_query_text: str,
        source_filter: CandidateSource | None,
        top_k: int,
        required_skills: list[str],
        candidate_ids: list[str] | None = None,
    ) -> dict[str, CandidateSearchHit]:
        if candidate_ids:
            candidates = await self.candidate_repository.list_by_ids(candidate_ids)
            if source_filter is not None:
                candidates = [candidate for candidate in candidates if candidate.source == source_filter]
        else:
            candidates = await self.candidate_repository.list_for_ats(source=source_filter)
        if not candidates:
            return {}

        documents: dict[str, str] = {}
        exact_scores: dict[str, float] = {}
        for candidate in candidates:
            structured = StructuredResume.model_validate(candidate.structured_resume)
            lexical_document = build_lexical_document(
                current_title=candidate.current_title,
                summary=candidate.summary,
                skills=structured.skills,
                experience_titles=[item.title for item in structured.experience],
                project_names=[item.name for item in structured.projects],
                project_summaries=[item.summary or "" for item in structured.projects],
            )
            documents[candidate.id] = lexical_document
            exact_scores[candidate.id] = self._lexical_exact_match_score(
                structured_resume=structured,
                lexical_document=lexical_document,
                job_query_text=job_query_text,
                required_skills=required_skills,
            )

        bm25_raw = bm25_score_documents(
            query=job_query_text,
            documents=documents,
        )
        bm25_scores = normalize_score_map(bm25_raw)
        lexical_scores = {
            candidate_id: round(
                (bm25_scores.get(candidate_id, 0.0) * _LEXICAL_BLEND["bm25"])
                + (exact_scores.get(candidate_id, 0.0) * _LEXICAL_BLEND["exact"]),
                4,
            )
            for candidate_id in documents
        }
        top_candidates = sorted(
            lexical_scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:top_k]
        return {
            candidate_id: CandidateSearchHit(
                candidate_id=candidate_id,
                lexical_score=score,
            )
            for candidate_id, score in top_candidates
            if score > 0
        }

    def _merge_retrieval_hits(
        self,
        *,
        vector_hits: dict[str, CandidateSearchHit],
        lexical_hits: dict[str, CandidateSearchHit],
        retrieval_top_k: int,
    ) -> list[CandidateSearchHit]:
        candidate_ids = set(vector_hits) | set(lexical_hits)
        merged_hits: list[CandidateSearchHit] = []
        for candidate_id in candidate_ids:
            vector_score = (
                vector_hits.get(candidate_id).vector_score
                if candidate_id in vector_hits
                else None
            )
            lexical_score = (
                lexical_hits.get(candidate_id).lexical_score
                if candidate_id in lexical_hits
                else None
            )

            retrieval_score = self._hybrid_retrieval_score(
                vector_score=vector_score,
                lexical_score=lexical_score,
            )

            if retrieval_score is None:
                continue

            merged_hits.append(
                CandidateSearchHit(
                    candidate_id=candidate_id,
                    retrieval_score=round(retrieval_score, 4),
                    vector_score=vector_score,
                    lexical_score=lexical_score,
                    metadata=dict(
                        vector_hits.get(candidate_id).metadata
                        if candidate_id in vector_hits
                        else lexical_hits.get(candidate_id).metadata
                    ),
                    experience_penalty=(
                        vector_hits.get(candidate_id).experience_penalty
                        if candidate_id in vector_hits
                        else lexical_hits.get(candidate_id).experience_penalty
                    ),
                )
            )

        merged_hits.sort(
            key=lambda hit: (
                hit.retrieval_score or 0.0,
                hit.vector_score or 0.0,
                hit.lexical_score or 0.0,
            ),
            reverse=True,
        )
        return merged_hits[:retrieval_top_k]

    async def _apply_graph_scoring(
        self,
        *,
        search_hits: list[CandidateSearchHit],
        required_skills: list[str],
        required_years: float | None,
        candidate_pool_size: int,
    ) -> list[CandidateSearchHit]:
        graph_scores = None
        if required_skills or required_years:
            try:
                graph_scores = await self.graph_store.score_candidates(
                    candidate_ids=[hit.candidate_id for hit in search_hits],
                    required_skills=required_skills,
                    required_years=required_years,
                )
            except Exception as exc:
                logger.warning("Neo4j graph scoring failed, continuing without graph boost: %s", exc)
                graph_scores = None

        if graph_scores is not None:
            for hit in search_hits:
                graph_match = graph_scores.get(hit.candidate_id)
                hit.graph_score = graph_match.score if graph_match is not None else 0.0
                hit.graph_matched_skills = (
                    list(graph_match.matched_skills)
                    if graph_match is not None
                    else []
                )

        ranked_hits = sorted(
            search_hits,
            key=lambda hit: (
                self._pre_rerank_score(hit),
                hit.retrieval_score or 0.0,
            ),
            reverse=True,
        )
        return ranked_hits[:candidate_pool_size]

    async def _apply_reranker(
        self,
        *,
        candidate_hits: list[tuple[Candidate, CandidateSearchHit]],
        job_query_text: str,
    ) -> list[tuple[Candidate, CandidateSearchHit]]:
        if not candidate_hits:
            return []

        if self.reranker_model is None:
            return candidate_hits

        documents = [self._build_reranker_document(candidate) for candidate, _ in candidate_hits]
        try:
            scores = await asyncio.wait_for(
                asyncio.to_thread(self.reranker_model.score, job_query_text, documents),
                timeout=max(30, len(documents) * 5),
            )
        except Exception as exc:
            logger.warning("BGE reranker failed, continuing without reranker score: %s", exc)
            return candidate_hits

        reranked_hits: list[tuple[Candidate, CandidateSearchHit]] = []
        for (candidate, hit), score in zip(candidate_hits, scores, strict=False):
            hit.reranker_score = score
            reranked_hits.append((candidate, hit))

        reranked_hits.sort(
            key=lambda item: (
                item[1].reranker_score or 0.0,
                self._pre_rerank_score(item[1]),
                item[1].retrieval_score or 0.0,
            ),
            reverse=True,
        )
        return reranked_hits

    async def _fallback_candidates(
        self,
        source_filter: CandidateSource | None,
    ) -> list[tuple[Candidate, CandidateSearchHit]]:
        candidates = await self.candidate_repository.list_for_ats(source=source_filter)
        return [
            (
                candidate,
                CandidateSearchHit(candidate_id=candidate.id),
            )
            for candidate in candidates
        ]

    async def _build_report(
        self,
        candidate: Candidate,
        structured_resume: StructuredResume,
        job_description: str,
        *,
        hit: CandidateSearchHit,
        requirements: JobRequirements,
        ranking_weights: dict[str, float],
    ) -> ResumeATSReport:
        sections = section_status(structured_resume)
        completeness_score = section_completeness_score(sections)
        keyword_score, matched_keywords, missing_keywords = keyword_scores(
            job_description=job_description,
            candidate_skills=resume_skill_inventory(structured_resume),
        )
        semantic_similarity = await asyncio.to_thread(
            self._semantic_similarity,
            job_description,
            structured_resume.summary,
        )
        formatting_score, formatting_issues, formatting_signals = await asyncio.to_thread(
            inspect_resume_format,
            Path(candidate.file_path),
        )
        heuristic_quality, heuristic_issues, heuristic_suggestions, heuristic_summary = (
            heuristic_quality_score(
                raw_text=candidate.raw_text,
                structured_resume=structured_resume,
                formatting_score_value=formatting_score,
                completeness_score_value=completeness_score,
            )
        )
        candidate_role_profile = infer_role_profile(
            title=structured_resume.current_title or candidate.current_title,
            text=" ".join(
                fragment
                for fragment in (
                    structured_resume.summary,
                    " ".join(project.name for project in structured_resume.projects[: _ANALYSIS_LIMITS["role_projects"]]),
                    " ".join((project.summary or "") for project in structured_resume.projects[: _ANALYSIS_LIMITS["role_projects"]]),
                    " ".join(experience.title for experience in structured_resume.experience[: _ANALYSIS_LIMITS["role_experiences"]]),
                    " ".join((experience.summary or "") for experience in structured_resume.experience[: _ANALYSIS_LIMITS["role_experiences"]]),
                )
                if fragment
            ),
            skills=resume_skill_inventory(structured_resume),
        )
        role_score = role_alignment_score(
            job_profile=requirements.role_profile,
            candidate_profile=candidate_role_profile,
        )
        hit.role_alignment_score = role_score

        issues = list(formatting_issues)
        suggestions = list(heuristic_suggestions)
        if missing_keywords:
            issues.append(
                "Missing relevant keywords: "
                + ", ".join(missing_keywords[: _ANALYSIS_LIMITS["missing_keywords"]])
            )
            suggestions.append(
                "Add the missing role-specific keywords naturally in experience and project sections."
            )
        for section_name, present in sections.items():
            if not present:
                issues.append(f"Missing or weak {section_name} section.")
                suggestions.append(f"Add a clearer {section_name} section for ATS completeness.")
        if structured_resume.parsing_warnings:
            issues.append("Resume parsing confidence is moderate; review extracted experience and project blocks.")
            suggestions.append(
                "Use clearer section headers, consistent bulleting, and standard date ranges to improve parsing quality."
            )
        issues.extend(structured_resume.parsing_warnings)
        issues.extend(heuristic_issues)

        experience_score = experience_relevance_score(
            candidate_years=structured_resume.total_experience_years,
            requested_years=requirements.required_years,
            keyword_score_value=keyword_score,
        )
        hit.experience_penalty = max(
            hit.experience_penalty,
            self._experience_penalty(
                candidate_years=structured_resume.total_experience_years,
                required_years=requirements.required_years,
            ),
        )
        if hit.experience_penalty > 0:
            issues.append(
                "Experience is below the role expectation and ranking has been penalized accordingly."
            )
            suggestions.append(
                "Prioritize candidates closer to the required experience band for this role."
            )
        if role_score < _ANALYSIS_RULES["weak_role_alignment_threshold"]:
            target_role = role_alignment_label(requirements.role_profile) or "the target role"
            issues.append(
                f"Current role alignment is weak for {target_role} responsibilities."
            )
            suggestions.append(
                "Make role alignment explicit in the title, summary, and experience bullets for the target role."
            )
        ats_score = round(
            (
                keyword_score * _ATS_COMPONENT_WEIGHTS["keyword"]
                + semantic_similarity * _ATS_COMPONENT_WEIGHTS["semantic"]
                + formatting_score * _ATS_COMPONENT_WEIGHTS["formatting"]
                + heuristic_quality * _ATS_COMPONENT_WEIGHTS["quality"]
                + experience_score * _ATS_COMPONENT_WEIGHTS["experience"]
                + completeness_score * _ATS_COMPONENT_WEIGHTS["completeness"]
                + role_score * _ATS_COMPONENT_WEIGHTS["role"]
            )
            * 100,
            2,
        )
        final_score = self._final_score(
            hit=hit,
            ats_score=ats_score,
            ranking_weights=ranking_weights,
        )
        reasons = self._build_reasons(
            structured_resume=structured_resume,
            hit=hit,
            job_description=job_description,
            matched_keywords=matched_keywords,
            semantic_similarity=semantic_similarity,
            experience_score=experience_score,
            heuristic_quality=heuristic_quality,
            formatting_score=formatting_score,
        )

        return ResumeATSReport(
            candidate_id=candidate.id,
            candidate_name=candidate.full_name,
            candidate_email=candidate.email,
            current_title=candidate.current_title,
            relative_path=self._relative_path(Path(candidate.file_path)),
            source=candidate.source,
            summary=candidate.summary,
            rank=0,
            ats_score=ats_score,
            final_score=final_score,
            keyword_score=keyword_score,
            semantic_similarity=semantic_similarity,
            formatting_score=formatting_score,
            quality_score=heuristic_quality,
            experience_relevance_score=experience_score,
            section_completeness_score=completeness_score,
            retrieval_score=hit.retrieval_score,
            graph_score=hit.graph_score,
            reranker_score=hit.reranker_score,
            parsing_quality_score=structured_resume.parsing_quality_score,
            parsing_warnings=list(structured_resume.parsing_warnings),
            reasons=reasons,
            issues=self._deduplicate(issues),
            suggestions=self._deduplicate(suggestions),
            missing_keywords=missing_keywords,
            matched_keywords=matched_keywords,
            sections=ATSSectionStatus(**sections),
            formatting_signals=formatting_signals,
            llm_summary=heuristic_summary,
            generated_at=None,
        )

    def _build_stored_report(
        self,
        *,
        report_run: ATSReportRun,
        candidate: Candidate,
        report: ResumeATSReport,
    ) -> ResumeReport:
        return ResumeReport(
            report_run_id=report_run.id,
            candidate_id=candidate.id,
            candidate_name=report.candidate_name,
            current_title=report.current_title,
            source=report.source,
            relative_path=report.relative_path,
            summary=report.summary,
            rank=report.rank,
            ats_score=report.ats_score,
            final_score=report.final_score,
            keyword_score=report.keyword_score,
            semantic_similarity=report.semantic_similarity,
            formatting_score=report.formatting_score,
            quality_score=report.quality_score,
            experience_relevance_score=report.experience_relevance_score,
            section_completeness_score=report.section_completeness_score,
            retrieval_score=report.retrieval_score,
            graph_score=report.graph_score,
            reranker_score=report.reranker_score,
            parsing_quality_score=report.parsing_quality_score,
            parsing_warnings=report.parsing_warnings,
            reasons=report.reasons,
            issues=report.issues,
            suggestions=report.suggestions,
            missing_keywords=report.missing_keywords,
            matched_keywords=report.matched_keywords,
            sections=report.sections.model_dump(),
            formatting_signals=report.formatting_signals,
            llm_summary=report.llm_summary,
        )

    def _hydrate_report(self, report: ResumeReport) -> ResumeATSReport:
        generated_at = report.updated_at or report.created_at or datetime.now(timezone.utc)
        return ResumeATSReport(
            candidate_id=report.candidate_id,
            candidate_name=report.candidate_name,
            candidate_email=None,
            current_title=report.current_title,
            relative_path=report.relative_path or "",
            source=report.source,
            summary=report.summary,
            rank=report.rank,
            ats_score=report.ats_score,
            final_score=report.final_score,
            keyword_score=report.keyword_score,
            semantic_similarity=report.semantic_similarity,
            formatting_score=report.formatting_score,
            quality_score=report.quality_score,
            experience_relevance_score=report.experience_relevance_score,
            section_completeness_score=report.section_completeness_score,
            retrieval_score=report.retrieval_score,
            graph_score=report.graph_score,
            reranker_score=report.reranker_score,
            parsing_quality_score=report.parsing_quality_score,
            parsing_warnings=list(report.parsing_warnings or []),
            reasons=list(report.reasons or []),
            issues=list(report.issues or []),
            suggestions=list(report.suggestions or []),
            missing_keywords=list(report.missing_keywords or []),
            matched_keywords=list(report.matched_keywords or []),
            sections=ATSSectionStatus(**(report.sections or {})),
            formatting_signals=report.formatting_signals or {},
            llm_summary=report.llm_summary,
            generated_at=generated_at,
        )

    def _build_check_response(
        self,
        *,
        report_run: ATSReportRun,
        results: list[ResumeATSReport],
        generated_at: datetime,
    ) -> ResumeCheckResponse:
        return ResumeCheckResponse(
            report_run_id=report_run.id,
            job_id=report_run.job_id,
            job_title=report_run.job_title,
            job_description=report_run.job_description,
            source=report_run.source,
            minimum_ats_score=report_run.minimum_ats_score,
            ranking_weights=dict(report_run.ranking_weights or {}),
            feedback_events_analyzed=report_run.feedback_events_analyzed,
            total_candidates=report_run.total_candidates,
            matched_candidates=report_run.matched_candidates,
            returned_candidates=len(results),
            results=results,
            generated_at=generated_at,
        )

    def _resolve_retrieval_config(self, payload: ResumeCheckRequest) -> RetrievalConfig:
        retrieval_top_k = payload.retrieval_top_k or self.settings.retrieval_top_k
        candidate_pool_size = min(
            payload.candidate_pool_size or self.settings.candidate_pool_size,
            retrieval_top_k,
        )
        final_top_k = min(
            payload.final_top_k or self.settings.final_results_limit,
            candidate_pool_size,
        )
        return RetrievalConfig(
            retrieval_top_k=retrieval_top_k,
            candidate_pool_size=candidate_pool_size,
            final_top_k=final_top_k,
        )

    def _resolve_job_requirements(
        self,
        *,
        job_title: str | None,
        job_query_text: str,
    ) -> JobRequirements:
        required_years = requested_experience_years(job_query_text)
        job_title_keywords = role_keywords(job_title)
        description_role_keywords = role_keywords(job_query_text)
        combined_role_keywords = list(
            dict.fromkeys(
                job_title_keywords
                + description_role_keywords[: _ANALYSIS_RULES["description_role_keyword_limit"]]
            )
        )
        seniority_text = f"{job_title or ''} {job_query_text}".lower()
        is_senior_role = any(
            token in seniority_text
            for token in _ANALYSIS_RULES["senior_role_tokens"]
        ) or bool(required_years and required_years >= _ANALYSIS_RULES["senior_years_threshold"])
        return JobRequirements(
            required_skills=extract_required_skills(job_query_text),
            required_years=required_years,
            role_keywords=combined_role_keywords,
            is_senior_role=is_senior_role,
            role_profile=infer_role_profile(
                title=job_title,
                text=job_query_text,
                skills=extract_required_skills(job_query_text),
            ),
        )

    def _build_pinecone_metadata_filter(
        self,
        requirements: JobRequirements,
    ) -> dict[str, Any] | None:
        if requirements.required_years is None:
            return None
        minimum_years = max(
            requirements.required_years - self.settings.experience_filter_grace_years,
            0.0,
        )
        return {"experience_years": {"$gte": round(minimum_years, 2)}}

    def _filter_hits_by_metadata(
        self,
        *,
        search_hits: list[CandidateSearchHit],
        requirements: JobRequirements,
        fallback_pool_size: int,
    ) -> list[CandidateSearchHit]:
        if not search_hits:
            return []

        screened_hits: list[CandidateSearchHit] = []
        for hit in search_hits:
            hit.experience_penalty = self._experience_penalty(
                candidate_years=self._metadata_experience_years(hit.metadata),
                required_years=requirements.required_years,
            )
            hit.role_alignment_score = self._metadata_role_alignment_score(hit.metadata, requirements)
            if self._metadata_role_mismatch(hit.metadata, requirements) and len(search_hits) > fallback_pool_size:
                continue
            screened_hits.append(hit)

        return screened_hits if len(screened_hits) >= min(fallback_pool_size, len(search_hits)) else search_hits

    @staticmethod
    def _metadata_experience_years(metadata: dict[str, Any]) -> float:
        try:
            return float(metadata.get("experience_years") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _metadata_role_mismatch(
        self,
        metadata: dict[str, Any],
        requirements: JobRequirements,
    ) -> bool:
        current_role = str(metadata.get("current_role") or "").lower()
        if current_role and any(token in current_role for token in _ROLE_MISMATCH_TOKENS):
            return True
        return (
            self._metadata_role_alignment_score(metadata, requirements)
            < _RETRIEVAL_RULES["role_mismatch_threshold"]
        )

    def _metadata_role_alignment_score(
        self,
        metadata: dict[str, Any],
        requirements: JobRequirements,
    ) -> float:
        candidate_profile = infer_role_profile(
            title=str(metadata.get("current_role") or ""),
            text=" ".join(
                fragment
                for fragment in (
                    str(metadata.get("current_role") or ""),
                    " ".join(str(item) for item in (metadata.get("top_keywords") or [])),
                )
                if fragment
            ),
            skills=[str(skill) for skill in (metadata.get("skills") or [])],
        )
        return role_alignment_score(
            job_profile=requirements.role_profile,
            candidate_profile=candidate_profile,
        )

    def _experience_penalty(
        self,
        *,
        candidate_years: float,
        required_years: float | None,
    ) -> float:
        if required_years is None or required_years <= 0 or candidate_years >= required_years:
            return 0.0

        gap_ratio = min((required_years - candidate_years) / required_years, 1.0)
        penalty = self.settings.experience_penalty_min + (
            (self.settings.experience_penalty_max - self.settings.experience_penalty_min)
            * gap_ratio
        )
        return round(clamp01(penalty), 4)

    def _lexical_exact_match_score(
        self,
        *,
        structured_resume: StructuredResume,
        lexical_document: str,
        job_query_text: str,
        required_skills: list[str],
    ) -> float:
        skill_score, _, _ = keyword_scores(
            job_description=job_query_text,
            candidate_skills=resume_skill_inventory(structured_resume),
        )
        phrase_score = phrase_overlap_score(
            phrases=required_skills,
            text=lexical_document,
        )
        summary_overlap = self._summary_token_overlap(
            job_query_text,
            lexical_document,
        )
        return round(
            (
                skill_score * _EXACT_MATCH_WEIGHTS["skill"]
                + phrase_score * _EXACT_MATCH_WEIGHTS["phrase"]
                + summary_overlap * _EXACT_MATCH_WEIGHTS["summary"]
            ),
            4,
        )

    def _hybrid_retrieval_score(
        self,
        *,
        vector_score: float | None,
        lexical_score: float | None,
    ) -> float | None:
        available_scores = {
            "vector": vector_score,
            "lexical": lexical_score,
        }
        available = {name: value for name, value in available_scores.items() if value is not None}
        if not available:
            return None
        weight_map = {
            "vector": self.settings.hybrid_vector_weight,
            "lexical": self.settings.hybrid_lexical_weight,
        }
        normalized_weights = self._normalized_weights(
            weight_map,
            available_keys=available.keys(),
        )
        return round(
            sum(available[name] * normalized_weights[name] for name in available),
            4,
        )

    def _pre_rerank_score(self, hit: CandidateSearchHit) -> float:
        score = self._weighted_signal_score(
            signal_values={
                "retrieval": hit.retrieval_score,
                "graph": hit.graph_score,
            },
            weight_map={
                "retrieval": self.settings.final_weight_retrieval,
                "graph": self.settings.final_weight_graph,
            },
        )
        return round(
            score
            * (1 - hit.experience_penalty)
            * (1 - self._role_alignment_penalty(hit.role_alignment_score)),
            4,
        )

    def _final_score(
        self,
        *,
        hit: CandidateSearchHit,
        ats_score: float,
        ranking_weights: dict[str, float],
    ) -> float:
        combined = self._weighted_signal_score(
            signal_values={
                "retrieval": hit.retrieval_score,
                "graph": hit.graph_score,
                "reranker": hit.reranker_score,
                "ats": round(ats_score / 100, 4),
            },
            weight_map=ranking_weights,
        )
        adjusted = (
            combined
            * (1 - hit.experience_penalty)
            * (1 - self._role_alignment_penalty(hit.role_alignment_score))
        )
        return round(clamp01(adjusted) * 100, 2)

    @staticmethod
    def _role_alignment_penalty(role_alignment_score_value: float | None) -> float:
        threshold = _ROLE_ALIGNMENT_PENALTY_RULES["threshold"]
        if role_alignment_score_value is None or role_alignment_score_value >= threshold:
            return 0.0
        gap_ratio = min((threshold - role_alignment_score_value) / threshold, 1.0)
        return round(
            _ROLE_ALIGNMENT_PENALTY_RULES["base"]
            + (_ROLE_ALIGNMENT_PENALTY_RULES["max_additional"] * gap_ratio),
            4,
        )

    def _weighted_signal_score(
        self,
        *,
        signal_values: dict[str, float | None],
        weight_map: dict[str, float],
    ) -> float:
        available = {
            name: value
            for name, value in signal_values.items()
            if value is not None
        }
        if not available:
            return 0.0
        normalized_weights = self._normalized_weights(weight_map, available_keys=available.keys())
        return round(
            sum(available[name] * normalized_weights[name] for name in available),
            4,
        )

    @staticmethod
    def _normalized_weights(
        weight_map: dict[str, float],
        *,
        available_keys,
    ) -> dict[str, float]:
        available_weight_map = {
            key: max(weight_map.get(key, 0.0), 0.0)
            for key in available_keys
        }
        total = sum(available_weight_map.values())
        if total <= 0:
            fallback = 1 / max(len(available_weight_map), 1)
            return {key: round(fallback, 4) for key in available_weight_map}
        return {
            key: round(value / total, 4)
            for key, value in available_weight_map.items()
        }

    def _apply_diversity_selection(
        self,
        *,
        evaluations: list[CandidateEvaluation],
        final_top_k: int,
    ) -> list[CandidateEvaluation]:
        if len(evaluations) <= final_top_k:
            return evaluations

        remaining = list(evaluations)
        selected: list[CandidateEvaluation] = []
        while remaining and len(selected) < final_top_k:
            next_item = max(
                remaining,
                key=lambda item: self._diversified_score(item, selected),
            )
            selected.append(next_item)
            remaining.remove(next_item)
        return selected

    def _diversified_score(
        self,
        item: CandidateEvaluation,
        selected: list[CandidateEvaluation],
    ) -> float:
        base_score = item.report.final_score / 100
        if not selected:
            return base_score

        selected_skills = {
            skill
            for selected_item in selected
            for skill in self._primary_skills(selected_item)
        }
        item_skills = set(self._primary_skills(item))
        skill_novelty = (
            len(item_skills - selected_skills) / max(len(item_skills), 1)
            if item_skills
            else 0.0
        )
        item_band = experience_band(item.structured_resume.total_experience_years)
        selected_bands = {
            experience_band(selected_item.structured_resume.total_experience_years)
            for selected_item in selected
        }
        experience_novelty = 1.0 if item_band not in selected_bands else 0.0

        duplicate_similarity = max(
            self._duplicate_similarity(item, selected_item)
            for selected_item in selected
        )
        duplicate_penalty = 0.0
        if duplicate_similarity >= self.settings.diversity_duplicate_threshold:
            duplicate_penalty = (
                (duplicate_similarity - self.settings.diversity_duplicate_threshold)
                / max(1 - self.settings.diversity_duplicate_threshold, 1e-9)
            )

        return round(
            base_score
            + (self.settings.diversity_skill_weight * skill_novelty)
            + (self.settings.diversity_experience_weight * experience_novelty)
            - (self.settings.diversity_dedup_penalty_weight * duplicate_penalty),
            4,
        )

    def _duplicate_similarity(
        self,
        left: CandidateEvaluation,
        right: CandidateEvaluation,
    ) -> float:
        skill_similarity = jaccard_similarity(
            self._primary_skills(left),
            self._primary_skills(right),
        )
        summary_similarity = jaccard_similarity(
            tokenize_for_retrieval(left.report.summary),
            tokenize_for_retrieval(right.report.summary),
        )
        title_similarity = (
            1.0
            if (left.report.current_title or "").lower() == (right.report.current_title or "").lower()
            else 0.0
        )
        experience_gap = abs(
            left.structured_resume.total_experience_years - right.structured_resume.total_experience_years
        )
        experience_similarity = 1.0 if experience_gap <= 1 else 0.5 if experience_gap <= 2 else 0.0
        return round(
            max(
                skill_similarity,
                summary_similarity,
                (title_similarity * 0.6) + (experience_similarity * 0.4),
            ),
            4,
        )

    def _primary_skills(self, item: CandidateEvaluation) -> list[str]:
        return (
            item.report.matched_keywords
            or resume_skill_inventory(item.structured_resume)[: _ANALYSIS_LIMITS["primary_skill_fallback"]]
        )

    def _build_reasons(
        self,
        *,
        structured_resume: StructuredResume,
        hit: CandidateSearchHit,
        job_description: str,
        matched_keywords: list[str],
        semantic_similarity: float,
        experience_score: float,
        heuristic_quality: float,
        formatting_score: float,
    ) -> list[str]:
        reasons: list[str] = []
        if matched_keywords:
            reasons.append(
                "Strong skill match for "
                + ", ".join(matched_keywords[: _ANALYSIS_LIMITS["reason_skills"]])
                + "."
            )
        if hit.graph_matched_skills:
            reasons.append(
                "Graph relationships reinforce adjacency to "
                + ", ".join(hit.graph_matched_skills[: _ANALYSIS_LIMITS["reason_graph_skills"]])
                + "."
            )
        if (
            hit.role_alignment_score is not None
            and hit.role_alignment_score >= _ANALYSIS_REASON_THRESHOLDS["role_alignment"]
        ):
            reasons.append("Role alignment is strong for the requested responsibilities.")
        if hit.reranker_score is not None and hit.reranker_score >= _ANALYSIS_REASON_THRESHOLDS["reranker"]:
            reasons.append("Reranker scored this resume highly against the job description.")
        elif hit.retrieval_score is not None and hit.retrieval_score >= _ANALYSIS_REASON_THRESHOLDS["retrieval"]:
            reasons.append("Retrieval signals show strong semantic and exact-match relevance.")
        elif hit.lexical_score is not None and hit.lexical_score >= _ANALYSIS_REASON_THRESHOLDS["lexical"]:
            reasons.append("Exact keyword overlap is strong across the title, skills, or project text.")
        if semantic_similarity >= _ANALYSIS_REASON_THRESHOLDS["semantic"]:
            reasons.append("Resume summary is semantically close to the job description.")
        requested_years = requested_experience_years(job_description)
        if requested_years is not None and experience_score >= _ANALYSIS_REASON_THRESHOLDS["experience"]:
            reasons.append(
                f"Experience level aligns well with the requested {requested_years:g}+ years."
            )
        project_reason = self._project_reason(structured_resume, matched_keywords)
        if project_reason:
            reasons.append(project_reason)
        if (
            heuristic_quality >= _ANALYSIS_REASON_THRESHOLDS["quality"]
            and formatting_score >= _ANALYSIS_REASON_THRESHOLDS["formatting"]
        ):
            reasons.append("Resume structure looks ATS-friendly with strong formatting and section coverage.")
        if structured_resume.parsing_quality_score < _ANALYSIS_REASON_THRESHOLDS["parsing_quality"]:
            reasons.append("Parsing quality is moderate, so extracted details should be reviewed manually.")
        return self._deduplicate(reasons)[: _ANALYSIS_LIMITS["max_reasons"]]

    @staticmethod
    def _job_query_text(*, job_title: str | None, job_description: str) -> str:
        if job_title and job_title.strip():
            return f"{job_title.strip()}. {job_description.strip()}"
        return job_description.strip()

    @staticmethod
    def _build_reranker_document(candidate: Candidate) -> str:
        structured = StructuredResume.model_validate(candidate.structured_resume)
        experience_fragments = [
            f"{item.title} at {item.company or 'Unknown'} {item.summary or ''}".strip()
            for item in structured.experience[: _ANALYSIS_LIMITS["reranker_experiences"]]
        ]
        project_fragments = [
            " ".join(
                fragment
                for fragment in (
                    project.name,
                    project.summary or "",
                    ", ".join(project.technologies[: _ANALYSIS_LIMITS["reranker_project_technologies"]])
                    if project.technologies
                    else "",
                )
                if fragment
            ).strip()
            for project in structured.projects[: _ANALYSIS_LIMITS["reranker_projects"]]
        ]
        fragments = [
            f"Candidate: {candidate.full_name}",
            f"Current title: {structured.current_title or candidate.current_title or 'Unknown'}",
            f"Total experience years: {structured.total_experience_years}",
            f"Skills: {', '.join(structured.skills)}",
            f"Summary: {structured.summary or candidate.summary}",
        ]
        if any(experience_fragments):
            fragments.append("Experience: " + " ; ".join(experience_fragments))
        if any(project_fragments):
            fragments.append("Projects: " + " ; ".join(project_fragments))
        return "\n".join(fragment for fragment in fragments if fragment.strip())

    @staticmethod
    def _project_reason(
        structured_resume: StructuredResume,
        matched_keywords: list[str],
    ) -> str | None:
        if not structured_resume.projects:
            return None
        lowered_matches = {skill.lower() for skill in matched_keywords}
        for project in structured_resume.projects:
            technologies = [tech for tech in project.technologies if tech]
            if lowered_matches and any(tech.lower() in lowered_matches for tech in technologies):
                return (
                    f"Relevant project evidence includes {project.name} using "
                    + ", ".join(technologies[: _ANALYSIS_LIMITS["reason_project_technologies"]])
                    + "."
                )
        first_project = structured_resume.projects[0]
        if first_project.technologies:
            return (
                f"Relevant project evidence includes {first_project.name} using "
                + ", ".join(first_project.technologies[: _ANALYSIS_LIMITS["reason_project_technologies"]])
                + "."
            )
        return f"Relevant project experience includes {first_project.name}."

    @staticmethod
    def _summary_token_overlap(job_description: str, summary: str) -> float:
        job_tokens = {
            token
            for token in tokenize_for_retrieval(job_description)
            if token not in _SUMMARY_OVERLAP_STOPWORDS
        }
        summary_tokens = set(tokenize_for_retrieval(summary))
        if not job_tokens or not summary_tokens:
            return 0.0
        return round(len(job_tokens & summary_tokens) / len(job_tokens), 4)

    @staticmethod
    def _source_filter(value: str) -> CandidateSource | None:
        if value == "internal":
            return CandidateSource.internal
        if value == "external":
            return CandidateSource.external
        return None

    def _relative_path(self, file_path: Path) -> str:
        try:
            return str(file_path.resolve().relative_to(self.settings.resume_source_dir.resolve()))
        except ValueError:
            return str(file_path)

    def _semantic_similarity(self, job_description: str, resume_summary: str) -> float:
        query_embedding = self.embedding_model.embed_queries([job_description])[0]
        summary_embedding = self.embedding_model.embed_passages([resume_summary])[0]
        return round(
            clamp01(sum(left * right for left, right in zip(query_embedding, summary_embedding))),
            4,
        )

    @staticmethod
    def _deduplicate(items: list[str]) -> list[str]:
        deduplicated: list[str] = []
        seen: set[str] = set()
        for item in items:
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduplicated.append(normalized)
        return deduplicated

    @staticmethod
    def _matches_threshold(score: float, minimum_ats_score: float | None) -> bool:
        if minimum_ats_score is None:
            return True
        return score >= minimum_ats_score

    @staticmethod
    def _resolved_job_title(payload: ResumeCheckRequest) -> str | None:
        if payload.job_title:
            return payload.job_title.strip()

        first_line = next(
            (line.strip() for line in payload.job_description.splitlines() if line.strip()),
            "",
        )
        if not first_line:
            return None
        return first_line[:120]

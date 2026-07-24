from __future__ import annotations

from pathlib import Path

from conftest import build_candidate
from docx import Document

from app.core.config import Settings
from app.graph.neo4j_client import GraphCandidateScore
from app.models.enums import CandidateSource
from app.schemas.resume_analysis import ResumeCheckRequest
from app.services.feedback_service import RankingWeightSnapshot
from app.services.resume_analysis_service import CandidateSearchHit, ResumeAnalysisService
from app.utils.candidate_profile import (
    build_graph_payload,
    build_pinecone_metadata,
    infer_role_profile,
    role_alignment_score,
)
from app.vectorstore.pinecone_client import RetrievedCandidateMatch


class StubCandidateRepository:
    def __init__(self, candidates):
        self._candidates = candidates

    async def list_for_ats(self, *, source=None):
        if source is None:
            return list(self._candidates)
        return [candidate for candidate in self._candidates if candidate.source == source]

    async def list_by_ids(self, candidate_ids):
        candidates = {candidate.id: candidate for candidate in self._candidates}
        return [candidates[candidate_id] for candidate_id in candidate_ids if candidate_id in candidates]


class StubReportRunRepository:
    def __init__(self):
        self.runs = {}
        self.commits = 0

    async def get_by_id(self, report_run_id):
        return self.runs.get(report_run_id)

    async def save(self, report_run):
        self.runs[report_run.id] = report_run
        return report_run

    async def commit(self):
        self.commits += 1


class StubReportRepository:
    def __init__(self):
        self.reports = {}

    async def get_by_run_and_candidate(self, report_run_id, candidate_id):
        return self.reports.get((report_run_id, candidate_id))

    async def list_by_run_id(self, report_run_id):
        reports = [
            report
            for (run_id, _), report in self.reports.items()
            if run_id == report_run_id
        ]
        return sorted(reports, key=lambda report: report.rank)

    async def save(self, report):
        self.reports[(report.report_run_id, report.candidate_id)] = report
        return report


class StubEmbeddingModel:
    def embed_queries(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_passages(self, texts):
        scores = []
        for text in texts:
            if "Python" in text or "FastAPI" in text:
                scores.append([0.9, 0.1])
            else:
                scores.append([0.4, 0.6])
        return scores


class StubVectorStore:
    def __init__(self, matches=None, *, failure: Exception | None = None):
        self.matches = matches or []
        self.failure = failure
        self.calls = []
        self.settings = type(
            "VectorSettings",
            (),
            {
                "pinecone_connect_timeout_seconds": 1,
                "pinecone_read_timeout_seconds": 1,
            },
        )()

    async def query_candidates(self, *, query_embedding, top_k, source=None, metadata_filter=None):
        self.calls.append(
            {
                "query_embedding": query_embedding,
                "top_k": top_k,
                "source": source,
                "metadata_filter": metadata_filter,
            }
        )
        if self.failure is not None:
            raise self.failure
        return list(self.matches)


class StubGraphStore:
    def __init__(self, scores=None):
        self.scores = scores or {}
        self.calls = []

    async def score_candidates(self, *, candidate_ids, required_skills, required_years=None):
        self.calls.append(
            {
                "candidate_ids": list(candidate_ids),
                "required_skills": list(required_skills),
                "required_years": required_years,
            }
        )
        return dict(self.scores)


class StubRerankerModel:
    def __init__(self, scores=None, *, scorer=None):
        self.scores = scores or {}
        self.scorer = scorer
        self.calls = []

    def score(self, query, documents):
        self.calls.append({"query": query, "documents": list(documents)})
        if self.scorer is not None:
            return [self.scorer(query, document) for document in documents]
        return [self.scores[document] for document in documents]


class StubFeedbackService:
    def __init__(self, weights=None, feedback_events_analyzed=0):
        self.weights = weights or {
            "retrieval": 0.30,
            "graph": 0.15,
            "reranker": 0.35,
            "ats": 0.20,
        }
        self.feedback_events_analyzed = feedback_events_analyzed

    async def get_weight_snapshot(self):
        return RankingWeightSnapshot(
            weights=dict(self.weights),
            feedback_events_analyzed=self.feedback_events_analyzed,
            learned_from_feedback=self.feedback_events_analyzed > 0,
        )


async def test_check_resumes_uses_hybrid_graph_and_bge_reranking(tmp_path: Path) -> None:
    internal_dir = tmp_path / "internal"
    internal_dir.mkdir(parents=True)

    strong_resume_path = internal_dir / "candidate_strong.docx"
    strong_document = Document()
    strong_document.add_paragraph("John Doe")
    strong_document.add_paragraph("Backend Developer")
    strong_document.add_paragraph("Built FastAPI services and improved delivery by 30 percent.")
    strong_document.save(strong_resume_path)

    weak_resume_path = internal_dir / "candidate_weak.docx"
    weak_document = Document()
    weak_document.add_paragraph("Jane Smith")
    weak_document.add_paragraph("Operations Executive")
    weak_document.add_paragraph("Handled reporting and stakeholder communication.")
    weak_document.save(weak_resume_path)

    strong_candidate = build_candidate(
        candidate_id="cand_report",
        name="John Doe",
        source=CandidateSource.internal,
        summary="Backend developer with Python, FastAPI, Docker, and Neo4j experience.",
        raw_text="John Doe Backend Developer Improved delivery by 30 percent using Python FastAPI and Neo4j.",
        skills=["python", "fastapi", "docker", "neo4j"],
        experience_years=5,
        file_path=str(strong_resume_path),
    )
    strong_candidate.structured_resume = {
        "name": "John Doe",
        "email": "john@example.com",
        "phone": None,
        "location": "Remote",
        "current_title": "Backend Developer",
        "skills": ["python", "fastapi", "docker", "neo4j"],
        "experience": [],
        "education": [],
        "projects": [{"name": "ATS Parser", "summary": "Parser", "technologies": ["python"]}],
        "total_experience_years": 5,
        "links": {},
        "availability": "Immediate",
        "source": "internal",
        "summary": strong_candidate.summary,
    }

    weak_candidate = build_candidate(
        candidate_id="cand_other",
        name="Jane Smith",
        source=CandidateSource.internal,
        summary="Operations profile with stakeholder reporting and coordination experience.",
        raw_text="Jane Smith operations reporting stakeholder communication.",
        skills=["excel", "communication"],
        experience_years=3,
        file_path=str(weak_resume_path),
    )
    weak_candidate.structured_resume = {
        "name": "Jane Smith",
        "email": "jane@example.com",
        "phone": None,
        "location": "Remote",
        "current_title": "Operations Executive",
        "skills": ["excel", "communication"],
        "experience": [],
        "education": [],
        "projects": [],
        "total_experience_years": 3,
        "links": {},
        "availability": "Immediate",
        "source": "internal",
        "summary": weak_candidate.summary,
    }

    report_run_repository = StubReportRunRepository()
    report_repository = StubReportRepository()
    vector_store = StubVectorStore(
        [
            RetrievedCandidateMatch(
                candidate_id="cand_other",
                score=0.96,
                metadata={
                    "candidate_id": "cand_other",
                    "skills": ["excel", "communication"],
                    "summary": weak_candidate.summary,
                },
            ),
            RetrievedCandidateMatch(
                candidate_id="cand_report",
                score=0.91,
                metadata={
                    "candidate_id": "cand_report",
                    "skills": ["python", "fastapi", "docker", "neo4j"],
                    "summary": strong_candidate.summary,
                },
            ),
        ]
    )
    graph_store = StubGraphStore(
        {
            "cand_report": GraphCandidateScore(
                candidate_id="cand_report",
                score=1.0,
                matched_skills=["fastapi", "neo4j", "python"],
            ),
            "cand_other": GraphCandidateScore(
                candidate_id="cand_other",
                score=0.0,
                matched_skills=[],
            ),
        }
    )
    reranker = StubRerankerModel(
        scorer=lambda query, document: 0.99 if "Backend Developer" in document else 0.08
    )
    settings = Settings(
        _env_file=None,
        resume_source_dir=tmp_path,
        retrieval_top_k=5,
        candidate_pool_size=2,
        final_results_limit=1,
    )
    service = ResumeAnalysisService(
        settings=settings,
        candidate_repository=StubCandidateRepository([strong_candidate, weak_candidate]),
        report_run_repository=report_run_repository,
        report_repository=report_repository,
        feedback_service=StubFeedbackService(),
        embedding_model=StubEmbeddingModel(),
        reranker_model=reranker,
        vector_store=vector_store,
        graph_store=graph_store,
    )

    response = await service.check_resumes(
        ResumeCheckRequest(
            job_id="jd_backend_001",
            job_title="Senior Backend Engineer",
            job_description="Need Python, FastAPI, Neo4j, and 4 years of backend experience.",
            source="internal",
            minimum_ats_score=50,
            retrieval_top_k=4,
            candidate_pool_size=2,
            final_top_k=1,
        )
    )

    assert response.job_id == "jd_backend_001"
    assert response.job_title == "Senior Backend Engineer"
    assert response.total_candidates == 2
    assert response.matched_candidates == 1
    assert response.returned_candidates == 1
    assert response.ranking_weights["retrieval"] == 0.30
    assert response.results[0].candidate_id == "cand_report"
    assert response.results[0].candidate_name == "John Doe"
    assert response.results[0].rank == 1
    assert response.results[0].final_score > 0
    assert response.results[0].graph_score == 1.0
    assert response.results[0].reranker_score == 0.99
    assert response.results[0].reasons
    assert "python" in response.results[0].matched_keywords
    assert reranker.calls[0]["query"].startswith("Senior Backend Engineer.")
    assert any(
        "Current title: Backend Developer" in document
        for document in reranker.calls[0]["documents"]
    )
    assert vector_store.calls[0]["top_k"] == 4
    assert vector_store.calls[0]["source"] == "internal"
    assert graph_store.calls[0]["candidate_ids"] == ["cand_report", "cand_other"]

    run_response = await service.get_check_run(response.report_run_id)
    assert run_response.report_run_id == response.report_run_id
    assert run_response.results[0].candidate_id == "cand_report"
    assert run_response.results[0].final_score > 0
    assert run_response.results[0].retrieval_score is not None
    assert run_response.results[0].graph_score == 1.0
    assert run_response.results[0].reranker_score == 0.99

    report_response = await service.get_report(response.report_run_id, "cand_report")
    assert report_response.report_run_id == response.report_run_id
    assert report_response.job_description.startswith("Need Python")
    assert report_response.relative_path == "internal\\candidate_strong.docx"
    assert report_response.final_score > 0
    assert report_response.retrieval_score is not None
    assert report_response.graph_score == 1.0
    assert report_response.reranker_score == 0.99
    assert report_response.reasons


async def test_check_resumes_still_returns_matches_when_vector_lookup_fails(
    tmp_path: Path,
) -> None:
    internal_dir = tmp_path / "internal"
    internal_dir.mkdir(parents=True)

    strong_resume_path = internal_dir / "candidate_strong.docx"
    strong_document = Document()
    strong_document.add_paragraph("John Doe")
    strong_document.add_paragraph("Backend Developer")
    strong_document.save(strong_resume_path)

    weak_resume_path = internal_dir / "candidate_weak.docx"
    weak_document = Document()
    weak_document.add_paragraph("Jane Smith")
    weak_document.add_paragraph("Operations Executive")
    weak_document.save(weak_resume_path)

    strong_candidate = build_candidate(
        candidate_id="cand_report",
        name="John Doe",
        source=CandidateSource.internal,
        summary="Backend developer with Python, FastAPI, Docker, and Neo4j experience.",
        raw_text="John Doe Backend Developer Improved delivery by 30 percent using Python FastAPI and Neo4j.",
        skills=["python", "fastapi", "docker", "neo4j"],
        experience_years=5,
        file_path=str(strong_resume_path),
    )
    strong_candidate.structured_resume = {
        "name": "John Doe",
        "email": "john@example.com",
        "phone": None,
        "location": "Remote",
        "current_title": "Backend Developer",
        "skills": ["python", "fastapi", "docker", "neo4j"],
        "experience": [],
        "education": [],
        "projects": [],
        "total_experience_years": 5,
        "links": {},
        "availability": "Immediate",
        "source": "internal",
        "summary": strong_candidate.summary,
    }

    weak_candidate = build_candidate(
        candidate_id="cand_other",
        name="Jane Smith",
        source=CandidateSource.internal,
        summary="Operations profile with stakeholder reporting and coordination experience.",
        raw_text="Jane Smith operations reporting stakeholder communication.",
        skills=["excel", "communication"],
        experience_years=3,
        file_path=str(weak_resume_path),
    )
    weak_candidate.structured_resume = {
        "name": "Jane Smith",
        "email": "jane@example.com",
        "phone": None,
        "location": "Remote",
        "current_title": "Operations Executive",
        "skills": ["excel", "communication"],
        "experience": [],
        "education": [],
        "projects": [],
        "total_experience_years": 3,
        "links": {},
        "availability": "Immediate",
        "source": "internal",
        "summary": weak_candidate.summary,
    }

    service = ResumeAnalysisService(
        settings=Settings(_env_file=None, resume_source_dir=tmp_path),
        candidate_repository=StubCandidateRepository([strong_candidate, weak_candidate]),
        report_run_repository=StubReportRunRepository(),
        report_repository=StubReportRepository(),
        feedback_service=StubFeedbackService(),
        embedding_model=StubEmbeddingModel(),
        reranker_model=None,
        vector_store=StubVectorStore(failure=RuntimeError("pinecone down")),
        graph_store=StubGraphStore(),
    )

    response = await service.check_resumes(
        ResumeCheckRequest(
            job_description="Need Python, FastAPI, Neo4j, and 4 years of backend experience.",
            source="internal",
            minimum_ats_score=50,
        )
    )

    assert response.total_candidates == 2
    assert response.matched_candidates == 1
    assert response.returned_candidates == 1
    assert response.results[0].candidate_id == "cand_report"


async def test_senior_ml_role_prefers_ml_candidate_when_reranker_and_experience_align(
    tmp_path: Path,
    monkeypatch,
) -> None:
    external_dir = tmp_path / "external"
    external_dir.mkdir(parents=True)

    backend_resume_path = external_dir / "backend.docx"
    backend_document = Document()
    backend_document.add_paragraph("Arun Kumar R")
    backend_document.add_paragraph("Backend Developer")
    backend_document.add_paragraph("Built FastAPI services and improved delivery by 30 percent.")
    backend_document.save(backend_resume_path)

    ml_resume_path = external_dir / "ml.docx"
    ml_document = Document()
    ml_document.add_paragraph("Sathish Kumar V")
    ml_document.add_paragraph("Machine Learning Engineer")
    ml_document.add_paragraph("Built NLP pipelines and recommendation systems.")
    ml_document.save(ml_resume_path)

    backend_candidate = build_candidate(
        candidate_id="cand_backend",
        name="Arun Kumar R",
        source=CandidateSource.external,
        summary="Candidate Arun Kumar R. Current title Backend Developer. Experience 0.0 years.",
        raw_text="Backend Developer with FastAPI PostgreSQL REST API experience.",
        skills=["fastapi", "postgresql", "python", "rest", "sql"],
        experience_years=0.0,
        file_path=str(backend_resume_path),
    )
    backend_candidate.structured_resume = {
        "name": "Arun Kumar R",
        "email": "arun@example.com",
        "phone": None,
        "location": "Tamil Nadu, India",
        "current_title": "Backend Developer",
        "skills": ["fastapi", "postgresql", "python", "rest", "sql"],
        "experience": [],
        "education": [],
        "projects": [
            {"name": "Task Management API", "summary": "REST API backend", "technologies": ["fastapi", "postgresql", "rest"]}
        ],
        "total_experience_years": 0.0,
        "links": {},
        "availability": "Immediate",
        "source": "external",
        "summary": "Candidate Arun Kumar R. Current title Backend Developer. Experience 0.0 years. Skills fastapi, postgresql, python, rest, sql.",
    }

    ml_candidate = build_candidate(
        candidate_id="cand_ml",
        name="Sathish Kumar V",
        source=CandidateSource.external,
        summary="Candidate Sathish Kumar V. Current title Machine Learning Engineer. Experience 4.0 years.",
        raw_text="Machine Learning Engineer with NLP, FastAPI, and recommendation system experience.",
        skills=["fastapi", "machine learning", "nlp", "python", "sql"],
        experience_years=4.0,
        file_path=str(ml_resume_path),
    )
    ml_candidate.structured_resume = {
        "name": "Sathish Kumar V",
        "email": "sathish@example.com",
        "phone": None,
        "location": "Tamil Nadu, India",
        "current_title": "Machine Learning Engineer",
        "skills": ["fastapi", "machine learning", "nlp", "python", "sql"],
        "experience": [],
        "education": [],
        "projects": [
            {
                "name": "Recommendation System",
                "summary": "Built NLP-powered recommendation APIs",
                "technologies": ["fastapi", "machine learning", "nlp"],
            }
        ],
        "total_experience_years": 4.0,
        "links": {},
        "availability": "Immediate",
        "source": "external",
        "summary": "Candidate Sathish Kumar V. Current title Machine Learning Engineer. Experience 4.0 years. Skills fastapi, machine learning, nlp, python, sql.",
    }

    vector_store = StubVectorStore(
        [
            RetrievedCandidateMatch(candidate_id="cand_backend", score=0.8374, metadata={}),
            RetrievedCandidateMatch(candidate_id="cand_ml", score=0.8209, metadata={}),
        ]
    )
    graph_store = StubGraphStore(
        {
            "cand_backend": GraphCandidateScore(
                candidate_id="cand_backend",
                score=0.5,
                matched_skills=["fastapi", "postgresql", "python"],
            ),
            "cand_ml": GraphCandidateScore(
                candidate_id="cand_ml",
                score=0.5,
                matched_skills=["fastapi", "machine learning", "nlp", "python"],
            ),
        }
    )
    reranker = StubRerankerModel(
        scorer=lambda query, document: 0.16 if "Machine Learning Engineer" in document else 0.07
    )
    service = ResumeAnalysisService(
        settings=Settings(
            _env_file=None,
            resume_source_dir=tmp_path,
            retrieval_top_k=5,
            candidate_pool_size=2,
            final_results_limit=2,
        ),
        candidate_repository=StubCandidateRepository([backend_candidate, ml_candidate]),
        report_run_repository=StubReportRunRepository(),
        report_repository=StubReportRepository(),
        feedback_service=StubFeedbackService(),
        embedding_model=StubEmbeddingModel(),
        reranker_model=reranker,
        vector_store=vector_store,
        graph_store=graph_store,
    )

    async def fake_lexical_retrieval_hits(**kwargs):
        return {
            "cand_backend": CandidateSearchHit(candidate_id="cand_backend", lexical_score=0.8374),
            "cand_ml": CandidateSearchHit(candidate_id="cand_ml", lexical_score=0.8209),
        }

    monkeypatch.setattr(service, "_lexical_retrieval_hits", fake_lexical_retrieval_hits)

    response = await service.check_resumes(
        ResumeCheckRequest(
            job_id="jd_ml_2026_01",
            job_title="Senior ML Engineer",
            job_description=(
                "We are hiring a Senior ML Engineer to work on an ATS parser and checker service "
                "using FastAPI, PostgreSQL, Pinecone, and Neo4j. The engineer should have strong "
                "Python experience, machine learning fundamentals, NLP or RAG exposure, REST API "
                "design, clean backend design, and measurable project outcomes."
            ),
            source="external",
            minimum_ats_score=0,
            retrieval_top_k=5,
            candidate_pool_size=2,
            final_top_k=2,
        )
    )

    assert response.results[0].candidate_id == "cand_ml"
    assert response.results[0].candidate_name == "Sathish Kumar V"
    assert response.results[0].experience_relevance_score > response.results[1].experience_relevance_score
    assert response.results[0].reranker_score > response.results[1].reranker_score
    assert response.results[0].final_score > response.results[1].final_score


def test_candidate_profile_metadata_and_graph_payload_include_project_only_infra_skills() -> None:
    structured_resume = {
        "name": "Infra Candidate",
        "email": "infra@example.com",
        "phone": None,
        "location": "Remote",
        "current_title": "ML Engineer",
        "skills": ["python", "fastapi"],
        "experience": [
            {
                "title": "ML Engineer",
                "company": "Example",
                "start_date": "2022",
                "end_date": "Present",
                "summary": "Built APIs backed by Neo4j for recommendation search.",
            }
        ],
        "education": [],
        "projects": [
            {
                "name": "ATS Parser Checker",
                "summary": "Implemented retrieval using Pinecone and PostgreSQL storage.",
                "technologies": ["rag"],
            }
        ],
        "total_experience_years": 4.0,
        "links": {},
        "availability": "Immediate",
        "source": "external",
        "summary": "FastAPI engineer building ML platforms.",
    }

    from app.schemas.ingestion import StructuredResume

    resume = StructuredResume.model_validate(structured_resume)
    metadata = build_pinecone_metadata(
        candidate_id="cand_infra",
        source="external",
        structured_resume=resume,
    )
    graph_payload = build_graph_payload(
        candidate_id="cand_infra",
        full_name="Infra Candidate",
        source="external",
        structured_resume=resume,
    )

    assert {"python", "fastapi", "neo4j", "pinecone", "postgresql", "rag"}.issubset(
        set(metadata["skills"])
    )
    assert {"python", "fastapi", "neo4j", "pinecone", "postgresql", "rag"}.issubset(
        set(graph_payload["skills"])
    )
    assert {"pinecone", "postgresql", "rag"}.issubset(set(graph_payload["projects"][0]["skills"]))


async def test_check_resumes_matches_infra_keywords_from_project_and_experience_evidence(
    tmp_path: Path,
) -> None:
    external_dir = tmp_path / "external"
    external_dir.mkdir(parents=True)

    resume_path = external_dir / "infra_candidate.docx"
    document = Document()
    document.add_paragraph("Infra Candidate")
    document.add_paragraph("ML Engineer")
    document.add_paragraph("Built ATS services with Pinecone, Neo4j, and PostgreSQL.")
    document.save(resume_path)

    candidate = build_candidate(
        candidate_id="cand_infra",
        name="Infra Candidate",
        source=CandidateSource.external,
        summary="ML engineer with FastAPI and Python experience.",
        raw_text="Built ATS services with Pinecone, Neo4j, PostgreSQL, and measurable delivery outcomes.",
        skills=["python", "fastapi", "machine learning"],
        experience_years=4.0,
        file_path=str(resume_path),
    )
    candidate.structured_resume = {
        "name": "Infra Candidate",
        "email": "infra@example.com",
        "phone": None,
        "location": "Remote",
        "current_title": "ML Engineer",
        "skills": ["python", "fastapi", "machine learning"],
        "experience": [
            {
                "title": "ML Engineer",
                "company": "Example",
                "start_date": "2022",
                "end_date": "Present",
                "summary": "Built ATS services with Neo4j-backed graph search and REST APIs.",
            }
        ],
        "education": [],
        "projects": [
            {
                "name": "ATS Parser Checker",
                "summary": "Implemented retrieval using Pinecone and PostgreSQL for search quality.",
                "technologies": ["rag", "nlp"],
            }
        ],
        "total_experience_years": 4.0,
        "links": {},
        "availability": "Immediate",
        "source": "external",
        "summary": "ML engineer with FastAPI and Python experience.",
    }

    service = ResumeAnalysisService(
        settings=Settings(
            _env_file=None,
            resume_source_dir=tmp_path,
            retrieval_top_k=5,
            candidate_pool_size=1,
            final_results_limit=1,
        ),
        candidate_repository=StubCandidateRepository([candidate]),
        report_run_repository=StubReportRunRepository(),
        report_repository=StubReportRepository(),
        feedback_service=StubFeedbackService(),
        embedding_model=StubEmbeddingModel(),
        reranker_model=None,
        vector_store=StubVectorStore(
            [
                RetrievedCandidateMatch(
                    candidate_id="cand_infra",
                    score=0.92,
                    metadata={
                        "candidate_id": "cand_infra",
                        "experience_years": 4.0,
                        "current_role": "ML Engineer",
                    },
                )
            ]
        ),
        graph_store=StubGraphStore(
            {
                "cand_infra": GraphCandidateScore(
                    candidate_id="cand_infra",
                    score=0.85,
                    matched_skills=["fastapi", "neo4j", "pinecone", "postgresql", "python"],
                )
            }
        ),
    )

    response = await service.check_resumes(
        ResumeCheckRequest(
            job_id="jd_ml_2026_01",
            job_title="Senior ML Engineer",
            job_description=(
                "We are hiring a Senior ML Engineer to work on an ATS parser and checker service "
                "using FastAPI, PostgreSQL, Pinecone, and Neo4j. The engineer should have strong "
                "Python experience, machine learning fundamentals, NLP or RAG exposure, REST API design, "
                "clean backend design, and measurable project outcomes."
            ),
            source="external",
            minimum_ats_score=0,
            retrieval_top_k=5,
            candidate_pool_size=1,
            final_top_k=1,
        )
    )

    result = response.results[0]
    assert {"fastapi", "postgresql", "pinecone", "neo4j", "python", "rag"}.issubset(
        set(result.matched_keywords)
    )
    assert "sql" not in result.matched_keywords


def test_role_alignment_distinguishes_ml_ai_and_backend() -> None:
    job_profile = infer_role_profile(
        title="Senior ML Engineer",
        text="Need machine learning, NLP, RAG, and backend design for ATS services.",
        skills=["machine learning", "nlp", "rag", "fastapi", "python"],
    )
    ml_profile = infer_role_profile(
        title="Machine Learning Engineer",
        text="Built recommendation systems and NLP pipelines.",
        skills=["machine learning", "nlp", "python"],
    )
    ai_profile = infer_role_profile(
        title="AI Engineer",
        text="Built LLM and RAG applications.",
        skills=["llm", "rag", "python"],
    )
    backend_profile = infer_role_profile(
        title="Backend Engineer",
        text="Built REST APIs and PostgreSQL services.",
        skills=["fastapi", "postgresql", "rest"],
    )

    ml_score = role_alignment_score(job_profile=job_profile, candidate_profile=ml_profile)
    ai_score = role_alignment_score(job_profile=job_profile, candidate_profile=ai_profile)
    backend_score = role_alignment_score(job_profile=job_profile, candidate_profile=backend_profile)

    assert ml_score > ai_score > backend_score
    assert ml_score >= 0.9
    assert backend_score <= 0.2


async def test_backend_role_penalizes_ml_profiles_even_with_shared_python_fastapi_skills(
    tmp_path: Path,
) -> None:
    internal_dir = tmp_path / "internal"
    internal_dir.mkdir(parents=True)

    backend_resume_path = internal_dir / "backend.docx"
    backend_document = Document()
    backend_document.add_paragraph("Vikram Rao")
    backend_document.add_paragraph("Backend Engineer")
    backend_document.add_paragraph("Built FastAPI and PostgreSQL APIs.")
    backend_document.save(backend_resume_path)

    ml_resume_path = internal_dir / "ml.docx"
    ml_document = Document()
    ml_document.add_paragraph("Sathish Kumar V")
    ml_document.add_paragraph("Machine Learning Engineer")
    ml_document.add_paragraph("Built ML services with FastAPI.")
    ml_document.save(ml_resume_path)

    backend_candidate = build_candidate(
        candidate_id="cand_backend_role",
        name="Vikram Rao",
        source=CandidateSource.internal,
        summary="Backend engineer building FastAPI and PostgreSQL services.",
        raw_text="Built REST APIs with FastAPI and PostgreSQL for backend systems.",
        skills=["python", "fastapi", "postgresql", "rest"],
        experience_years=4.0,
        file_path=str(backend_resume_path),
    )
    backend_candidate.structured_resume = {
        "name": "Vikram Rao",
        "email": "vikram@example.com",
        "phone": None,
        "location": "Remote",
        "current_title": "Backend Engineer",
        "skills": ["python", "fastapi", "postgresql", "rest"],
        "experience": [],
        "education": [],
        "projects": [{"name": "Billing API", "summary": "REST backend", "technologies": ["fastapi", "postgresql", "rest"]}],
        "total_experience_years": 4.0,
        "links": {},
        "availability": "Immediate",
        "source": "internal",
        "summary": backend_candidate.summary,
    }

    ml_candidate = build_candidate(
        candidate_id="cand_ml_role",
        name="Sathish Kumar V",
        source=CandidateSource.internal,
        summary="Machine learning engineer with Python and FastAPI experience.",
        raw_text="Built NLP pipelines and model-serving APIs with FastAPI.",
        skills=["python", "fastapi", "machine learning", "nlp"],
        experience_years=4.0,
        file_path=str(ml_resume_path),
    )
    ml_candidate.structured_resume = {
        "name": "Sathish Kumar V",
        "email": "sathish@example.com",
        "phone": None,
        "location": "Remote",
        "current_title": "Machine Learning Engineer",
        "skills": ["python", "fastapi", "machine learning", "nlp"],
        "experience": [],
        "education": [],
        "projects": [{"name": "Recommendation API", "summary": "ML API", "technologies": ["fastapi", "machine learning", "nlp"]}],
        "total_experience_years": 4.0,
        "links": {},
        "availability": "Immediate",
        "source": "internal",
        "summary": ml_candidate.summary,
    }

    service = ResumeAnalysisService(
        settings=Settings(
            _env_file=None,
            resume_source_dir=tmp_path,
            retrieval_top_k=5,
            candidate_pool_size=2,
            final_results_limit=2,
        ),
        candidate_repository=StubCandidateRepository([backend_candidate, ml_candidate]),
        report_run_repository=StubReportRunRepository(),
        report_repository=StubReportRepository(),
        feedback_service=StubFeedbackService(),
        embedding_model=StubEmbeddingModel(),
        reranker_model=None,
        vector_store=StubVectorStore(
            [
                RetrievedCandidateMatch(
                    candidate_id="cand_backend_role",
                    score=0.91,
                    metadata={"candidate_id": "cand_backend_role", "current_role": "Backend Engineer", "skills": ["python", "fastapi", "postgresql", "rest"], "experience_years": 4.0},
                ),
                RetrievedCandidateMatch(
                    candidate_id="cand_ml_role",
                    score=0.93,
                    metadata={"candidate_id": "cand_ml_role", "current_role": "Machine Learning Engineer", "skills": ["python", "fastapi", "machine learning", "nlp"], "experience_years": 4.0},
                ),
            ]
        ),
        graph_store=StubGraphStore(
            {
                "cand_backend_role": GraphCandidateScore(
                    candidate_id="cand_backend_role",
                    score=0.82,
                    matched_skills=["fastapi", "postgresql", "python", "rest"],
                ),
                "cand_ml_role": GraphCandidateScore(
                    candidate_id="cand_ml_role",
                    score=0.79,
                    matched_skills=["fastapi", "python"],
                ),
            }
        ),
    )

    response = await service.check_resumes(
        ResumeCheckRequest(
            job_id="jd_backend_002",
            job_title="Senior Backend Engineer",
            job_description=(
                "Need a Senior Backend Engineer with FastAPI, PostgreSQL, REST API design, "
                "clean backend architecture, and measurable project outcomes."
            ),
            source="internal",
            minimum_ats_score=0,
            retrieval_top_k=5,
            candidate_pool_size=2,
            final_top_k=2,
        )
    )

    assert response.results[0].candidate_id == "cand_backend_role"
    assert response.results[0].final_score > response.results[1].final_score
    assert any("Role alignment is strong" in reason for reason in response.results[0].reasons)
    assert any("role alignment is weak" in issue.lower() for issue in response.results[1].issues)

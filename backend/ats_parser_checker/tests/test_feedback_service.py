from __future__ import annotations

from app.models.enums import RecruiterFeedbackType
from app.repositories.feedback_event_repository import FeedbackLearningRow
from app.schemas.feedback import CandidateFeedbackRequest
from app.services.feedback_service import RecruiterFeedbackService


class _StubFeedbackRepository:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.added = []
        self.commits = 0

    async def list_learning_rows(self):
        return list(self.rows)

    async def count_by_type(self):
        counts = {}
        for row in self.rows:
            counts[row.feedback_type.value] = counts.get(row.feedback_type.value, 0) + 1
        return counts

    async def add(self, event):
        event.id = len(self.added) + 1
        self.added.append(event)
        return event

    async def commit(self):
        self.commits += 1


class _StubReportRunRepository:
    def __init__(self, run_exists=True):
        self.run_exists = run_exists

    async def get_by_id(self, report_run_id):
        if not self.run_exists:
            return None
        return type("ReportRun", (), {"id": report_run_id})()


class _StubReportRepository:
    def __init__(self, report_exists=True):
        self.report_exists = report_exists

    async def get_by_run_and_candidate(self, report_run_id, candidate_id):
        if not self.report_exists:
            return None
        return type("Report", (), {"report_run_id": report_run_id, "candidate_id": candidate_id})()


async def test_feedback_service_learns_weights_from_feedback_outcomes():
    service = RecruiterFeedbackService(
        settings=type(
            "Settings",
            (),
            {
                "final_weight_retrieval": 0.30,
                "final_weight_graph": 0.15,
                "final_weight_reranker": 0.35,
                "final_weight_ats": 0.20,
                "feedback_min_events_to_learn": 4,
                "feedback_max_weight_blend": 0.45,
            },
        )(),
        feedback_repository=_StubFeedbackRepository(
            rows=[
                FeedbackLearningRow(
                    report_run_id="run_1",
                    candidate_id="cand_a",
                    feedback_type=RecruiterFeedbackType.selected,
                    retrieval_score=0.88,
                    graph_score=0.20,
                    reranker_score=0.95,
                    ats_score=72.0,
                    final_score=83.0,
                ),
                FeedbackLearningRow(
                    report_run_id="run_1",
                    candidate_id="cand_b",
                    feedback_type=RecruiterFeedbackType.hired,
                    retrieval_score=0.84,
                    graph_score=0.25,
                    reranker_score=0.98,
                    ats_score=75.0,
                    final_score=86.0,
                ),
                FeedbackLearningRow(
                    report_run_id="run_2",
                    candidate_id="cand_c",
                    feedback_type=RecruiterFeedbackType.rejected,
                    retrieval_score=0.90,
                    graph_score=0.10,
                    reranker_score=0.18,
                    ats_score=54.0,
                    final_score=61.0,
                ),
                FeedbackLearningRow(
                    report_run_id="run_2",
                    candidate_id="cand_d",
                    feedback_type=RecruiterFeedbackType.rejected,
                    retrieval_score=0.82,
                    graph_score=0.05,
                    reranker_score=0.12,
                    ats_score=49.0,
                    final_score=55.0,
                ),
            ]
        ),
        report_run_repository=_StubReportRunRepository(),
        report_repository=_StubReportRepository(),
    )

    snapshot = await service.get_weight_snapshot()

    assert snapshot.learned_from_feedback is True
    assert snapshot.feedback_events_analyzed == 4
    assert snapshot.weights["reranker"] > snapshot.weights["retrieval"]
    assert abs(sum(snapshot.weights.values()) - 1.0) < 0.001


async def test_feedback_service_records_feedback_event():
    feedback_repository = _StubFeedbackRepository()
    service = RecruiterFeedbackService(
        settings=type(
            "Settings",
            (),
            {
                "final_weight_retrieval": 0.30,
                "final_weight_graph": 0.15,
                "final_weight_reranker": 0.35,
                "final_weight_ats": 0.20,
                "feedback_min_events_to_learn": 4,
                "feedback_max_weight_blend": 0.45,
            },
        )(),
        feedback_repository=feedback_repository,
        report_run_repository=_StubReportRunRepository(),
        report_repository=_StubReportRepository(),
    )

    response = await service.record_feedback(
        CandidateFeedbackRequest(
            report_run_id="run_1",
            candidate_id="cand_a",
            feedback_type=RecruiterFeedbackType.shortlisted,
            note="Looks like a strong shortlist option",
            metadata={"source": "manual-review"},
        )
    )

    assert response.feedback_id == 1
    assert response.feedback_type == RecruiterFeedbackType.shortlisted
    assert feedback_repository.commits == 1

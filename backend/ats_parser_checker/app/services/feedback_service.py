from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.config import Settings
from app.core.exceptions import NotFoundException
from app.models.enums import RecruiterFeedbackType
from app.models.feedback_event import CandidateFeedbackEvent
from app.repositories.feedback_event_repository import (
    FeedbackEventRepository,
    FeedbackLearningRow,
)
from app.repositories.report_run_repository import ATSReportRunRepository
from app.repositories.resume_report_repository import ResumeReportRepository
from app.schemas.feedback import (
    CandidateFeedbackRequest,
    CandidateFeedbackResponse,
    FeedbackSummaryResponse,
)

FEEDBACK_IMPACT = {
    RecruiterFeedbackType.clicked: 0.2,
    RecruiterFeedbackType.shortlisted: 0.5,
    RecruiterFeedbackType.selected: 0.8,
    RecruiterFeedbackType.hired: 1.0,
    RecruiterFeedbackType.rejected: -1.0,
}

SIGNAL_NAMES = ("retrieval", "graph", "reranker", "ats")


@dataclass(slots=True)
class RankingWeightSnapshot:
    weights: dict[str, float]
    feedback_events_analyzed: int = 0
    learned_from_feedback: bool = False


class RecruiterFeedbackService:
    def __init__(
        self,
        *,
        settings: Settings,
        feedback_repository: FeedbackEventRepository,
        report_run_repository: ATSReportRunRepository,
        report_repository: ResumeReportRepository,
    ) -> None:
        self.settings = settings
        self.feedback_repository = feedback_repository
        self.report_run_repository = report_run_repository
        self.report_repository = report_repository

    async def record_feedback(
        self,
        payload: CandidateFeedbackRequest,
    ) -> CandidateFeedbackResponse:
        report_run = await self.report_run_repository.get_by_id(payload.report_run_id)
        if report_run is None:
            raise NotFoundException(f"ATS report run '{payload.report_run_id}' was not found")

        report = await self.report_repository.get_by_run_and_candidate(
            payload.report_run_id,
            payload.candidate_id,
        )
        if report is None:
            raise NotFoundException(
                f"No ATS report is available for candidate '{payload.candidate_id}' in run "
                f"'{payload.report_run_id}'"
            )

        event = CandidateFeedbackEvent(
            report_run_id=payload.report_run_id,
            candidate_id=payload.candidate_id,
            feedback_type=payload.feedback_type,
            note=payload.note.strip() if payload.note else None,
            details=dict(payload.metadata or {}),
        )
        saved = await self.feedback_repository.add(event)
        await self.feedback_repository.commit()
        return self._build_feedback_response(saved)

    async def get_feedback_summary(self) -> FeedbackSummaryResponse:
        counts = await self.feedback_repository.count_by_type()
        snapshot = await self.get_weight_snapshot()
        return FeedbackSummaryResponse(
            total_events=sum(counts.values()),
            counts=counts,
            effective_weights=snapshot.weights,
            learned_from_feedback=snapshot.learned_from_feedback,
            feedback_events_analyzed=snapshot.feedback_events_analyzed,
        )

    async def get_weight_snapshot(self) -> RankingWeightSnapshot:
        rows = await self.feedback_repository.list_learning_rows()
        return self._learn_weight_snapshot(rows)

    def _learn_weight_snapshot(
        self,
        rows: list[FeedbackLearningRow],
    ) -> RankingWeightSnapshot:
        base_weights = self._base_weights()
        strongest_rows = self._collapse_feedback_rows(rows)
        evidence_count = len(strongest_rows)
        if evidence_count < self.settings.feedback_min_events_to_learn:
            return RankingWeightSnapshot(
                weights=base_weights,
                feedback_events_analyzed=evidence_count,
                learned_from_feedback=False,
            )

        signal_strengths = {
            "retrieval": self._signal_strength(
                strongest_rows,
                signal_name="retrieval_score",
            ),
            "graph": self._signal_strength(
                strongest_rows,
                signal_name="graph_score",
            ),
            "reranker": self._signal_strength(
                strongest_rows,
                signal_name="reranker_score",
            ),
            "ats": self._signal_strength(
                strongest_rows,
                signal_name="ats_score",
                normalize_ats=True,
            ),
        }
        total_strength = sum(signal_strengths.values())
        if total_strength <= 0:
            return RankingWeightSnapshot(
                weights=base_weights,
                feedback_events_analyzed=evidence_count,
                learned_from_feedback=False,
            )

        learned_weights = {
            name: round(strength / total_strength, 4)
            for name, strength in signal_strengths.items()
        }
        blend = min(
            self.settings.feedback_max_weight_blend,
            (evidence_count / self.settings.feedback_min_events_to_learn)
            * self.settings.feedback_max_weight_blend,
        )
        blended_weights = {
            name: ((1 - blend) * base_weights[name]) + (blend * learned_weights[name])
            for name in SIGNAL_NAMES
        }
        return RankingWeightSnapshot(
            weights=self._normalize_weights(blended_weights),
            feedback_events_analyzed=evidence_count,
            learned_from_feedback=True,
        )

    @staticmethod
    def _collapse_feedback_rows(
        rows: list[FeedbackLearningRow],
    ) -> list[tuple[FeedbackLearningRow, float]]:
        strongest: dict[tuple[str, str], tuple[FeedbackLearningRow, float]] = {}
        for row in rows:
            impact = FEEDBACK_IMPACT[row.feedback_type]
            key = (row.report_run_id, row.candidate_id)
            existing = strongest.get(key)
            if existing is None or abs(impact) >= abs(existing[1]):
                strongest[key] = (row, impact)
        return list(strongest.values())

    @staticmethod
    def _signal_strength(
        rows: list[tuple[FeedbackLearningRow, float]],
        *,
        signal_name: str,
        normalize_ats: bool = False,
    ) -> float:
        positive_total = 0.0
        positive_weight = 0.0
        negative_total = 0.0
        negative_weight = 0.0
        available_rows = 0

        for row, impact in rows:
            score = getattr(row, signal_name)
            if score is None:
                continue
            available_rows += 1
            normalized_score = float(score) / 100 if normalize_ats else float(score)
            if impact > 0:
                positive_total += normalized_score * impact
                positive_weight += impact
            else:
                negative_total += normalized_score * abs(impact)
                negative_weight += abs(impact)

        if available_rows == 0 or positive_weight == 0:
            return 0.0

        positive_mean = positive_total / positive_weight
        negative_mean = negative_total / negative_weight if negative_weight else 0.0
        participation = available_rows / max(len(rows), 1)
        return max(positive_mean - negative_mean, 0.0) * participation

    def _base_weights(self) -> dict[str, float]:
        return self._normalize_weights(
            {
                "retrieval": self.settings.final_weight_retrieval,
                "graph": self.settings.final_weight_graph,
                "reranker": self.settings.final_weight_reranker,
                "ats": self.settings.final_weight_ats,
            }
        )

    @staticmethod
    def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
        total = sum(max(value, 0.0) for value in weights.values())
        if total <= 0:
            return {name: round(1 / len(weights), 4) for name in weights}
        return {
            name: round(max(value, 0.0) / total, 4)
            for name, value in weights.items()
        }

    @staticmethod
    def _build_feedback_response(event: CandidateFeedbackEvent) -> CandidateFeedbackResponse:
        created_at: datetime | None = getattr(event, "created_at", None)
        return CandidateFeedbackResponse(
            feedback_id=event.id,
            report_run_id=event.report_run_id,
            candidate_id=event.candidate_id,
            feedback_type=event.feedback_type,
            note=event.note,
            metadata=dict(event.details or {}),
            created_at=created_at,
        )

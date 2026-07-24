from __future__ import annotations

from app.models.candidate import Candidate


def test_candidate_model_omits_redundant_file_and_vector_columns() -> None:
    assert "file_name" not in Candidate.__table__.c
    assert "vector_id" not in Candidate.__table__.c
    assert "graph_synced_at" not in Candidate.__table__.c
    assert "ingestion_error" not in Candidate.__table__.c

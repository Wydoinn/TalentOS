from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


def _fail_result(reason: str, score: float = 20.0):
    from app.api.schemas import AnalysisResult, OverallStatus, RiskLevel

    return AnalysisResult(
        overall_status=OverallStatus.FAIL,
        overall_score=score,
        face_score=10.0,
        audio_score=15.0,
        challenge_score=20.0,
        tamper_score=5.0,
        identity_consistency_score=30.0,
        reasons=[reason],
        human_readable_summary="Verification failed.",
        risk_level=RiskLevel.HIGH,
        top_issues=[reason],
        confidence="90%",
    )


@pytest.mark.anyio
async def test_create_session(client):
    response = await client.post(
        "/sessions",
        json={"candidate_id": "candidate-001", "job_id": "job-42"},
    )
    payload = response.json()

    assert response.status_code == 201
    assert payload["session_id"]
    assert payload["status"] == "created"
    assert payload["access_token"]


@pytest.mark.anyio
async def test_issue_challenge(client):
    session = (await client.post("/sessions", json={"candidate_id": "candidate-002"})).json()

    response = await client.post(
        f"/sessions/{session['session_id']}/challenge",
        json={"challenge_type": "phrase"},
        headers={"Authorization": f"Bearer {session['access_token']}"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["challenge_id"]
    assert payload["prompt"]
    assert isinstance(payload["instructions"], list)
    assert len(payload["instructions"]) >= 1


@pytest.mark.anyio
async def test_analyze_requires_auth(client, dummy_mp4):
    response = await client.post(
        "/sessions/fake-id/analyze",
        files={"video": ("clip.mp4", dummy_mp4, "video/mp4")},
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_full_pass_flow(client, dummy_mp4, pass_result):
    with patch(
        "app.pipeline.orchestrator.AntiSpoofingPipeline.analyze",
        new_callable=AsyncMock,
        return_value=pass_result,
    ):
        session = (await client.post("/sessions", json={"candidate_id": "candidate-pass"})).json()
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        session_id = session["session_id"]

        challenge_response = await client.post(
            f"/sessions/{session_id}/challenge",
            json={"challenge_type": "phrase"},
            headers=headers,
        )
        assert challenge_response.status_code == 200

        analysis_response = await client.post(
            f"/sessions/{session_id}/analyze",
            files={"video": ("clip.mp4", dummy_mp4, "video/mp4")},
            headers=headers,
        )
        analysis = analysis_response.json()

        assert analysis_response.status_code == 200
        assert analysis["overall_status"] == "PASS"
        assert 0 <= analysis["overall_score"] <= 100
        assert "human_readable_summary" in analysis
        assert "risk_level" in analysis

        finalize_response = await client.post(
            f"/sessions/{session_id}/finalize",
            headers=headers,
        )
        assert finalize_response.status_code == 200
        assert finalize_response.json()["final_decision"] == "PASS"


@pytest.mark.anyio
async def test_analyze_accepts_webm_content_type_with_codec_suffix(client, dummy_mp4, pass_result):
    with patch(
        "app.pipeline.orchestrator.AntiSpoofingPipeline.analyze",
        new_callable=AsyncMock,
        return_value=pass_result,
    ):
        session = (await client.post("/sessions", json={"candidate_id": "candidate-webm"})).json()
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        session_id = session["session_id"]

        challenge_response = await client.post(
            f"/sessions/{session_id}/challenge",
            json={"challenge_type": "phrase"},
            headers=headers,
        )
        assert challenge_response.status_code == 200

        analysis_response = await client.post(
            f"/sessions/{session_id}/analyze",
            files={
                "video": (
                    "capture.webm",
                    dummy_mp4,
                    "video/webm;codecs=vp9,opus",
                )
            },
            headers=headers,
        )

        assert analysis_response.status_code == 200
        assert analysis_response.json()["overall_status"] == "PASS"


@pytest.mark.anyio
async def test_session_detail(client):
    session = (await client.post("/sessions", json={"candidate_id": "candidate-detail"})).json()

    response = await client.get(
        f"/sessions/{session['session_id']}",
        headers={"Authorization": f"Bearer {session['access_token']}"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["candidate_id"] == "candidate-detail"
    assert "retry_count" in payload
    assert "trust_score" in payload


@pytest.mark.anyio
async def test_file_too_large(client):
    from app.config import get_settings

    session = (await client.post("/sessions", json={"candidate_id": "candidate-large"})).json()
    oversized = b"\x00" * (get_settings().MAX_FILE_SIZE_MB * 1024 * 1024 + 1024)

    response = await client.post(
        f"/sessions/{session['session_id']}/analyze",
        files={"video": ("big.mp4", oversized, "video/mp4")},
        headers={"Authorization": f"Bearer {session['access_token']}"},
    )

    assert response.status_code == 413


@pytest.mark.anyio
async def test_review_ready_session_cannot_resubmit(client, dummy_mp4):
    fail_result = _fail_result("FACE_SPOOF_DETECTED")
    with patch(
        "app.pipeline.orchestrator.AntiSpoofingPipeline.analyze",
        new_callable=AsyncMock,
        return_value=fail_result,
    ):
        session = (await client.post("/sessions", json={"candidate_id": "candidate-review"})).json()
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        session_id = session["session_id"]

        await client.post(
            f"/sessions/{session_id}/challenge",
            json={"challenge_type": "phrase"},
            headers=headers,
        )

        first_response = await client.post(
            f"/sessions/{session_id}/analyze",
            files={"video": ("clip.mp4", dummy_mp4, "video/mp4")},
            headers=headers,
        )
        assert first_response.json()["overall_status"] == "FAIL"

        second_response = await client.post(
            f"/sessions/{session_id}/analyze",
            files={"video": ("clip.mp4", dummy_mp4, "video/mp4")},
            headers=headers,
        )
        assert second_response.status_code == 409


@pytest.mark.anyio
async def test_challenge_is_required_before_analyze(client, dummy_mp4):
    session = (await client.post("/sessions", json={"candidate_id": "candidate-no-challenge"})).json()

    response = await client.post(
        f"/sessions/{session['session_id']}/analyze",
        files={"video": ("clip.mp4", dummy_mp4, "video/mp4")},
        headers={"Authorization": f"Bearer {session['access_token']}"},
    )

    assert response.status_code == 409


@pytest.mark.anyio
async def test_token_cannot_access_different_session(client):
    session_a = (await client.post("/sessions", json={"candidate_id": "candidate-a"})).json()
    session_b = (await client.post("/sessions", json={"candidate_id": "candidate-b"})).json()

    response = await client.get(
        f"/sessions/{session_b['session_id']}",
        headers={"Authorization": f"Bearer {session_a['access_token']}"},
    )

    assert response.status_code == 403


@pytest.mark.anyio
async def test_flagged_result_requires_new_challenge(client, dummy_mp4, flag_result):
    with patch(
        "app.pipeline.orchestrator.AntiSpoofingPipeline.analyze",
        new_callable=AsyncMock,
        return_value=flag_result,
    ):
        session = (await client.post("/sessions", json={"candidate_id": "candidate-flag"})).json()
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        session_id = session["session_id"]

        await client.post(
            f"/sessions/{session_id}/challenge",
            json={"challenge_type": "phrase"},
            headers=headers,
        )

        analysis_response = await client.post(
            f"/sessions/{session_id}/analyze",
            files={"video": ("clip.mp4", dummy_mp4, "video/mp4")},
            headers=headers,
        )
        analysis = analysis_response.json()

        assert analysis_response.status_code == 200
        assert analysis["overall_status"] == "FLAG"
        assert analysis["retry_allowed"] is True

        detail_response = await client.get(f"/sessions/{session_id}", headers=headers)
        detail = detail_response.json()

        assert detail_response.status_code == 200
        assert detail["status"] == "retry_required"
        assert detail["challenge"] is None

        second_try = await client.post(
            f"/sessions/{session_id}/analyze",
            files={"video": ("clip.mp4", dummy_mp4, "video/mp4")},
            headers=headers,
        )
        assert second_try.status_code == 409


@pytest.mark.anyio
async def test_failed_session_can_be_finalized_and_locked(client, dummy_mp4):
    fail_result = _fail_result("AUDIO_SPOOF_DETECTED", score=10.0)
    with patch(
        "app.pipeline.orchestrator.AntiSpoofingPipeline.analyze",
        new_callable=AsyncMock,
        return_value=fail_result,
    ):
        session = (await client.post("/sessions", json={"candidate_id": "candidate-finalize"})).json()
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        session_id = session["session_id"]

        await client.post(
            f"/sessions/{session_id}/challenge",
            json={"challenge_type": "phrase"},
            headers=headers,
        )
        await client.post(
            f"/sessions/{session_id}/analyze",
            files={"video": ("clip.mp4", dummy_mp4, "video/mp4")},
            headers=headers,
        )

        finalize_response = await client.post(
            f"/sessions/{session_id}/finalize",
            headers=headers,
        )
        assert finalize_response.status_code == 200
        assert finalize_response.json()["final_decision"] == "FAIL"

        lock_response = await client.post(
            f"/sessions/{session_id}/lock",
            headers=headers,
        )
        assert lock_response.status_code == 200
        assert lock_response.json()["status"] == "locked"


@pytest.mark.anyio
async def test_openapi_documents_session_error_responses(client):
    response = await client.get("/openapi.json")
    payload = response.json()

    assert response.status_code == 200

    paths = payload["paths"]
    analyze_responses = paths["/sessions/{session_id}/analyze"]["post"]["responses"]
    finalize_responses = paths["/sessions/{session_id}/finalize"]["post"]["responses"]
    challenge_responses = paths["/sessions/{session_id}/challenge"]["post"]["responses"]
    lock_responses = paths["/sessions/{session_id}/lock"]["post"]["responses"]
    detail_schema = {"$ref": "#/components/schemas/DetailResponse"}

    for code in ("401", "403", "404", "409"):
        assert challenge_responses[code]["content"]["application/json"]["schema"] == detail_schema

    for code in ("401", "403", "404", "409", "413", "415"):
        assert analyze_responses[code]["content"]["application/json"]["schema"] == detail_schema

    assert finalize_responses["409"]["content"]["application/json"]["schema"] == detail_schema
    assert lock_responses["409"]["content"]["application/json"]["schema"] == detail_schema

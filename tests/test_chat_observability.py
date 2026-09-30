from __future__ import annotations

import json
import asyncio
import re
from pathlib import Path

import httpx

from app import logging_config
from app.main import app


def test_chat_response_log_exposes_quality_for_dashboard(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(
                "/chat",
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": "Explain observability",
                },
            )

    response = asyncio.run(send_request())

    assert response.status_code == 200
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    response_event = next(event for event in events if event["event"] == "response_sent")
    assert re.fullmatch(r"req-[0-9a-f]{8}", response.headers["x-request-id"])
    assert response.headers["x-request-id"] == response.json()["correlation_id"]
    assert response.headers["x-response-time-ms"].replace(".", "", 1).isdigit()
    assert response_event["correlation_id"] == response.headers["x-request-id"]
    assert response_event["user_id_hash"] != "student-01"
    assert response_event["session_id"] == "session-01"
    assert response_event["feature"] == "qa"
    assert response_event["model"] == "claude-sonnet-4-5"
    assert response_event["env"] == "dev"
    assert response_event["quality_score"] == response.json()["quality_score"]
    assert response_event["ttft_ms"] == response.json()["ttft_ms"]
    assert response_event["tool_name"] == "retrieval"
    assert response_event["tool_success"] is True


def test_chat_accepts_valid_request_id() -> None:
    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(
                "/chat",
                headers={"x-request-id": "req-a1b2c3d4"},
                json={
                    "user_id": "student-02",
                    "session_id": "session-02",
                    "feature": "qa",
                    "message": "Explain observability",
                },
            )

    response = asyncio.run(send_request())
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-a1b2c3d4"
    assert response.json()["correlation_id"] == "req-a1b2c3d4"


def test_chat_replaces_invalid_request_id() -> None:
    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(
                "/chat",
                headers={"x-request-id": "not-a-request-id"},
                json={
                    "user_id": "student-03",
                    "session_id": "session-03",
                    "feature": "qa",
                    "message": "Explain observability",
                },
            )

    response = asyncio.run(send_request())
    assert response.status_code == 200
    assert re.fullmatch(r"req-[0-9a-f]{8}", response.headers["x-request-id"])
    assert response.json()["correlation_id"] == response.headers["x-request-id"]

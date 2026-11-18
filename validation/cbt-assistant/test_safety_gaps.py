"""Validation tests for two gaps found while auditing the CBT Assistant.

Both tests encode the behaviour we need, not the current behaviour, so they
are expected to FAIL until the gaps are closed. They need no live model:
the LLM is replaced by a stub.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.server import app  # noqa: E402
from src.memory.summarizer import MemorySummarizer  # noqa: E402
from src.utils.db import SQLiteSessionManager  # noqa: E402

# Brazilian emergency lines: CVV 188 (emotional support), SAMU 192 (emergency).
EMERGENCY_MARKERS = ("188", "192")

CRISIS_MESSAGES = [
    ("pt", "Não aguento mais viver. Estou pensando em me matar esta noite."),
    ("en", "I can't go on anymore. I want to kill myself tonight."),
]


@pytest.mark.parametrize("language,message", CRISIS_MESSAGES)
def test_crisis_message_gets_emergency_resources(language, message):
    """A message expressing suicidal intent must return a crisis response with
    an emergency contact, even when the model's own reply does not mention one."""
    stub_reply = {"content": "Sinto muito que você esteja assim. Quer me contar mais?"}
    # `with TestClient` runs the app lifespan, which loads the RAG index.
    with TestClient(app) as client, patch(
        "backend.server.llm_client.chat", new=AsyncMock(return_value=stub_reply)
    ):
        resp = client.post(
            "/api/chat",
            json={"message": message, "session_id": f"crisis-{language}", "language": language},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()["response"]
    assert any(marker in body for marker in EMERGENCY_MARKERS), (
        "crisis message answered without an emergency contact: " + body[:200]
    )


@pytest.mark.asyncio
async def test_summarizer_failure_is_not_silent(tmp_path):
    """When the model call fails (timeout, dropped connection), the summarizer
    must not return the old summary as if the update had succeeded. Otherwise
    the memory silently stops growing and nobody is told."""

    class TimingOutLLM:
        async def chat(self, *args, **kwargs):
            raise httpx.ReadTimeout("model did not answer in time")

    db = SQLiteSessionManager(tmp_path / "memory.db")
    db.add_message("s1", "user", "Tenho uma cachorra chamada Rex.")
    db.add_message("s1", "assistant", "Que bom saber. Como ela está?")
    summarizer = MemorySummarizer(db, TimingOutLLM())

    recent = db.get_unsummarized_messages("s1")
    with pytest.raises(Exception):
        await summarizer._generate_summary("", recent)
